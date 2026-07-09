# s11 Error Recovery

이 챕터는 코딩 에이전트가 모델 호출 실패를 만나도 가능한 범위 안에서 자동으로
복구하고, 복구할 수 없는 오류는 대화 히스토리에 명확히 남긴 뒤 안전하게 멈추도록
구현한다.

원본 예제 `s11_error_recovery/code.py`의 핵심은 세 가지 복구 경로다. 이 저장소의
챕터 구조는 Anthropic 단일 파일 스크립트가 아니라 OpenAI-compatible Chat
Completions 클라이언트와 모듈형 에이전트 구조를 사용하므로, 같은 아이디어를
`error_recovery.py`로 분리하고 `agent.py`에서 호출하도록 연결했다.

## 파일 구성

```text
chapters/s11_error_recovery/
├── main.py                # REPL 진입점과 훅 등록
├── agent.py               # 모델 호출, 도구 실행, recovery 연결
├── error_recovery.py      # 토큰 제한, context 초과, 429/529 복구 로직
├── context_compact.py     # 자동 compact와 reactive compact
├── tool.py                # bash/read/write/edit/glob/todo/load_skill 도구
├── hook.py                # 권한, 로그, large output, Stop 훅
├── memory.py              # 대화 후 메모리 추출과 통합
├── subagent.py            # task 하위 에이전트 도구
└── system_prompt.py       # system/developer prompt 조립
```

## 전체 흐름

```text
user message
  -> hooks
  -> memory load
  -> L1/L2/L3 compact
  -> model call through call_with_retries()
  -> max token recovery or context recovery or transient retry
  -> assistant message
  -> tool calls
  -> Stop hook, memory extraction, memory consolidation
```

`agent_loop()`는 매 모델 호출마다 `RecoveryState`를 사용한다. 이 상태 객체는 현재
모델, 출력 토큰 한도, 529 연속 횟수, reactive compact 수행 여부, continuation 횟수를
추적한다.

## 복구 경로 1: 출력 토큰 제한

OpenAI-compatible 응답에서 `finish_reason`이 `length`이거나 Anthropic 스타일의
`stop_reason`이 `max_tokens`이면 출력 토큰 제한에 걸린 것으로 본다.

첫 번째 제한은 잘린 응답을 히스토리에 추가하지 않고 같은 요청을 더 큰
`max_tokens`로 다시 보낸다. 기본값은 `8000`에서 `64000`으로 증가한다.

두 번째 이후에도 계속 잘리면 잘린 assistant 응답을 히스토리에 보존하고, 다음 user
메시지로 continuation prompt를 추가한다.

```text
Output token limit hit. Resume directly. Do not apologize or recap; continue from the exact stopping point.
```

continuation은 기본 3회까지만 수행한다. 계속 `max_tokens`에 걸리면 무한 루프를 막기
위해 `[max_tokens] recovery limit reached`를 출력하고 현재 턴을 종료한다.

## 복구 경로 2: 프롬프트 또는 컨텍스트 초과

모델 호출 예외 메시지에 `prompt_too_long`, `context_length_exceeded`, `maximum context
length`, `too many tokens` 같은 marker가 있으면 context limit 오류로 판단한다.

처음 한 번은 `context_compact.reactive_compact()`를 실행한다. 이 함수는 현재 대화를
`.transcripts/`에 저장하고, 오래된 대화는 요약으로 바꾼 뒤 최근 메시지와 이어 붙인다.

reactive compact 후 같은 context limit 오류가 다시 발생하면 더 이상 반복하지 않는다.
대신 assistant 메시지로 `[Error] <ErrorName>: <message>`를 추가하고 현재 턴을 종료한다.

## 복구 경로 3: 429와 529 일시 오류

`call_with_retries()`는 모델 호출 주변을 감싸고 transient error만 재시도한다.

429 rate limit은 exponential backoff와 jitter를 사용한다. 응답 헤더에 `Retry-After`가
있으면 그 값을 우선 사용한다.

529 overloaded도 exponential backoff와 jitter를 사용한다. 529가 기본 3회 연속 발생하면
fallback 모델이 설정되어 있을 때 `RecoveryState.current_model`을 fallback 모델로 바꾼다.

transient retry는 기본 10회까지 수행한다. retry 횟수를 모두 소진하면 unrecoverable
오류로 처리하고 현재 턴을 종료한다.

## 설정값

기본 모델 설정은 프로젝트 공통 설정을 따른다.

```bash
OPENAI_BASE_URL=http://localhost:10531/v1
OPENAI_API_KEY=gpt-local
QWEN_MODEL=gpt-5.5
```

error recovery 전용 설정은 shell 환경변수 또는 프로젝트 루트의 `.env`에서 읽는다.

```bash
FALLBACK_QWEN_MODEL=gpt-5.5-mini
ERROR_RECOVERY_DEFAULT_MAX_TOKENS=8000
ERROR_RECOVERY_ESCALATED_MAX_TOKENS=64000
ERROR_RECOVERY_MAX_RETRIES=10
ERROR_RECOVERY_BASE_DELAY_MS=500
ERROR_RECOVERY_MAX_CONSECUTIVE_529=3
ERROR_RECOVERY_MAX_CONTINUATIONS=3
```

`FALLBACK_MODEL_ID`도 호환 이름으로 지원한다. `FALLBACK_QWEN_MODEL`이 있으면 그것을
우선 사용한다.

## 실행 방법

루트 디렉터리에서 챕터 runner를 사용한다.

```bash
uv run python scripts/run_chapter.py s11_error_recovery
```

직접 실행하려면 `src`와 챕터 디렉터리가 `PYTHONPATH`에 있어야 하므로 runner 사용을
권장한다.

## 구현 포인트

`error_recovery.py`는 모델 호출 자체를 알지 않는다. 대신 `Callable[[str, int], Any]`를
받아 현재 모델 이름과 `max_tokens`만 주입한다. 그래서 OpenAI-compatible client를 쓰는
`agent.py`가 요청 메시지와 도구 목록을 계속 책임진다.

`agent.py`는 `call_with_retries()`가 반환한 응답을 받은 뒤 `completion_hit_token_limit()`로
출력 제한 여부를 확인한다. 토큰 제한 복구는 응답을 히스토리에 넣을지 말지 결정해야
하므로 agent loop 안에서 처리한다.

context limit 오류는 일반 transient retry와 다르게 처리한다. 재시도 전에 메시지 배열을
줄여야 하기 때문에 `agent.py`의 예외 처리 블록에서 `reactive_compact()`를 호출한다.

도구 실행 오류는 모델 호출 실패와 다르게 취급한다. `tool.py`의 각 handler는 대부분
예외를 문자열 `Error: ...`로 바꿔 tool result에 넣고, 다음 모델 턴이 그 오류를 보고
수정 행동을 선택하게 한다.

## 현재 구현의 한계

- fallback 모델 변경은 메인 `agent_loop()`의 모델 호출에 적용된다.
- `subagent.py`, `memory.py`, `context_compact.py` 내부의 보조 모델 호출은 아직 별도 retry wrapper를 쓰지 않는다.
- context limit marker는 provider별 메시지 문자열에 의존한다.
- `max_tokens=64000`은 endpoint가 지원하는 실제 출력 한도를 넘을 수 있다.
- 학습용 구현이므로 retry 중단 후 자동으로 새 작업 세션을 만들지는 않는다.
