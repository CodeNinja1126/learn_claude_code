# learn_claude_code 프로젝트 분석

분석 대상: `/home/hyunwoo/workspace/learn_claude_code`

## 1. 프로젝트 요약

이 프로젝트는 `learn-claude-code`류의 에이전트 동작 방식을 직접 학습하고 재구현하기 위한 Python 기반 실험용 코드베이스입니다.

핵심 목표는 다음으로 보입니다.

- OpenAI 호환 API, 특히 로컬 Qwen/Ollama 계열 엔드포인트를 사용해 에이전트 루프 구현
- Claude Code 스타일의 기능을 단계별 챕터로 학습
  - tool calling
  - bash 실행
  - 파일 읽기/쓰기/수정
  - 권한 체크
  - hook
  - subagent
  - todo reminder
  - skill loading
  - context compaction
- 공통 유틸리티는 `src/util`에 모으고, 각 `s01`, `s02` 등 챕터에서 점진적으로 기능 확장

즉, 완성형 제품이라기보다는 Claude Code의 내부 패턴을 로컬 LLM 기반으로 따라 만들어보는 학습용 하네스에 가깝습니다.

---

## 2. 전체 구조

대략적인 구조는 다음과 같습니다.

```text
learn_claude_code/
├── README.md
├── pyproject.toml
├── package.json
├── memory/
│   └── project.md
├── scripts/
│   └── run_chapter.py
├── src/
│   └── util/
│       ├── config.py
│       ├── client.py
│       ├── loop.py
│       ├── messages.py
│       └── tools/
│           ├── registry.py
│           ├── filesystem.py
│           └── shell.py
├── tests/
│   ├── test_config.py
│   └── test_tools.py
├── s01/
├── s02/
├── s03/
├── s04/
├── s06/
├── s07/
├── s08/
├── s09/
...
└── s20/
```

챕터별 디렉터리는 실험 단위이고, `src/util`은 공통 재사용 유틸리티입니다.

---

## 3. 설정 구조

설정 우선순위는 다음과 같습니다.

1. shell environment
2. `.env`
3. `.env.example`

주요 환경 변수는 다음입니다.

```text
OPENAI_BASE_URL
OPENAI_API_KEY
QWEN_MODEL
```

`src/util/config.py`의 `load_config()`가 이 설정을 읽고, `src/util/client.py`의 `create_client()`가 OpenAI 클라이언트를 생성합니다.

장점:

- 로컬 LLM, OpenAI 호환 서버, Qwen 모델 등을 쉽게 바꿀 수 있음
- 설정 우선순위가 명확함
- 테스트가 존재함

개선점:

- 일부 챕터 코드에서는 설정 구조를 완전히 따르지 않고 endpoint를 하드코딩하는 부분이 있음
- OpenAI-compatible API와 Ollama native API 사용 방식을 명확히 분리하는 것이 좋음

---

## 4. 핵심 공통 유틸리티

### 4.1 `util.config`

역할:

- `.env`, `.env.example`, shell env를 읽어서 모델 설정 구성
- 기본 모델명, base URL, API key 제공

개선점:

- 누락된 필수 값에 대한 에러 메시지 개선
- base URL이 OpenAI Chat Completions 호환인지, Ollama native API인지 구분하는 validation 추가 고려

### 4.2 `util.client`

역할:

- OpenAI Python SDK 클라이언트 생성
- 설정값 기반으로 `base_url`, `api_key` 주입

개선점:

- timeout, max retries, logging 옵션 추가
- local endpoint가 죽었을 때 진단 메시지 제공

### 4.3 `util.loop.AgentLoop`

역할:

- messages 유지
- LLM 호출
- tool call 실행
- tool 결과를 다시 messages에 넣고 반복

장점:

- Claude Code식 tool loop의 최소 구조를 잘 보여줌
- 도구 registry와 결합해 확장 가능
- 챕터별 중복 구현보다 재사용성이 높음

개선점:

- tool call 실패 시 복구 정책 필요
- 최대 반복 횟수 설정 필요
- assistant message serialization 방식 통일 필요
- tool result 메시지 포맷 검증 필요
- permission, hook, context compaction 등을 middleware처럼 끼울 수 있는 구조로 발전 가능

### 4.4 `util.tools.registry`

역할:

- 사용할 수 있는 tool 목록과 schema 제공
- `list_files`, `read_text`, `run_command` 등을 registry로 묶음

장점:

- OpenAI function calling에 맞는 `parameters` 스키마를 사용하고 있음
- 챕터별 코드보다 표준적인 OpenAI SDK 호환 구조에 가까움

### 4.5 `util.tools.filesystem`

역할:

- 파일 목록 조회
- 텍스트 파일 읽기

개선점:

- workspace sandboxing이 약함
- 실제 에이전트 도구로 쓰려면 root 경계 제한 필요
- `../` path traversal, symlink escape, 절대 경로 접근 방지 필요

### 4.6 `util.tools.shell`

역할:

- shell command 실행

개선점:

