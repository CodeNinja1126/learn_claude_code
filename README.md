# learn_claude_code

Local learning workspace for rebuilding the `learn-claude-code` harness pattern
with an OpenAI-compatible Qwen endpoint.

## Layout

```text
src/util/             reusable client, loop, message, and tool modules
chapters/            s01-s20 learning track adapted for Qwen
examples/            small runnable experiments
prompts/             reusable system/tool prompt text
skills/              placeholder for the skill-loading chapter
memory/              project and session memory experiments
scripts/             chapter runner and smoke checks
tests/               lightweight regression tests
```

## Configuration

Configuration is loaded from shell environment variables first, then from a
local `.env`, then from `.env.example`:

```bash
OPENAI_BASE_URL=http://localhost:10531/v1
OPENAI_API_KEY=gpt-local
QWEN_MODEL=gpt-5.5
```

Create `.env` when you want local overrides without editing `.env.example`.

For the `openai-oauth` local proxy, start the proxy before running a chapter:

```bash
npm run openai-oauth
```

The script sets `NODE_OPTIONS=--experimental-global-webcrypto`, which is needed
on Node 18 for the current `openai-oauth` package. Node 20+ is recommended by
the package.

## Run

```bash
uv run python examples/local_qwen_smoke.py
uv run python scripts/run_chapter.py s01_agent_loop
uv run pytest
```
