"""Pure ClaimCheck logic: Double-Entry Verification Interlock Kernel (no Hermes imports)."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

COMPLETION_PATTERN = re.compile(
    r"\b(?:"
    r"done|complete(?:d|ly)?|shipped|fixed|working|ready|passing|live|verified|resolved"
    r")\b",
    re.IGNORECASE,
)

RISKY_TOOLS = frozenset(
    {
        "shell_exec",
        "terminal",
        "write_file",
        "edit_file",
        "patch",
        "delete_file",
    }
)

MUTATION_TOOLS = frozenset(
    {
        "write_file",
        "edit_file",
        "patch",
        "delete_file",
    }
)

CLAIMCHECK_TOOLS = frozenset(
    {
        "record_observation",
        "list_observations",
        "export_receipt",
        "approve_risky",
        "claimcheck_status",
    }
)

TEST_COMMAND_PATTERNS = [
    re.compile(r"\bpytest\b", re.IGNORECASE),
    re.compile(r"\bpython3?\s+-m\s+unittest\b", re.IGNORECASE),
    re.compile(r"\bcargo\s+test\b", re.IGNORECASE),
    re.compile(r"\bnpm\s+(?:run\s+)?test\b", re.IGNORECASE),
    re.compile(r"\bnpx\s+(?:jest|vitest)\b", re.IGNORECASE),
    re.compile(r"\bgo\s+test\b", re.IGNORECASE),
    re.compile(r"\bpython3?\s+test_\w+\.py\b", re.IGNORECASE),
    re.compile(r"\bcurl\s+.*http", re.IGNORECASE),
]

FAILURE_INDICATORS = [
    re.compile(r"\bFAIL(?:ED|URES?)?\b", re.IGNORECASE),
    re.compile(r"\bTraceback\s+\(most\s+recent\s+call\s+last\):", re.IGNORECASE),
    re.compile(r"\bSyntaxError:", re.IGNORECASE),
    re.compile(r"\bERRORS?:\b", re.IGNORECASE),
    re.compile(r"\bcommand\s+failed\b", re.IGNORECASE),
    re.compile(r"Exit\s+code:\s*[1-9]", re.IGNORECASE),
]

SUCCESS_INDICATORS = [
    re.compile(r"\b(?:passed|ok)\b", re.IGNORECASE),
    re.compile(r"\bRan\s+\d+\s+tests?\s+in\s+[\d\.]+s\s+OK\b", re.IGNORECASE),
    re.compile(r"\btest\s+result:\s+ok\b", re.IGNORECASE),
    re.compile(r"\bHTTP/\d(?:\.\d)?\s+200\b", re.IGNORECASE),
]

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


def is_mutation_tool(tool_name: str) -> bool:
    return tool_name in MUTATION_TOOLS


def session_key_from_kwargs(kwargs: dict[str, Any]) -> str:
    for key in ("conversation_id", "session_id", "task_id"):
        value = kwargs.get(key)
        if value:
            return str(value)
    return "default"


@dataclass
class Mutation:
    """An unbalanced reality mutation (debit)."""
    target_path: str
    tool_name: str
    timestamp: float
    turn_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_path": self.target_path,
            "tool_name": self.tool_name,
            "timestamp": self.timestamp,
            "turn_hint": self.turn_hint,
        }


@dataclass
class Observation:
    """An empirical verification credit with cryptographic attestation."""
    session_id: str
    target_ref: str
    measured_property: str
    how_checked: str
    recorded_at: float
    turn_hint: str | None = None
    stdout_digest: str | None = None
    receipt_hash: str = ""
    is_automatic: bool = False

    def __post_init__(self) -> None:
        if not self.receipt_hash:
            payload = (
                f"{self.session_id}:{self.target_ref}:{self.measured_property}:"
                f"{self.how_checked}:{self.stdout_digest or ''}:{self.recorded_at}"
            )
            self.receipt_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        row = {
            "session_id": self.session_id,
            "target_ref": self.target_ref,
            "measured_property": self.measured_property,
            "how_checked": self.how_checked,
            "recorded_at": self.recorded_at,
            "receipt_hash": self.receipt_hash,
            "is_automatic": self.is_automatic,
        }
        if self.turn_hint:
            row["turn_hint"] = self.turn_hint
        if self.stdout_digest:
            row["stdout_digest"] = self.stdout_digest
        return row

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Observation:
        obs = cls(
            session_id=str(data.get("session_id", "")),
            target_ref=str(data.get("target_ref", "")),
            measured_property=str(data.get("measured_property", "")),
            how_checked=str(data.get("how_checked", "")),
            recorded_at=float(data.get("recorded_at", 0.0)),
            turn_hint=data.get("turn_hint"),
            stdout_digest=data.get("stdout_digest"),
            receipt_hash=str(data.get("receipt_hash", "")),
            is_automatic=bool(data.get("is_automatic", False)),
        )
        return obs


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
class SessionLedger:
    """Session state for the Double-Entry Reconciliation Ledger."""
    risky_approved: bool = False
    observation_fresh: bool = False
    mutations: list[Mutation] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)

    @property
    def has_unverified_mutations(self) -> bool:
        if not self.mutations:
            return False
        # If there are mutations but zero observations since the first mutation
        if not self.observations:
            return True
        latest_obs_time = max(o.recorded_at for o in self.observations)
        latest_mut_time = max(m.timestamp for m in self.mutations)
        # Unverified if any mutation happened after the latest observation
        return latest_mut_time > latest_obs_time

    def unverified_paths(self) -> list[str]:
        if not self.mutations:
            return []
        if not self.observations:
            return list(dict.fromkeys(m.target_path for m in self.mutations))
        latest_obs_time = max(o.recorded_at for o in self.observations)
        pending: list[str] = []
        for m in self.mutations:
            if m.timestamp > latest_obs_time:
                pending.append(m.target_path)
        return list(dict.fromkeys(pending))


@dataclass
class ClaimCheckState:
    store: ReceiptStore
    ledgers: dict[str, SessionLedger] = field(default_factory=dict)

    def ledger(self, session_id: str) -> SessionLedger:
        if session_id not in self.ledgers:
            self.ledgers[session_id] = SessionLedger()
        return self.ledgers[session_id]

    def mark_observation_fresh(self, session_id: str) -> None:
        self.ledger(session_id).observation_fresh = True

    def clear_turn_observation_fresh(self, session_id: str) -> None:
        self.ledger(session_id).observation_fresh = False

    def approve_risky(self, session_id: str) -> None:
        self.ledger(session_id).risky_approved = True

    def risky_allowed(self, session_id: str) -> bool:
        return self.ledger(session_id).risky_approved

    def record_mutation(
        self,
        session_id: str,
        target_path: str,
        tool_name: str,
        turn_hint: str | None = None,
    ) -> Mutation:
        """Register a mutation debit in the double-entry ledger."""
        mut = Mutation(
            target_path=target_path.strip(),
            tool_name=tool_name,
            timestamp=time.time(),
            turn_hint=turn_hint,
        )
        ledger = self.ledger(session_id)
        ledger.mutations.append(mut)
        ledger.observation_fresh = False
        return mut

    def record_observation(
        self,
        *,
        session_id: str,
        target_ref: str,
        measured_property: str,
        how_checked: str,
        turn_hint: str | None = None,
        stdout_digest: str | None = None,
        is_automatic: bool = False,
    ) -> Observation:
        """Register an empirical observation credit in the double-entry ledger."""
        obs = Observation(
            session_id=session_id,
            target_ref=target_ref.strip(),
            measured_property=measured_property.strip(),
            how_checked=how_checked.strip(),
            recorded_at=time.time(),
            turn_hint=turn_hint,
            stdout_digest=stdout_digest,
            is_automatic=is_automatic,
        )
        self.store.append(obs)
        ledger = self.ledger(session_id)
        ledger.observations.append(obs)
        self.mark_observation_fresh(session_id)
        return obs

    def is_balanced(self, session_id: str, changed_paths: list[str] | None = None) -> bool:
        """Return True if the double-entry reconciliation ledger has zero deficit."""
        ledger = self.ledger(session_id)
        # If external changed_paths are reported by Hermes and unrecorded, register them
        if changed_paths:
            for path in changed_paths:
                if not any(m.target_path == path for m in ledger.mutations):
                    self.record_mutation(session_id, path, tool_name="hermes_turn_edit")

        return not ledger.has_unverified_mutations

    def try_auto_ingest_tool_result(
        self,
        session_id: str,
        tool_name: str,
        args: dict[str, Any],
        result: str,
    ) -> Observation | None:
        """Sniff shell/terminal tool execution to automatically capture empirical proof."""
        if tool_name not in ("shell_exec", "terminal"):
            return None

        cmd = str(args.get("command") or args.get("cmd") or "").strip()
        if not cmd:
            return None

        # Check if command matches any known test/verification runner
        is_test_command = any(pat.search(cmd) for pat in TEST_COMMAND_PATTERNS)
        if not is_test_command:
            return None

        # Check if result contains clear failure indicators
        has_failure = any(pat.search(result) for pat in FAILURE_INDICATORS)
        if has_failure:
            return None

        # Check if result contains clear success indicators
        has_success = any(pat.search(result) for pat in SUCCESS_INDICATORS)
        # If exit_code 0 is explicitly reported in result
        exit_code_zero = "exit code: 0" in result.lower() or "exit code 0" in result.lower()

        if not (has_success or exit_code_zero):
            return None

        # Empirical proof verified!
        stdout_hash = hashlib.sha256(result.encode("utf-8")).hexdigest()[:16]
        measured_prop = "Tests passed (Exit Code 0)"
        obs = self.record_observation(
            session_id=session_id,
            target_ref=cmd.split()[0] if cmd else "test",
            measured_property=measured_prop,
            how_checked=cmd,
            stdout_digest=stdout_hash,
            is_automatic=True,
            turn_hint="auto-captured",
        )
        return obs

    def pre_verify_interlock(
        self,
        session_id: str,
        changed_paths: list[str] | None = None,
        attempt: int = 0,
    ) -> dict[str, str] | None:
        """Poka-Yoke interlock hook for Hermes pre_verify."""
        # Auto-register any paths modified during the turn
        if changed_paths:
            for p in changed_paths:
                if not any(m.target_path == p for m in self.ledger(session_id).mutations):
                    self.record_mutation(session_id, p, tool_name="turn_edit")

        ledger = self.ledger(session_id)
        if not ledger.has_unverified_mutations:
            return None

        unverified = ledger.unverified_paths() or (changed_paths or ["unverified files"])
        summary_paths = ", ".join(unverified[:3])
        if len(unverified) > 3:
            summary_paths += f" (+{len(unverified) - 3} more)"

        return {
            "action": "continue",
            "message": (
                f"⛔ [ClaimCheck Interlock Veto]\n"
                f"Reconciliation Deficit: Unverified mutations detected on: {summary_paths}.\n"
                f"You modified files without recording an empirical verification receipt.\n"
                f"Run the matching test suite (e.g. `pytest`, `cargo test`, `npm test`) or "
                f"call `record_observation` with the measured property before declaring completion."
            ),
        }

    def should_nudge(self, session_id: str, assistant_text: str) -> bool:
        if not contains_completion_claim(assistant_text):
            return False
        return not self.ledger(session_id).observation_fresh

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

    def generate_attestation_voucher(self, session_id: str) -> dict[str, Any] | None:
        ledger = self.ledger(session_id)
        if not ledger.observations:
            return None
        latest = ledger.observations[-1]
        parity = "BALANCED" if not ledger.has_unverified_mutations else "DEFICIT"
        voucher = {
            "attestation": latest.receipt_hash,
            "session_id": session_id,
            "parity": parity,
            "target": latest.target_ref,
            "evidence": f"{latest.how_checked} ({latest.measured_property})",
            "stdout_digest": latest.stdout_digest or "n/a",
            "timestamp": latest.recorded_at,
        }
        return voucher

    def format_ascii_certificate(self, session_id: str) -> str:
        voucher = self.generate_attestation_voucher(session_id)
        if not voucher:
            return "[ClaimCheck] No verification receipts logged in this session."
        cert = (
            "┌────────────────────────────────────────────────────────────────────────┐\n"
            "│  🛡️  CLAIMCHECK BALANCED RECONCILIATION VOUCHER                         │\n"
            f"│  Status: {voucher['parity']:<60} │\n"
            f"│  Target: {voucher['target'][:58]:<60} │\n"
            f"│  Evidence: {voucher['evidence'][:56]:<58} │\n"
            f"│  Attestation: sha256:{voucher['attestation'][:48]:<49} │\n"
            "└────────────────────────────────────────────────────────────────────────┘"
        )
        return cert
