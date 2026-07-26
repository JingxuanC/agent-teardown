# Causal Memory MCP

> **A causal memory layer for AI agents.** Records decisions and their outcomes as causal relationships, so agents learn from experience across sessions and survive compaction.
>
> Based on [insights/11](../insights/11-causal-state-store.md) + validated by [real LLM benchmark](../spike/grok-causal-memory/bench-RESULTS.md).

## What it does

Every agent has a memory problem: after N compactions, it forgets why it made past decisions. This MCP server fixes the **causal** slice of that problem:

- `record_decision` — "I chose X, it caused Y"
- `search_causal` — "What did I learn about Z in the past?"
- `trace_cause` — "Something broke, which decision caused it?"

**Key difference from Mem0/Zep/Letta**: those store *what* happened. This stores *why* — the causal link between decisions and outcomes. Per [insights/10](../insights/10-memory-frameworks.md) §6, no production memory company does this.

## Quick start

```bash
# Build
cargo build --release

# Wire into Claude Code / Cursor / any MCP-compatible agent
# Add to your MCP config:
{
  "mcpServers": {
    "causal-memory": {
      "command": "/path/to/causal-memory-mcp/target/release/causal-memory-mcp",
      "env": {
        "CAUSAL_MEMORY_DB": "~/.local/share/causal-memory/causal.db"
      }
    }
  }
}
```

Then copy [`CLAUDE.md`](CLAUDE.md) into your project's system prompt to activate proactive causal memory use.

## Data path

- Default: `~/.local/share/causal-memory/causal.db`
- Override: `CAUSAL_MEMORY_DB` env var

SQLite file, portable, no server process needed.

## Tools

| Tool | When to call | What it does |
|---|---|---|
| `record_decision` | After completing an action | Logs decision → outcome as a causal edge |
| `search_causal` | Before a non-trivial decision | Retrieves past causal episodes by task or text |
| `trace_cause` | When something fails | Reverse-traces which decision caused an outcome |

## Architecture

```
Agent ←(MCP stdio)→ Causal Memory Server → SQLite (causal_edges table)
```

The causal_edges table is **never compacted** — it's outside the agent's context window. Per [papers/02](../papers/02-compaction-degradation.md) §4.6: after k=5 compactions, textual recall drops to 45%, but causal-table recall stays at 100%.

## Build & test

```bash
cargo build --release    # Build binary
cargo test               # Run unit tests
```

## Status

v0.1.0 — working prototype. Unit tests pass, MCP server compiles and serves via stdio. Not yet wired into a production agent end-to-end.

## License

Apache-2.0
