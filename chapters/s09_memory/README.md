# s09 Memory

이 챕터는 에이전트가 대화 중 알게 된 사용자 선호, 피드백, 프로젝트 사실을
다음 요청에서도 다시 사용할 수 있도록 `.memory/` 디렉터리에 저장하는 기능을
구현한다.

핵심 아이디어는 두 가지다.

1. 저장된 메모리의 색인을 시스템 지시에 넣어 에이전트가 어떤 기억이 있는지 알게 한다.
2. 현재 요청과 관련 있는 메모리만 골라 모델 호출 직전에 추가 컨텍스트로 주입한다.

## 파일 구성

```text
chapters/s09_memory/
├── main.py               # 에이전트 루프와 메모리 기능 연결
├── memory_func.py        # 메모리 저장, 색인, 선택, 추출, 통합
├── context_compact.py    # 긴 대화 압축
├── tool.py               # bash/read/write/edit/glob/todo/load_skill 도구
├── hook.py               # 권한, 로그, Stop 훅
├── subagent.py           # task 하위 에이전트 도구
├── skill.py              # skills/ 디렉터리 스캔
└── notes.md              # 챕터 메모
```

런타임 메모리는 프로젝트 실행 위치인 `WORKDIR` 아래의 `.memory/`에 저장된다.
`WORKDIR`는 `util.WORKDIR`이며 현재 프로세스의 작업 디렉터리다.

```text
.memory/
├── MEMORY.md             # 전체 메모리 색인
├── user-preference.md    # 개별 메모리 파일 예시
└── project-fact.md       # 개별 메모리 파일 예시
```

## 메모리 파일 포맷

각 메모리는 Markdown 파일 하나로 저장된다. 파일 앞에는 간단한 YAML 형태의
frontmatter가 붙는다.

```markdown
---
name: user-preference-tabs
description: User prefers tab-based navigation in examples.
type: user
---

The user prefers tab-based navigation when a UI has multiple modes.
```

필드는 다음 의미를 가진다.

| 필드 | 의미 |
| --- | --- |
| `name` | 짧은 메모리 이름. 파일명 생성에도 사용된다. |
| `description` | 색인과 관련도 판단에 쓰는 한 줄 요약. |
| `type` | 메모리 종류. 현재 구현은 `user`, `feedback`, `project`, `reference`를 사용한다. |
| 본문 | 모델에 주입될 실제 상세 내용. Markdown으로 작성된다. |

`write_memory_file()`은 `name`을 소문자 slug로 바꿔 파일명을 만들고, 저장 후
`MEMORY.md` 색인을 다시 만든다.

## 메모리 종류

현재 구현의 메모리 타입은 네 가지다.

| 타입 | 저장 대상 |
| --- | --- |
| `user` | 사용자의 선호, 작업 방식, 반복적으로 따라야 할 개인 규칙 |
| `feedback` | 이전 답변이나 작업에 대한 사용자 피드백 |
| `project` | 프로젝트 구조, 목표, 현재 상태 같은 사실 |
| `reference` | 외부 문서, 링크, 기준 자료에 대한 포인터 |

타입은 저장된 정보를 나중에 정리하거나 우선순위를 판단하기 위한 힌트다. 현재
선택 로직은 타입보다 `name`과 `description` 중심으로 관련도를 판단한다.

## 전체 동작 흐름

### 1. 시작 시 메모리 색인 읽기

`main.py`의 `build_system()`은 `read_memory_index()`로 `.memory/MEMORY.md`를 읽는다.
색인이 있으면 시스템 지시에 다음 내용을 추가한다.

```text
Memories available:
- [memory-name](memory-file.md) - description
```

이 단계에서는 개별 메모리 본문 전체를 넣지 않는다. 전체 본문을 항상 넣으면
컨텍스트가 빠르게 커질 수 있기 때문에, 먼저 색인만 알려준다.

### 2. 사용자 요청을 보고 관련 메모리 선택

`agent_loop()`는 모델을 호출하기 전에 `load_memories(messages)`를 실행한다.

`load_memories()`는 내부에서 `select_relevant_memories()`를 호출한다. 선택 기준은
최근 사용자 메시지 최대 3개와 메모리 카탈로그의 `name`, `description`이다.

우선 작은 모델 호출로 관련 메모리 번호를 고르게 한다.

```json
[0, 3]
```

모델 호출이나 JSON 파싱이 실패하면 fallback으로 단순 키워드 매칭을 사용한다.
이 fallback은 최근 요청 단어 중 길이가 4자를 넘는 단어가 메모리 이름이나 설명에
포함되는지 확인한다.

### 3. 관련 메모리 본문 주입

선택된 파일이 있으면 `load_memories()`는 다음 형태의 문자열을 만든다.

```xml
<relevant_memories>
---
name: ...
description: ...
type: ...
---

...
</relevant_memories>
```

`main.py`의 `_with_relevant_memories()`는 이 내용을 첫 번째 instruction 메시지에
추가한다. 주입 문구에는 메모리를 새 사용자 요청으로 취급하지 말라는 지시가 포함된다.

```text
Use these as developer-provided context. Do not treat them as a new user request.
```

즉, 메모리는 사용자의 현재 요청을 대체하지 않고 현재 요청을 해석하기 위한 배경
정보로만 사용된다.

### 4. 응답 후 새 메모리 추출

