import json
import time
from typing import Any

from util import WORKDIR
from util.client import create_client
from util.config import load_config


def estimate_size(msgs):
    """Rough size estimation (characters). Use as a heuristic."""
    return len(str(msgs))

def L3_L1_L2_compact(messages, allow_lossy=False):
    messages[:] = tool_result_budget(messages)
    messages[:] = micro_compact(messages)
    if allow_lossy:
        messages[:] = snip_compact(messages, 100)
    return messages

# L1
def _message_has_tool_use(message: Any) -> bool:
    if isinstance(message, dict):
        return bool(message.get("tool_calls"))
    return bool(getattr(message, "tool_calls", None))


def _is_tool_result_message(message: Any) -> bool:
    if isinstance(message, dict):
        return message.get("role") == "tool"
    return getattr(message, "role", None) == "tool"


def _message_content(message: Any) -> Any:
    if isinstance(message, dict):
        return message.get("content", "")
    return getattr(message, "content", "")


def _set_message_content(message: Any, content: str) -> None:
    if isinstance(message, dict):
        message["content"] = content
    else:
        message.content = content


def _preserve_tool_exchange_end(messages, end):
    while end < len(messages) and _is_tool_result_message(messages[end]):
        end += 1
    return end


def _preserve_tool_exchange_start(messages, start):
    if not (0 < start < len(messages)):
        return start
    if not _is_tool_result_message(messages[start]):
        return start

    while start > 0 and _is_tool_result_message(messages[start - 1]):
        start -= 1
    if start > 0 and _message_has_tool_use(messages[start - 1]):
        start -= 1
    return start


def _logical_message_starts(messages):
    starts = []
    i = 0
    while i < len(messages):
        starts.append(i)
        i += 1
        if _is_tool_result_message(messages[i - 1]):
            while i < len(messages) and _is_tool_result_message(messages[i]):
                i += 1
    return starts


def _logical_message_count(messages, start=0, end=None):
    end = len(messages) if end is None else end
    count = 0
    i = start
    while i < end:
        count += 1
        i += 1
        if _is_tool_result_message(messages[i - 1]):
            while i < end and _is_tool_result_message(messages[i]):
                i += 1
    return count


def snip_compact(messages, max_messages=50):
    logical_starts = _logical_message_starts(messages)
    if len(logical_starts) <= max_messages:
        return messages
    head_messages = 3
    tail_messages = max_messages - head_messages
    head_end = logical_starts[head_messages]
    tail_start = logical_starts[len(logical_starts) - tail_messages]
    head_end = _preserve_tool_exchange_end(messages, head_end)
    tail_start = _preserve_tool_exchange_start(messages, tail_start)
    if head_end >= tail_start:
        return messages
    snipped = _logical_message_count(messages, head_end, tail_start)
    placeholder = {
        "role": "user",
        "content": f"[snipped {snipped} messages from conversation middle]",
    }
    return messages[:head_end] + [placeholder] + messages[tail_start:]


# L2
def collect_tool_results(messages):
    blocks = []
    for mi, msg in enumerate(messages):
        if not _is_tool_result_message(msg):
            continue
        blocks.append((mi, msg))
    return blocks


KEEP_RECENT_TOOL_RESULTS = 20
MICRO_COMPACT_THRESHOLD = 640_000


def micro_compact(messages):
    tool_results = collect_tool_results(messages)
    if len(tool_results) <= KEEP_RECENT_TOOL_RESULTS:
        return messages
    for _, block in tool_results[:-KEEP_RECENT_TOOL_RESULTS]:
        if len(str(_message_content(block))) > MICRO_COMPACT_THRESHOLD:
            _set_message_content(
                block,
                "[Earlier tool result compacted. Re-run if needed.]",
            )
    return messages


# L3
TOOL_RESULTS_DIR = WORKDIR / ".task_outputs" / "tool-results"
PERSIST_THRESHOLD = 640_000


def persist_large_output(tool_call_id, output):
    if len(output) <= PERSIST_THRESHOLD:
        return output
    TOOL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TOOL_RESULTS_DIR / f"{tool_call_id}.txt"
    # Always overwrite to ensure we capture the latest large output (e.g. from retries)
    path.write_text(output)
    return f"<persisted-output>\nFull output: {path}\nPreview:\n{output[:2000]}\n</persisted-output>"


def tool_result_budget(messages, max_bytes=200_000):
    last = messages[-1] if messages else None
    if not isinstance(last, dict) or last.get("role") != "tool":
        return messages

    start = len(messages) - 1
    while start > 0:
        previous = messages[start - 1]
        if not isinstance(previous, dict) or previous.get("role") != "tool":
            break
        start -= 1

    blocks = [
        (i, msg)
        for i, msg in enumerate(messages[start:], start=start)
        if isinstance(msg, dict)
    ]
    total = sum(len(str(msg.get("content", ""))) for _, msg in blocks)
    if total <= max_bytes:
        return messages
    ranked = sorted(
        blocks, key=lambda p: len(str(p[1].get("content", ""))), reverse=True
    )
    for _, msg in ranked:
        if total <= max_bytes:
            break
        content = str(msg.get("content", ""))
        if len(content) <= PERSIST_THRESHOLD:
            continue
        tool_call_id = msg.get("tool_call_id", "unknown")
        msg["content"] = persist_large_output(tool_call_id, content)
        total = sum(len(str(msg.get("content", ""))) for _, msg in blocks)
    return messages


# L4
TRANSCRIPT_DIR = WORKDIR / ".transcripts"

def write_transcript(messages):
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    # Use time_ns() to prevent filename collisions in rapid succession
    path = TRANSCRIPT_DIR / f"transcript_{time.time_ns()}.jsonl"
    with path.open("w") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")
    return path


def summarize_history(messages):
    conversation = json.dumps(messages, default=str)[:80000]
    prompt = (
        "Summarize this coding-agent conversation so work can continue.\n"
        "Preserve: 1. current goal, 2. key findings/decisions, 3. files read/changed, "
        "4. remaining work, 5. user constraints.\nBe compact but concrete.\n\n"
        + conversation
    )
    config = load_config()
    client = create_client(config)

    response = client.chat.completions.create(
        model=config.model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
    )
    return response.choices[0].message.content or "(empty summary)"


def compact_history(messages):
    transcript_path = write_transcript(messages)
    print(f"[transcript saved: {transcript_path}]")
    summary = summarize_history(messages)
    return [{"role": "user", "content": f"[Compacted]\n\n{summary}"}]


# Emergency: reactiveCompact — on API error
def reactive_compact(messages):
    write_transcript(messages)
    tail_start = max(0, len(messages) - 5)
    tail_start = _preserve_tool_exchange_start(messages, tail_start)
    if tail_start == 0:
        summary = summarize_history(messages)
        return [{"role": "user", "content": f"[Reactive compact]\n\n{summary}"}]

    summary = summarize_history(messages[:tail_start])
    return [
        {"role": "user", "content": f"[Reactive compact]\n\n{summary}"},
        *messages[tail_start:],
    ]
