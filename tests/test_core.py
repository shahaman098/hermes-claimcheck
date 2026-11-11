"""Unit tests for ClaimCheck 2.0 Double-Entry Verification Interlock Kernel."""

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
    is_mutation_tool,
    is_risky_tool,
)


class CompletionClaimTests(unittest.TestCase):
    def test_detects_completion_words(self) -> None:
        self.assertTrue(contains_completion_claim("The fix is done."))
        self.assertTrue(contains_completion_claim("Shipped to prod"))
        self.assertTrue(contains_completion_claim("All tests verified and passing."))
        self.assertFalse(contains_completion_claim("Still investigating"))

    def test_risky_tool_set(self) -> None:
        self.assertTrue(is_risky_tool("shell_exec"))
        self.assertTrue(is_risky_tool("terminal"))
        self.assertTrue(is_risky_tool("write_file"))
        self.assertFalse(is_risky_tool("read_file"))

    def test_mutation_tool_set(self) -> None:
        self.assertTrue(is_mutation_tool("write_file"))
        self.assertTrue(is_mutation_tool("edit_file"))
        self.assertTrue(is_mutation_tool("patch"))
        self.assertFalse(is_mutation_tool("shell_exec"))
        self.assertFalse(is_mutation_tool("read_file"))


class ReceiptStoreTests(unittest.TestCase):
    def test_append_and_list_with_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "observations.jsonl"
            store = ReceiptStore(path)
            state = ClaimCheckState(store=store)
            obs = state.record_observation(
                session_id="s1",
                target_ref="tests/test_core.py",
                measured_property="3 passed",
                how_checked="python -m unittest",
            )
            self.assertTrue(obs.receipt_hash)
            self.assertEqual(len(obs.receipt_hash), 64)

            rows = store.list_observations(session_id="s1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["target_ref"], "tests/test_core.py")
            self.assertEqual(rows[0]["receipt_hash"], obs.receipt_hash)

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


class DoubleEntryInterlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "observations.jsonl"
        self.state = ClaimCheckState(store=ReceiptStore(path))

    def test_mutation_creates_reconciliation_deficit(self) -> None:
        sid = "sess_debit"
        self.assertTrue(self.state.is_balanced(sid))

        self.state.record_mutation(sid, "src/auth.py", "edit_file")
        self.assertFalse(self.state.is_balanced(sid))
        self.assertIn("src/auth.py", self.state.ledger(sid).unverified_paths())

        # Interlock should veto completion
        veto = self.state.pre_verify_interlock(sid)
        self.assertIsNotNone(veto)
        self.assertEqual(veto["action"], "continue")
        self.assertIn("⛔ [ClaimCheck Interlock Veto]", veto["message"])
        self.assertIn("src/auth.py", veto["message"])

        # Recording empirical observation balances the ledger
        self.state.record_observation(
            session_id=sid,
            target_ref="tests/test_auth.py",
            measured_property="4 passed",
            how_checked="pytest tests/test_auth.py",
        )
        self.assertTrue(self.state.is_balanced(sid))
        self.assertIsNone(self.state.pre_verify_interlock(sid))

    def test_auto_proof_ingestion_success(self) -> None:
        sid = "sess_auto"
        self.state.record_mutation(sid, "server.py", "write_file")
        self.assertFalse(self.state.is_balanced(sid))

        pytest_output = "==================== 12 passed in 0.42s ===================="
        obs = self.state.try_auto_ingest_tool_result(
            session_id=sid,
            tool_name="terminal",
            args={"command": "pytest tests/test_server.py"},
            result=pytest_output,
        )
        self.assertIsNotNone(obs)
        self.assertTrue(obs.is_automatic)
        self.assertTrue(self.state.is_balanced(sid))
        self.assertIsNone(self.state.pre_verify_interlock(sid))

    def test_auto_proof_ingestion_failure_does_not_mint_credit(self) -> None:
        sid = "sess_fail"
        self.state.record_mutation(sid, "calc.py", "edit_file")

        failed_output = (
            "Traceback (most recent call last):\n"
            "  File 'test_calc.py', line 5, in <module>\n"
            "    assert calc.add(2, 2) == 4\n"
            "AssertionError\n"
            "FAILURES: 1 failed in 0.05s\n"
        )
        obs = self.state.try_auto_ingest_tool_result(
            session_id=sid,
            tool_name="terminal",
            args={"command": "pytest test_calc.py"},
            result=failed_output,
        )
        self.assertIsNone(obs)
        self.assertFalse(self.state.is_balanced(sid))
        veto = self.state.pre_verify_interlock(sid)
        self.assertIsNotNone(veto)

    def test_attestation_voucher_and_ascii_cert(self) -> None:
        sid = "sess_voucher"
        self.state.record_mutation(sid, "main.rs", "edit_file")
        self.state.record_observation(
            session_id=sid,
            target_ref="src/main.rs",
            measured_property="test result: ok. 5 passed",
            how_checked="cargo test",
            stdout_digest="d8a2b3c4e5f6",
        )
        voucher = self.state.generate_attestation_voucher(sid)
        self.assertIsNotNone(voucher)
        self.assertEqual(voucher["parity"], "BALANCED")
        self.assertEqual(voucher["target"], "src/main.rs")

        cert = self.state.format_ascii_certificate(sid)
        self.assertIn("CLAIMCHECK BALANCED RECONCILIATION VOUCHER", cert)
        self.assertIn("BALANCED", cert)


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


if __name__ == "__main__":
    unittest.main()