- 명령어 허용/차단 정책 필요
- timeout 필요
- cwd 제한 필요
- stdout/stderr 크기 제한 필요
- destructive command 차단 필요
- 사용자 승인 흐름과 연결 필요

---

## 5. 챕터별 진행 상황

### `s01`

기초 agent loop와 bash/tool call 실험 단계로 보입니다.

발견된 문제:

```python
json.JSONDEcodeError
```

정상은 다음입니다.

```python
json.JSONDecodeError
```

또한 OpenAI function schema와 Anthropic-style schema가 섞인 흔적이 있습니다.

### `s02`

파일 읽기/쓰기/수정/glob 등을 확장한 단계로 보입니다.

발견된 문제:

- raw `message` 객체를 `messages`에 append하는 코드가 있음
- 다음 OpenAI 호출에서 직렬화 문제가 날 가능성이 있음
- `message.model_dump(...)` 또는 명확한 dict 변환을 사용하는 편이 안전함
- `WORKDIR = os.getcwd()` 후 `WORKDIR / match` 형태의 Path 연산이 있을 경우 `TypeError` 가능

권장:

```python
from pathlib import Path

WORKDIR = Path.cwd().resolve()
```

### `s03`

권한 체크가 들어간 단계로 보입니다.

좋은 방향입니다. Claude Code 스타일 에이전트에서는 file write, shell command, external action에 대한 permission layer가 중요합니다.

발견된 문제:

- `safe_path` 계열에서 `WORKDIR`가 문자열이면 타입 안정성이 떨어짐
- `WORKDIR`는 처음부터 `Path.cwd().resolve()`로 두는 것이 좋음
- glob 처리 역시 `Path` 기반으로 통일하는 것이 안전함

### `s04`

hook 관련 단계로 보입니다.

개선 방향:

- pre-tool hook
- post-tool hook
- pre-LLM hook
- post-LLM hook
- error hook

처럼 hook point를 명확히 나누면 학습 효과가 좋아집니다.

### `s06`

subagent와 todo reminder 관련 단계로 보입니다.

개선 방향:

- subagent 입력/출력 스키마 명확화
- subagent의 tool 접근 권한 제한
- subagent 결과를 요약해서 main context에 반영
- 실패/타임아웃 처리 추가

### `s07`

skill loading 관련 단계로 보입니다.

개선 방향:

- skill metadata 구조 정의
- skill activation condition 명시
- skill loading 후 system prompt에 어떻게 반영되는지 정리
- skill 간 충돌 처리
- skill이 tool, prompt, workflow 중 무엇을 제공하는지 구분

### `s08`

context compaction/reactive compaction 관련 단계로 보입니다.

개선 방향:

- token budget 추정 로직 추가
- compaction trigger 기준 정의
- compacted summary와 raw messages 분리
- tool result 요약 정책화
- irreversible summary 손실 방지용 checkpoint 전략 추가

### `s09`–`s20`

대부분 placeholder stub 상태로 보입니다.

README나 각 디렉터리 안에 다음을 명시하면 좋습니다.

```text
Status: placeholder
Goal:
Planned concepts:
Current runnable: no
```

---

## 6. 주요 설계상 장점

### 6.1 단계별 학습 구조

다음 흐름으로 자연스럽게 기능이 확장됩니다.

```text
LLM call
→ tool call
→ file tools
→ permission
→ hooks
→ subagents
→ skills
→ context compaction
```

Claude Code의 핵심 구성 요소를 직접 구현하면서 이해하기 좋은 구조입니다.

### 6.2 공통 유틸리티와 챕터 실험 코드 분리

`src/util`에 공통 코드를 모으고, 챕터별 폴더에서 실험하는 구조는 유지보수에 유리합니다.

향후에는 챕터별로 중복 구현된 tool schema, client 생성, message loop를 점차 `src/util`로 끌어올리면 좋습니다.

### 6.3 OpenAI-compatible endpoint 사용

로컬 Qwen, Ollama, vLLM, LM Studio 등과 연결할 수 있는 방향이라 실험성이 좋습니다.

단, OpenAI-compatible API와 Ollama native API는 경로와 payload 구조가 다르므로, 이 둘을 명확히 분리해야 합니다.

### 6.4 테스트 존재

`tests/test_config.py`, `tests/test_tools.py`가 존재합니다.

학습용 프로젝트라도 테스트가 있다는 점은 좋습니다.

---

## 7. 가장 중요한 개선 사항

### 1순위: OpenAI tool schema 정규화

일부 챕터 코드에서 Anthropic-style schema와 OpenAI-style schema가 섞인 것으로 보입니다.

OpenAI Chat Completions에서는 다음 형태가 필요합니다.

```python
{
    "type": "function",
    "function": {
        "name": "read_text",
        "description": "Read a text file",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        }
    }
}
```

반면 Anthropic 스타일은 보통 다음 형태입니다.

```python
{
    "name": "read_text",
    "description": "Read a text file",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"}
        }
    }
}
```

