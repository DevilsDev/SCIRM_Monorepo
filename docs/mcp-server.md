# MCP server (AI agents)

SCIRM is an [MCP](https://modelcontextprotocol.io) server, so an AI agent such as Claude
can look things up in SCIRM and propose changes, within limits your organization sets.

## Connecting

An administrator creates a key in **Administration → Integrations → AI agents (MCP)**. The
key is shown once, with the command for Claude Code:

```bash
claude mcp add --transport http scirm https://<your SCIRM>/mcp --header "Authorization: Bearer <key>"
```

Other MCP clients: Streamable HTTP at `https://<your SCIRM>/mcp`, with the key in an
`Authorization: Bearer` header. A key with the `mcp` scope can call only `/mcp`, nothing
else in the API, and expires after 90 days (revoke it on the same card). The server answers
nothing without such a key, not even its list of tools. Each key may make 30 tool calls per
minute (`MCP_CALLS_PER_MINUTE`).

## Tools

| Tool | What it returns |
|---|---|
| `search_suppliers` | Your suppliers: SAP number, country, risk tier, 12-month spend per currency |
| `supplier_records` | Public records matched to one supplier, and how each was matched |
| `ask` | A cited answer about one supplier, as in SCIRM (unverifiable sentences are removed) |
| `regulatory_watch` | FDA and EMA records naming a substance or product on your watchlist |
| `list_incidents`, `get_incident` | War-room incidents, with suppliers, spend at stake, tasks and timeline |
| `run_scenario` | [Spend at risk](scenario-studio.md) if suppliers are out for N weeks, and the resilience plan |
| `propose_action` | Propose a change (see below) |

The read tools are marked read-only. They see exactly what a read-only member of your
organization sees: the same code and row-level security as the web app.

## Changes are proposals

`propose_action` can open an incident, add a note to one, add a term to the watchlist, or
send a questionnaire to a supplier. What happens depends on your
[AI action policy](ai-control-centre.md): refused, queued for a person's approval (the
default), or done directly with an analyst's permissions. Sending a questionnaire emails
someone outside the organization, so it is never done without a person, and by default an
agent may not even propose it.

## Trust

- Record titles and summaries come from public sources, and assessment answers from
  suppliers: they are third-party text. Results that contain them say so, and the server's
  instructions tell the client never to follow instructions found in them.
- Answers are built from the records, numbers come from SCIRM's code, and every sentence of
  an `ask` answer cites its record.
- Every tool call is in the [AI run log](ai-control-centre.md#run-log), with the key's name.
