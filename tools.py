"""Hermes tool handlers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .core import ClaimCheckState, session_key_from_kwargs

if TYPE_CHECKING:
    pass

_STATE: ClaimCheckState | None = None


def configure(state: ClaimCheckState) -> None:
    global _STATE
    _STATE = state


def _require_state() -> ClaimCheckState:
    if _STATE is None:
        raise RuntimeError("ClaimCheck not configured; register() was not called")
    return _STATE


def record_observation(args: dict[str, Any], **kwargs: Any) -> str:
    state = _require_state()
    session_id = session_key_from_kwargs(kwargs)
    target_ref = (args.get("target_ref") or "").strip()
    measured_property = (args.get("measured_property") or "").strip()
    how_checked = (args.get("how_checked") or "").strip()
    if not target_ref or not measured_property or not how_checked:
        return json.dumps(
            {"error": "target_ref, measured_property, and how_checked are required"}
        )
    turn_hint = args.get("turn_hint")
    if turn_hint is not None:
        turn_hint = str(turn_hint).strip() or None
    obs = state.record_observation(
        session_id=session_id,
        target_ref=target_ref,
        measured_property=measured_property,
        how_checked=how_checked,
        turn_hint=turn_hint,
    )
    return json.dumps(
        {
            "ok": True,
            "observation": obs.to_dict(),
            "receipt_path": str(state.store.path),
        }
    )


def list_observations(args: dict[str, Any], **kwargs: Any) -> str:
    state = _require_state()
    session_id = session_key_from_kwargs(kwargs)
    all_sessions = bool(args.get("all_sessions"))
    limit = args.get("limit", 20)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 20
    if limit <= 0:
        limit = 20
    rows = state.store.list_observations(
        session_id=None if all_sessions else session_id,
        limit=limit,
    )
    return json.dumps(
        {
            "ok": True,
            "count": len(rows),
            "observations": rows,
            "receipt_path": str(state.store.path),
        }
    )


def export_receipt(args: dict[str, Any], **kwargs: Any) -> str:
    state = _require_state()
    dest = (args.get("dest_path") or "").strip()
    if not dest:
        return json.dumps({"error": "dest_path is required"})
    dest_path = Path(dest).expanduser()
    try:
        count = state.store.export_to(dest_path)
    except OSError as exc:
        return json.dumps({"error": f"export failed: {exc}"})
    return json.dumps(
        {
            "ok": True,
            "dest_path": str(dest_path),
            "rows_exported": count,
            "source_path": str(state.store.path),
        }
    )


def approve_risky(args: dict[str, Any], **kwargs: Any) -> str:
    state = _require_state()
    session_id = session_key_from_kwargs(kwargs)
    reason = (args.get("reason") or "").strip()
    state.approve_risky(session_id)
    return json.dumps(
        {
            "ok": True,
            "session_id": session_id,
            "risky_tools_allowed": True,
            "reason": reason or None,
        }
    )
