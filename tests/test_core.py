"""Unit tests for ClaimCheck core logic (no Hermes)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import (
    ClaimCheckState,
    ReceiptStore,
    contains_completion_claim,
    is_risky_tool,
)


class CompletionClaimTests(unittest.TestCase):
    def test_detects_completion_words(self) -> None:
        self.assertTrue(contains_completion_claim("The fix is done."))
        self.assertTrue(contains_completion_claim("Shipped to prod"))
        self.assertFalse(contains_completion_claim("Still investigating"))

    def test_risky_tool_set(self) -> None:
        self.assertTrue(is_risky_tool("shell_exec"))
        self.assertFalse(is_risky_tool("read_file"))


class ReceiptStoreTests(unittest.TestCase):
    def test_append_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"
            store = ReceiptStore(path)
            state = ClaimCheckState(store=store)
            state.record_observation(
                session_id="s1",
                target_ref="tests/test_core.py",
                measured_property="3 passed",
                how_checked="python -m unittest",
            )
            rows = store.list_observations(session_id="s1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["target_ref"], "tests/test_core.py")

    def test_export_copies_all_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "observations.jsonl"
            dest = base / "export.jsonl"
            state = ClaimCheckState(store=ReceiptStore(src))
            state.record_observation(
                session_id="s1",
                target_ref="a",
                measured_property="ok",
                how_checked="manual",
            )
            count = state.store.export_to(dest)
            self.assertEqual(count, 1)
            lines = dest.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["target_ref"], "a")


class SessionPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "observations.jsonl"
        self.state = ClaimCheckState(store=ReceiptStore(path))

    def test_risky_block_until_approve(self) -> None:
        block = self.state.pre_tool_call_block("shell_exec", "sess")
        self.assertIsNotNone(block)
        self.assertEqual(block["action"], "block")
        self.state.approve_risky("sess")
        self.assertIsNone(self.state.pre_tool_call_block("shell_exec", "sess"))

    def test_nudge_without_fresh_observation(self) -> None:
        self.state.clear_turn_observation_fresh("sess")
        self.assertTrue(self.state.should_nudge("sess", "All tests are passing."))
        self.state.mark_observation_fresh("sess")
        self.assertFalse(self.state.should_nudge("sess", "All tests are passing."))

    def test_record_observation_marks_fresh(self) -> None:
        self.state.clear_turn_observation_fresh("sess")
        self.state.record_observation(
            session_id="sess",
            target_ref="x",
            measured_property="y",
            how_checked="z",
        )
        self.assertFalse(self.state.should_nudge("sess", "Ready to ship."))


if __name__ == "__main__":
    unittest.main()
