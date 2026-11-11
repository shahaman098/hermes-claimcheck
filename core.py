"""Pure ClaimCheck logic (no Hermes imports)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

COMPLETION_PATTERN = re.compile(
    r"\b(?:"
    r"done|complete(?:d|ly)?|shipped|fixed|working|ready|passing|live"
    r")\b",
    re.IGNORECASE,
)

RISKY_TOOLS = frozenset(
    {
        "shell_exec",
        "write_file",
        "edit_file",
        "delete_file",
    }
)

CLAIMCHECK_TOOLS = frozenset(
    {
        "record_observation",
        "list_observations",
        "export_receipt",
        "approve_risky",
    }
)

NUDGE_TEXT = (
    "[ClaimCheck] Your reply uses completion language before a fresh "
    "record_observation in this turn. Call record_observation with the "
    "path or ref, the measured property, and how you verified it, then "
    "summarize only what the receipt supports."
)


def contains_completion_claim(text: str) -> bool:
    if not text:
        return False
    return COMPLETION_PATTERN.search(text) is not None


def is_risky_tool(tool_name: str) -> bool:
    return tool_name in RISKY_TOOLS


def session_key_from_kwargs(kwargs: dict[str, Any]) -> str:
    for key in ("conversation_id", "session_id", "task_id"):
        value = kwargs.get(key)
        if value:
            return str(value)
    return "default"


@dataclass
class SessionFlags:
    risky_approved: bool = False
    observation_fresh: bool = False


@dataclass
class Observation:
    session_id: str
    target_ref: str
    measured_property: str
    how_checked: str
    recorded_at: float
    turn_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        row = {
            "session_id": self.session_id,
            "target_ref": self.target_ref,
            "measured_property": self.measured_property,
            "how_checked": self.how_checked,
            "recorded_at": self.recorded_at,
        }
        if self.turn_hint:
            row["turn_hint"] = self.turn_hint
        return row

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        return cls(
            session_id=str(data.get("session_id", "")),
            target_ref=str(data.get("target_ref", "")),
            measured_property=str(data.get("measured_property", "")),
            how_checked=str(data.get("how_checked", "")),
            recorded_at=float(data.get("recorded_at", 0.0)),
            turn_hint=data.get("turn_hint"),
        )


class ReceiptStore:
    """Append-only JSONL observation log."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, observation: Observation) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(observation.to_dict(), ensure_ascii=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def iter_rows(self) -> Iterator[dict[str, Any]]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    continue

    def list_observations(
        self, *, session_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in self.iter_rows():
            if session_id and row.get("session_id") != session_id:
                continue
            rows.append(row)
        if limit > 0 and len(rows) > limit:
            rows = rows[-limit:]
        return rows

    def export_to(self, dest: Path) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with dest.open("w", encoding="utf-8") as out:
            for row in self.iter_rows():
                out.write(json.dumps(row, ensure_ascii=True) + "\n")
                count += 1
        return count


@dataclass
class ClaimCheckState:
    store: ReceiptStore
    sessions: dict[str, SessionFlags] = field(default_factory=dict)

    def flags(self, session_id: str) -> SessionFlags:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionFlags()
        return self.sessions[session_id]

    def mark_observation_fresh(self, session_id: str) -> None:
        flags = self.flags(session_id)
        flags.observation_fresh = True

    def clear_turn_observation_fresh(self, session_id: str) -> None:
        flags = self.flags(session_id)
        flags.observation_fresh = False

    def approve_risky(self, session_id: str) -> None:
        self.flags(session_id).risky_approved = True

    def risky_allowed(self, session_id: str) -> bool:
        return self.flags(session_id).risky_approved

    def record_observation(
        self,
        *,
        session_id: str,
        target_ref: str,
        measured_property: str,
        how_checked: str,
        turn_hint: str | None = None,
    ) -> Observation:
        obs = Observation(
            session_id=session_id,
            target_ref=target_ref.strip(),
            measured_property=measured_property.strip(),
            how_checked=how_checked.strip(),
            recorded_at=time.time(),
            turn_hint=turn_hint,
        )
        self.store.append(obs)
        self.mark_observation_fresh(session_id)
        return obs

    def should_nudge(self, session_id: str, assistant_text: str) -> bool:
        if not contains_completion_claim(assistant_text):
            return False
        return not self.flags(session_id).observation_fresh

    def pre_tool_call_block(
        self, tool_name: str, session_id: str
    ) -> dict[str, str] | None:
        if tool_name in CLAIMCHECK_TOOLS:
            return None
        if not is_risky_tool(tool_name):
            return None
        if self.risky_allowed(session_id):
            return None
        return {
            "action": "block",
            "message": (
                f"[ClaimCheck] Blocked risky tool `{tool_name}` until you call "
                "approve_risky once this session (after explaining the risk), "
                "or choose a read-only path."
            ),
        }
