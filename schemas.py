"""Tool schemas exposed to the model."""

RECORD_OBSERVATION = {
    "name": "record_observation",
    "description": (
        "Record a verification receipt before claiming work is done. "
        "Required before completion language (done, fixed, shipped, ready, etc.). "
        "Store path or ref, what you measured, and how you checked it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target_ref": {
                "type": "string",
                "description": "File path, URL ref, or identifier for what you checked",
            },
            "measured_property": {
                "type": "string",
                "description": "What you measured or verified (e.g. exit code 0, test count)",
            },
            "how_checked": {
                "type": "string",
                "description": "How you checked it (command, test name, manual step)",
            },
            "turn_hint": {
                "type": "string",
                "description": "Optional short label tying this receipt to the current task",
            },
        },
        "required": ["target_ref", "measured_property", "how_checked"],
    },
}

LIST_OBSERVATIONS = {
    "name": "list_observations",
    "description": "List local JSONL observation receipts for this session or all sessions.",
    "parameters": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Max rows to return (default 20, most recent)",
            },
            "all_sessions": {
                "type": "boolean",
                "description": "If true, include receipts from other sessions",
            },
        },
    },
}

EXPORT_RECEIPT = {
    "name": "export_receipt",
    "description": (
        "Copy the local observation JSONL log to a destination path for auditing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "dest_path": {
                "type": "string",
                "description": "Destination file path for the exported JSONL",
            },
        },
        "required": ["dest_path"],
    },
}

APPROVE_RISKY = {
    "name": "approve_risky",
    "description": (
        "One-time per-session approval to allow ClaimCheck risky tools "
        "(shell_exec, terminal, write_file, edit_file, patch, delete_file) after you accept the risk."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Brief reason you need risky tools this session",
            },
        },
    },
}

CLAIMCHECK_STATUS = {
    "name": "claimcheck_status",
    "description": (
        "Inspect the ClaimCheck double-entry reconciliation ledger: view open mutations, "
        "empirical verification receipts, ledger parity state, and cryptographic attestation vouchers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "verbose": {
                "type": "boolean",
                "description": "If true, include detailed receipt digests and full hashes.",
            },
        },
    },
}
