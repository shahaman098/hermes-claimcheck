# ClaimCheck (Hermes plugin)

ClaimCheck is a zero-dependency Hermes directory plugin that enforces verify-before-done discipline for agent completion claims.

## What it does

- **Tools:** `record_observation`, `list_observations`, `export_receipt`, `approve_risky`
- **Hooks:** blocks a small denylist of risky tools until `approve_risky` is called once per session; nudges (soft) when the assistant uses completion language without a fresh `record_observation` in the current turn
- **Storage:** append-only local JSONL under Hermes plugin data (no network, no API keys)

## Install

```bash
hermes plugins install shahaman098/hermes-claimcheck
hermes plugins enable claimcheck
```

Or sideload this directory:

```bash
cp -R . ~/.hermes/plugins/claimcheck
hermes plugins enable claimcheck
```

## Demo workflow

1. Run tests or a command you want to claim about.
2. Call `record_observation` with path/ref, measured property, and how you checked.
3. Only then use completion wording (done, fixed, shipped, ready, etc.).
4. Optional: call `approve_risky` once before `shell_exec` / `write_file` / `edit_file` / `delete_file`.

## Disclosure

When enabled, ClaimCheck writes observation receipts to your local Hermes plugin data directory, registers hooks on every tool call and LLM turn, and may inject a short user-role nudge in the CLI when completion language appears without a fresh observation. It does not send data over the network and does not require API keys. Risky-tool blocking is opt-in per session via `approve_risky`.

## Development

```bash
python -m unittest discover -s tests -v
hermes plugins validate . --install-deps
```

## License

MIT
