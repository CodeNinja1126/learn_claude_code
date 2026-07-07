# qwen-test

Local learning workspace for rebuilding the `learn-claude-code` harness pattern
with an OpenAI-compatible Qwen endpoint.

## Layout

```text
src/utill/            reusable client, loop, message, and tool modules
chapters/            s01-s20 learning track adapted for Qwen
examples/            small runnable experiments
prompts/             reusable system/tool prompt text
skills/              placeholder for the skill-loading chapter
memory/              project and session memory experiments
scripts/             chapter runner and smoke checks
tests/               lightweight regression tests
```

## Configuration

Copy `.env.example` values into your shell or a local `.env` loader if you use
one:

```bash
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_API_KEY=qwen-local
export QWEN_MODEL=qwen3.6
```

## Run

```bash
uv run python examples/local_qwen_smoke.py
uv run python scripts/run_chapter.py s01_agent_loop
uv run pytest
```
