"""Lifecycle hooks for ClaimCheck."""

from __future__ import annotations

from typing import Any

from .core import (
    ClaimCheckState,
    NUDGE_TEXT,
    session_key_from_kwargs,
)


class _HookContext:
    def __init__(self) -> None:
        self.ctx: Any = None
        self.state: ClaimCheckState | None = None


_REGISTRY = _HookContext()


def configure(ctx: Any, state: ClaimCheckState) -> None:
    _REGISTRY.ctx = ctx
    _REGISTRY.state = state


def on_pre_tool_call(tool_name: str, args: dict, task_id: str, **kwargs: Any):
    state = _REGISTRY.state
    if state is None:
        return None
    session_id = session_key_from_kwargs(kwargs) or str(task_id or "default")
    return state.pre_tool_call_block(tool_name, session_id)


def on_post_tool_call(
    tool_name: str,
    args: dict,
    result: str,
    task_id: str,
    **kwargs: Any,
):
    state = _REGISTRY.state
    if state is None:
        return None
    session_id = session_key_from_kwargs(kwargs) or str(task_id or "default")
    if tool_name == "record_observation":
        state.mark_observation_fresh(session_id)
    return None


def on_post_llm_call(
    session_id: str,
    user_message: str,
    assistant_response: str,
    conversation_history: list,
    model: str,
    platform: str,
    **kwargs: Any,
):
    state = _REGISTRY.state
    if state is None:
        return None
    sid = session_key_from_kwargs(kwargs) or str(session_id or "default")
    if not state.should_nudge(sid, assistant_response or ""):
        return None
    ctx = _REGISTRY.ctx
    if ctx is None:
        return None
    inject = getattr(ctx, "inject_message", None)
    if not callable(inject):
        return None
    try:
        inject(NUDGE_TEXT)
    except Exception:
        return None
    return None


def on_pre_llm_call_turn_start(session_id: str, **kwargs: Any):
    """Clear per-turn observation freshness at the start of each model turn."""
    state = _REGISTRY.state
    if state is None:
        return None
    sid = session_key_from_kwargs(kwargs) or str(session_id or "default")
    state.clear_turn_observation_fresh(sid)
    return None
