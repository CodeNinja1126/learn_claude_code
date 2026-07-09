from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import os
import random
import time

from util.config import _project_env


_FILE_ENV = _project_env()


def _setting(name: str, fallback: str = "") -> str:
    return os.getenv(name) or _FILE_ENV.get(name) or fallback


DEFAULT_MAX_TOKENS = int(_setting("ERROR_RECOVERY_DEFAULT_MAX_TOKENS", "8000"))
ESCALATED_MAX_TOKENS = int(_setting("ERROR_RECOVERY_ESCALATED_MAX_TOKENS", "64000"))
MAX_TRANSIENT_RETRIES = int(_setting("ERROR_RECOVERY_MAX_RETRIES", "10"))
BASE_DELAY_MS = int(_setting("ERROR_RECOVERY_BASE_DELAY_MS", "500"))
MAX_CONSECUTIVE_529 = int(_setting("ERROR_RECOVERY_MAX_CONSECUTIVE_529", "3"))
MAX_CONTINUATIONS = int(_setting("ERROR_RECOVERY_MAX_CONTINUATIONS", "3"))
CONTINUATION_PROMPT = (
    "Output token limit hit. Resume directly. "
    "Do not apologize or recap; continue from the exact stopping point."
)

CONTEXT_ERROR_MARKERS = (
    "prompt_too_long",
    "prompt is too long",
    "too many tokens",
    "context_length_exceeded",
    "maximum context length",
    "max_context_window",
)


def _fallback_model() -> str | None:
    return _setting("FALLBACK_QWEN_MODEL") or _setting("FALLBACK_MODEL_ID") or None


@dataclass
class RecoveryState:
    primary_model: str
    current_model: str = field(init=False)
    max_tokens: int = DEFAULT_MAX_TOKENS
    has_escalated_tokens: bool = False
    continuation_count: int = 0
    has_reactive_compacted: bool = False
    consecutive_529: int = 0
    fallback_model: str | None = field(default_factory=_fallback_model)

    def __post_init__(self) -> None:
        self.current_model = self.primary_model

    def escalate_tokens_once(self) -> tuple[int, int] | None:
        if self.has_escalated_tokens:
            return None
        previous = self.max_tokens
        self.max_tokens = ESCALATED_MAX_TOKENS
        self.has_escalated_tokens = True
        return previous, self.max_tokens

    def next_continuation(self) -> tuple[str, int, int] | None:
        if self.continuation_count >= MAX_CONTINUATIONS:
            return None
        self.continuation_count += 1
        return CONTINUATION_PROMPT, self.continuation_count, MAX_CONTINUATIONS

    def mark_reactive_compacted(self) -> None:
        self.has_reactive_compacted = True


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _retry_after(exc: Exception) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", {}) or {}
    value = headers.get("retry-after") if hasattr(headers, "get") else None
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def retry_delay(attempt: int, retry_after: float | None = None) -> float:
    if retry_after is not None:
        return retry_after
    base = min(BASE_DELAY_MS * (2**attempt), 32000) / 1000
    return base + random.uniform(0, base * 0.25)


def is_rate_limit_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return _status_code(exc) == 429 or "ratelimit" in name or "rate limit" in message


def is_overloaded_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return _status_code(exc) == 529 or "overloaded" in name or "overloaded" in message


def is_context_limit_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in CONTEXT_ERROR_MARKERS)


def _maybe_switch_to_fallback(state: RecoveryState) -> None:
    if state.fallback_model and state.fallback_model != state.current_model:
        state.current_model = state.fallback_model
        print(f"  \033[31m[529 fallback] switching to {state.current_model}\033[0m")
    elif state.fallback_model:
        print(f"  \033[31m[529 fallback] {state.current_model} is already active\033[0m")
    else:
        print("  \033[31m[529 fallback] no fallback model configured\033[0m")
    state.consecutive_529 = 0


def call_with_retries(
    request: Callable[[str, int], Any],
    state: RecoveryState,
) -> Any:
    for attempt in range(MAX_TRANSIENT_RETRIES):
        try:
            response = request(state.current_model, state.max_tokens)
            state.consecutive_529 = 0
            return response
        except Exception as exc:
            if is_rate_limit_error(exc):
                delay = retry_delay(attempt, _retry_after(exc))
                print(
                    f"  \033[33m[429 rate limit] retry {attempt + 1}/"
                    f"{MAX_TRANSIENT_RETRIES}, wait {delay:.1f}s\033[0m"
                )
                time.sleep(delay)
                continue

            if is_overloaded_error(exc):
                state.consecutive_529 += 1
                if state.consecutive_529 >= MAX_CONSECUTIVE_529:
                    _maybe_switch_to_fallback(state)
                delay = retry_delay(attempt, _retry_after(exc))
                print(
                    f"  \033[33m[529 overloaded] retry {attempt + 1}/"
                    f"{MAX_TRANSIENT_RETRIES}, wait {delay:.1f}s\033[0m"
                )
                time.sleep(delay)
                continue

            raise
    raise RuntimeError(f"Max transient retries exceeded ({MAX_TRANSIENT_RETRIES})")


def completion_hit_token_limit(response: Any) -> bool:
    reason = str(getattr(response, "stop_reason", "") or "").lower()
    choices = getattr(response, "choices", []) or []
    if choices:
        reason = str(getattr(choices[0], "finish_reason", reason) or reason).lower()
    return reason in {"length", "max_tokens"} or "max_tokens" in reason
