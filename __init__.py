"""ClaimCheck Hermes plugin registration."""

from __future__ import annotations

from pathlib import Path

from . import hooks, schemas, tools
from .core import ClaimCheckState, ReceiptStore

PLUGIN_ID = "claimcheck"
TOOLSET = "claimcheck"


def register(ctx) -> None:
    data_root = _resolve_data_root(ctx)
    receipts = data_root / "observations.jsonl"
    state = ClaimCheckState(store=ReceiptStore(receipts))
    tools.configure(state)
    hooks.configure(ctx, state)

    # Register tools
    ctx.register_tool(
        name="record_observation",
        toolset=TOOLSET,
        schema=schemas.RECORD_OBSERVATION,
        handler=tools.record_observation,
        description="Record an empirical verification receipt with cryptographic attestation",
    )
    ctx.register_tool(
        name="list_observations",
        toolset=TOOLSET,
        schema=schemas.LIST_OBSERVATIONS,
        handler=tools.list_observations,
        description="List local observation receipts and ledger history",
    )
    ctx.register_tool(
        name="export_receipt",
        toolset=TOOLSET,
        schema=schemas.EXPORT_RECEIPT,
        handler=tools.export_receipt,
        description="Export the cryptographic observation ledger for CI/CD auditing",
    )
    ctx.register_tool(
        name="approve_risky",
        toolset=TOOLSET,
        schema=schemas.APPROVE_RISKY,
        handler=tools.approve_risky,
        description="Approve risky tool execution for the session",
    )
    ctx.register_tool(
        name="claimcheck_status",
        toolset=TOOLSET,
        schema=schemas.CLAIMCHECK_STATUS,
        handler=tools.claimcheck_status,
        description="Inspect double-entry reconciliation ledger parity and attestation vouchers",
    )

    # Register slash command /claimcheck
    register_cmd = getattr(ctx, "register_command", None)
    if callable(register_cmd):
        try:
            register_cmd(
                name="claimcheck",
                handler=tools.claimcheck_slash_command,
                description="View ClaimCheck reconciliation ledger parity and attestation certificate",
            )
        except Exception:
            pass

    # Register lifecycle hooks
    ctx.register_hook("pre_tool_call", hooks.on_pre_tool_call)
    ctx.register_hook("post_tool_call", hooks.on_post_tool_call)
    ctx.register_hook("pre_verify", hooks.on_pre_verify)
    ctx.register_hook("pre_llm_call", hooks.on_pre_llm_call_turn_start)
    ctx.register_hook("post_llm_call", hooks.on_post_llm_call)


def _resolve_data_root(ctx) -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir

        return plugin_data_dir(PLUGIN_ID)
    except Exception:
        pass
    getter = getattr(ctx, "plugin_data_dir", None)
    if callable(getter):
        try:
            return Path(getter())
        except Exception:
            pass
    return Path.home() / ".hermes" / "plugin-data" / PLUGIN_ID