현재 프로젝트는 OpenAI SDK 기반이므로 `parameters`로 통일하는 편이 좋습니다.

### 2순위: assistant message 직렬화 통일

OpenAI SDK의 message 객체를 그대로 `messages.append(message)` 하면 다음 호출에서 문제가 생길 수 있습니다.

권장 방식:

```python
messages.append(message.model_dump(exclude_none=True))
```

또는 프로젝트 전용 helper를 둘 수 있습니다.

```python
def normalize_message(message):
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return message
```

### 3순위: Path 처리와 sandboxing 통일

권장 방식:

```python
from pathlib import Path

WORKDIR = Path.cwd().resolve()

def safe_path(path: str) -> Path:
    target = (WORKDIR / path).resolve()
    if not target.is_relative_to(WORKDIR):
        raise ValueError("Path escapes workspace")
    return target
```

이렇게 해야 다음 문제를 방지할 수 있습니다.

- `str / str` 연산 오류
- `../` path traversal
- symlink escape
- 절대 경로 접근
- workspace 밖 파일 읽기/쓰기

### 4순위: shell command 안전장치 추가

추천 사항:

```text
- cwd는 workspace로 제한
- timeout 기본값 설정
- stdout/stderr 최대 길이 제한
- destructive command 차단 또는 승인 요구
- network command 제한 옵션
- command allowlist/denylist
```

### 5순위: 챕터별 중복 코드 정리

권장 방향:

```text
src/util/
├── loop.py              # agent loop
├── tools/
│   ├── registry.py      # tool schema + dispatch
│   ├── filesystem.py
│   └── shell.py
├── permissions.py       # permission policy
├── hooks.py             # hook manager
├── subagents.py         # subagent runner
├── skills.py            # skill loader
└── compaction.py        # context compaction
```

### 6순위: 테스트 확대

추가하면 좋은 테스트:

```text
- OpenAI tool schema shape 검증
- AgentLoop가 tool call을 처리하는지
- tool call 실패 시 에러 메시지를 반환하는지
- safe_path가 ../ escape를 막는지
- glob이 workspace 내부 결과만 반환하는지
- shell tool timeout 동작
- permission denied 시 실행이 중단되는지
- context compaction trigger 동작
```

---

## 8. 잠재 버그 요약

| 위치 | 문제 | 영향 |
|---|---|---|
| `s01` | `json.JSONDEcodeError` 오타 | JSON 파싱 실패 처리 시 예외 |
| `s02` | raw message 객체 append | 다음 OpenAI 호출에서 serialization 문제 |
| `s02/s03` | `WORKDIR = os.getcwd()` 후 Path 연산 | glob/path 처리 실패 가능 |
| `s02/s03` | `WORKDIR / match` | `TypeError` 가능 |
| `s03` | `safe_path` 타입 혼용 | sandbox 검증 불안정 |
| 일부 챕터 | `input_schema` 사용 | OpenAI tool calling 비호환 가능 |
| 일부 코드 | Ollama native endpoint 하드코딩 | 설정 기반 실행과 충돌 |
| `filesystem.py` | sandbox 없음 | workspace 밖 파일 접근 가능 |
| `shell.py` | timeout/permission 약함 | 위험 명령 실행 가능 |

---

## 9. 추천 리팩터링 순서

```text
1. 모든 WORKDIR를 Path.cwd().resolve()로 통일
2. safe_path 공통 함수 작성
3. filesystem/glob/read/write/edit 도구가 safe_path를 사용하게 변경
4. OpenAI tool schema를 parameters 기반으로 통일
5. assistant message serialization helper 추가
6. AgentLoop에 max_steps, error handling, timeout 추가
7. shell tool에 timeout/cwd/stdout limit 추가
8. s01~s03 테스트 추가
9. s04~s08 개념을 util 모듈로 승격
10. s09~s20은 placeholder 상태 명시 또는 구현
```

---

## 10. 결론

이 프로젝트는 Claude Code 스타일 에이전트의 핵심 구조를 학습하기에 좋은 출발점입니다.

특히 다음 흐름이 잘 잡혀 있습니다.

```text
basic loop
→ tools
→ filesystem
→ permissions
→ hooks
→ subagents
→ skills
→ context compaction
```

다만 현재는 학습 실험 코드와 재사용 가능한 공통 코드가 섞여 있고, 일부 챕터에는 OpenAI SDK와 맞지 않는 schema, Path 타입 문제, message serialization 문제가 있습니다.

가장 먼저 고치면 좋은 것은 다음 네 가지입니다.

1. OpenAI tool schema를 `parameters` 기반으로 통일
2. assistant message를 dict로 직렬화해서 저장
3. `Path.cwd().resolve()` 기반의 `safe_path()` 도입
4. shell/file tool에 workspace sandbox와 timeout 추가

이 네 가지를 정리하면 프로젝트 안정성이 크게 올라가고, 이후 hook/subagent/skill/context compaction 같은 고급 기능을 훨씬 깔끔하게 확장할 수 있습니다.