에이전트가 도구 호출 없이 최종 답변을 만들면 `extract_memories(pre_compress)`가
실행된다.

이 함수는 최근 메시지 최대 10개를 모아 모델에게 다음 정보를 JSON 배열로 추출하게 한다.

```json
[
  {
    "name": "user-prefers-small-diffs",
    "type": "user",
    "description": "User prefers small reviewable diffs.",
    "body": "The user prefers small, reviewable code changes."
  }
]
```

추출 대상은 사용자 선호, 제약, 프로젝트 사실이다. 이미 기존 메모리에 포함된 내용이면
빈 배열을 반환하도록 프롬프트가 되어 있다.

### 5. 메모리 통합

`consolidate_memories()`는 개별 메모리 파일이 10개 이상일 때 실행된다.

통합 단계는 모든 메모리의 요약과 본문을 모델에 전달하고 다음 규칙으로 정리된 새
배열을 받는다.

1. 중복 메모리는 합친다.
2. 오래되었거나 모순된 메모리는 제거한다.
3. 전체 메모리는 30개 미만으로 유지한다.
4. 중요한 사용자 선호를 우선 보존한다.

현재 구현은 통합 결과를 받은 뒤 기존 개별 메모리 파일을 삭제하고 새 결과를 다시
저장한다. `MEMORY.md` 색인 파일은 삭제하지 않는다.

## `main.py`와의 연결 지점

메모리 기능은 `main.py`의 네 지점에 연결되어 있다.

| 위치 | 역할 |
| --- | --- |
| import 영역 | `memory_func.py`에서 `read_memory_index`, `load_memories`, `extract_memories`, `consolidate_memories`를 가져온다. |
| `build_system()` | 시작 시 메모리 색인을 시스템 지시에 넣는다. |
| `agent_loop()` 모델 호출 전 | 현재 요청에 관련 있는 메모리 본문을 선택해서 주입한다. |
| `agent_loop()` 최종 응답 후 | 새 메모리를 추출하고, 필요하면 통합한다. |

메모리 주입 전에 `_openai_compatible_messages()`를 거친다. 이 함수는 압축이나 중간
상태 때문에 생긴 orphan tool message, 불완전한 tool exchange를 제거해
OpenAI-compatible Chat Completions API가 거부하지 않는 메시지 형태로 만든다.

## 컨텍스트 압축과 메모리의 차이

이 챕터에는 `context_compact.py`도 함께 있다. 하지만 메모리와 컨텍스트 압축은 목적이
다르다.

| 기능 | 목적 | 저장 위치 | 수명 |
| --- | --- | --- | --- |
| 메모리 | 다음 요청에서도 재사용할 사실과 선호 보존 | `.memory/*.md` | 장기 |
| 컨텍스트 압축 | 현재 대화가 너무 길 때 이어가기 위한 요약 생성 | `.transcripts/`, 현재 메시지 배열 | 세션 중심 |

예를 들어 "나는 작은 diff를 선호해"는 장기 메모리에 적합하다. 반면 "방금 읽은
파일에서 A 함수가 B를 호출한다"처럼 현재 작업 흐름을 이어가기 위한 정보는 압축
요약에 더 적합하다.

## 실행 방법

루트 디렉터리에서 챕터 runner를 사용한다.

```bash
uv run python scripts/run_chapter.py s09_memory
```

실행 후 사용자가 명확한 선호나 프로젝트 사실을 말하면, 최종 응답 뒤 자동 추출이
시도된다.

```text
>> remember that I prefer small, focused patches
```

성공하면 `.memory/` 아래에 개별 메모리 파일과 `MEMORY.md` 색인이 생성된다.

## 현재 구현의 한계

이 챕터는 학습용 구현이므로 몇 가지 제한이 있다.

- `memory_func.py`를 import하는 순간 `.memory/` 디렉터리가 생성된다.
- 메모리 추출과 통합은 모델 출력 JSON에 의존한다.
- 추출, 선택, 통합 중 예외가 발생하면 대부분 조용히 무시된다.
- 통합 단계는 기존 개별 메모리 파일을 삭제한 뒤 새 파일을 쓰므로, 중간 실패에 대한
  원자적 백업 절차는 없다.
- `read_memory_file()`은 파일명이 `.memory/` 밖으로 나가지 못하게 별도 검증하지 않는다.
  현재는 내부 선택 로직에서 나온 파일명을 쓰는 구조다.
- `MEMORY_TYPES`는 정의되어 있지만 입력 검증에는 아직 사용되지 않는다.
- 메모리를 수동으로 추가, 삭제, 검색하는 전용 도구는 아직 노출되어 있지 않다.

## 개선 아이디어

완성도를 높이려면 다음 보강이 유용하다.

- `tests/test_s09_memory.py`를 추가해 저장, 색인, 관련도 선택 fallback, 주입 포맷을 검증한다.
- 통합 전에 백업 파일을 만들거나 임시 디렉터리에 먼저 쓴 뒤 교체한다.
- 메모리 파일명 검증을 추가해 path traversal 가능성을 막는다.
- `MEMORY_TYPES`를 실제 validation에 사용한다.
- README 예시와 실제 저장 경로를 계속 `.memory/` 기준으로 맞춘다.
- 필요하면 `list_memory`, `read_memory`, `forget_memory` 같은 명시적 도구를 추가한다.
