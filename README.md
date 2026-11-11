# ClaimCheck: The Double-Entry Verification Interlock Kernel

[![Hermes Agent Plugin](https://img.shields.io/badge/Hermes_Agent-Plugin_v2.0-blue.svg)](https://github.com/NousResearch/hermes-agent)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Dependencies](https://img.shields.io/badge/Dependencies-Zero_(stdlib_only)-brightgreen.svg)]()
[![Tests](https://img.shields.io/badge/Tests-11_passing-success.svg)]()

> **ClaimCheck** is a zero-dependency runtime governance kernel for [Hermes Agent](https://github.com/NousResearch/hermes-agent) that eliminates hallucinated task completion by enforcing double-entry reconciliation between code mutations and empirical test proofs.

---

## The Problem: Hallucinated Completion

Across SWE-bench and real-world developer workflows, over 60% of autonomous agent failures stem from **premature task termination**:
1. The agent edits a file.
2. The agent declares victory: *"I have fixed the bug and verified that all tests pass."*
3. The agent never actually ran the test suite—leaving behind syntax errors and broken builds.

Prompts like *"always verify before done"* fail under long context windows. **ClaimCheck replaces polite prompt nudges with a mechanical runtime interlock.**

---

## How It Works: Double-Entry Reconciliation

Imported from **Forensic Accounting** and **Poka-Yoke Reliability Engineering**:

```text
               [ AGENT MUTATES REALITY ]
          (write_file / edit_file / patch)
                          │
                          ▼
            ┌───────────────────────────┐
            │   UNBALANCED DEBIT LOG    │
            │   Mutation registered:    │
            │   auth/jwt.py (14 lines)  │
            └─────────────┬─────────────┘
                          │
       Agent attempts: "Task complete, fixed!"
                          │
                          ▼
            ┌───────────────────────────┐
            │   POKA-YOKE INTERLOCK     │
            │  (Hermes pre_verify Hook) │
            └─────────────┬─────────────┘
                          │
               Is ledger balanced?
               ├── NO ──► ⛔ HARD VETO: Clamps exit, injects reconciliation requirement.
               │          Agent forced to run `pytest tests/test_jwt.py`.
               │          post_tool_call auto-sniffs Exit Code 0 & stdout.
               │
               └── YES ─► ✅ BALANCED CREDIT committed.
                          Mints SHA-256 Attestation Voucher.
                          Issues Certified Proof-of-Work Badge.
```

1. **Mutation Debits:** When the agent modifies code (`write_file`, `edit_file`, `patch`), ClaimCheck registers an unbalanced mutation obligation.
2. **Poka-Yoke Interlock:** When the model attempts to finish its turn or exit, ClaimCheck's native `pre_verify` hook evaluates the ledger. If mutations remain unverified, **the exit is hard-vetoed**.
3. **Auto-Proof Ingestion:** When the agent executes test commands (`pytest`, `cargo test`, `npm test`, `go test`, `unittest`, `curl`), ClaimCheck sniffs the child process output in `post_tool_call`. If the test succeeds (`exit_code == 0`), an empirical observation credit is automatically minted.
4. **Cryptographic Attestation:** ClaimCheck seals the session with a deterministic SHA-256 voucher containing the session ID, target reference, how it was checked, and the execution digest.

---

## 60-Second Demo Walkthrough

### 1. Without ClaimCheck (The Agent's Lie)
```text
User: Fix the JWT expiration validation in auth/tokens.py.
Hermes: [edits auth/tokens.py]
Hermes: "All done! I have fixed the calculation and verified that authentication is working perfectly."
User: [runs pytest manually]
Result: CRASH (SyntaxError on line 42). The agent never checked.
```

### 2. With ClaimCheck (The Interlock Engaged)
```text
User: Fix the JWT expiration validation in auth/tokens.py.
Hermes: [edits auth/tokens.py]
Hermes: "I have fixed the issue..."
[ClaimCheck Interlock triggers]
⛔ [ClaimCheck Interlock Veto]
Reconciliation Deficit: Unverified mutations detected on: auth/tokens.py.
You modified files without recording an empirical verification receipt.
Run the matching test suite (e.g. `pytest`, `cargo test`, `npm test`) or
call `record_observation` with the measured property before declaring completion.

Hermes: [realizes exit is blocked -> runs `pytest tests/test_tokens.py`]
Pytest: FAIL (SyntaxError on line 42)
Hermes: [analyzes traceback -> fixes line 42 in auth/tokens.py]
Hermes: [reruns `pytest tests/test_tokens.py`]
Pytest: 4 passed in 0.04s (Exit Code 0)
[ClaimCheck auto-captures Exit Code 0 -> ledger parity achieved]

Hermes:
┌────────────────────────────────────────────────────────────────────────┐
│  🛡️  CLAIMCHECK BALANCED RECONCILIATION VOUCHER                         │
│  Status: BALANCED                                                      │
│  Target: pytest tests/test_tokens.py                                   │
│  Evidence: pytest tests/test_tokens.py (Tests passed (Exit Code 0))    │
│  Attestation: sha256:7b9c3a14e9f82d10...                               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Install & Setup

### Official Plugin Install
```bash
hermes plugins install shahaman098/hermes-claimcheck
hermes plugins enable claimcheck
```

### Or Local Sideload
```bash
cp -R . ~/.hermes/plugins/claimcheck
hermes plugins enable claimcheck
```

---

## Features & Capabilities

* **Zero External Dependencies:** Built 100% on the Python standard library (`hashlib`, `json`, `pathlib`, `re`, `time`). Zero network calls, zero API keys, <5ms latency.
* **Auto-Proof Ingestion:** Native sniffer for `pytest`, `cargo test`, `npm test`, `npx vitest/jest`, `go test`, `python -m unittest`, and `curl 200`.
* **Slash Command `/claimcheck`:** In-session inspection of ledger parity, open mutations, and attestation vouchers.
* **Cryptographic Ledger:** Append-only JSONL storage under `~/.hermes/plugin-data/claimcheck/observations.jsonl`.
* **Exportable Audit Trail:** Export verifiable receipts to Markdown or JSON for CI/CD pipelines and GitHub PR status checks via `export_receipt`.
* **Risky Tool Gating:** Optional per-session protection against destructive operations (`shell_exec`, `delete_file`).

---

## Development & Verification

Run the test suite:
```bash
python3 -m unittest discover -s tests -v
```

Validate with the Hermes plugin harness:
```bash
hermes plugins validate . --install-deps
```

---

## License

MIT © [shahaman098](https://github.com/shahaman098)
