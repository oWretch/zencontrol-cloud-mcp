# Copilot Instructions — zencontrol-mcp

This is an MCP (Model Context Protocol) server that lets AI assistants control
ZenControl DALI-2 lighting systems. Keep these conventions in mind when working
on the codebase.

## Language & Runtime

- **Python 3.11+**, async-first (`async def` everywhere, `httpx.AsyncClient`).
- Package manager: **uv**. Run tools with `uv run`.
- Entry point: `src/zencontrol_mcp/server.py` → `main()`.

## Key Libraries

| Library | Purpose |
|---------|---------|
| `fastmcp` | MCP server framework (tools, lifespan, transports) |
| `httpx` | Async HTTP client for ZenControl Cloud REST API |
| `pydantic` | Data models / schemas for all API types |
| `cryptography` | Fernet encryption for stored OAuth tokens |
| `platformdirs` | Cross-platform token storage paths |

## File Organisation

```text
src/zencontrol_mcp/
  server.py        — FastMCP server, lifespan, CLI
  tools/           — MCP tool definitions (one file per domain)
  api/             — HTTP client (client.py) and domain methods (rest.py)
  models/          — Pydantic schemas (schemas.py)
  auth/            — OAuth flow, token storage, proxy server
```

## Naming Conventions

- **Functions / tools:** `snake_case` (e.g., `list_sites`, `control_light`).
- **Pydantic models:** `PascalCase` (e.g., `SiteDetails`, `GroupSummary`).
- **Files:** `snake_case.py`, one module per logical domain.

## Tool Design Patterns

### Scope-parameterised tools

Tools that list entities (groups, devices) accept `scope_type` and `scope_id`
instead of having separate tools per scope. Example:

```python
@mcp.tool()
async def list_groups(
    ctx: Context,
    scope_type: Literal["site", "floor", "map", "gateway"],
    scope_id: str,
) -> str: ...
```

### Accessing the API

All tools get the API client from the MCP lifespan context:

```python
api: ZenControlAPI = ctx.lifespan_context["api"]
```

Never construct `ZenControlAPI` or `ZenControlClient` inside a tool.

### Return values

Tools return **formatted strings** (not raw JSON), because the output is
consumed by an LLM. Use bullet lists, tables, or short paragraphs.

## Error Handling

- **401 Unauthorized** → automatic token refresh and retry (handled in
  `ZenControlClient`).
- **429 Too Many Requests** → automatic back-off and retry.
- **DALI errors** (device unreachable, group empty, etc.) → surface clearly in
  the tool's return string so the LLM can report it to the user.
- Prefer raising descriptive exceptions over returning empty strings on failure.

## Testing

- Framework: **pytest** + **pytest-asyncio**.
- HTTP mocking: **respx** (mocks `httpx` at the transport layer).
- Test that tools return the expected formatted strings for canned API
  responses.
- Mark async tests with `@pytest.mark.asyncio`.
- Never hit the real ZenControl API in tests.

## Linting & Formatting

- **Ruff** for both linting and formatting.
- Run before committing:
  ```bash
  uv run ruff check src/ tests/
  uv run ruff format --check src/ tests/
  ```

## Local MCP Restart Workflow

- For this repo, prefer restarting the MCP server with **VS Code MCP tooling** instead of trying to hot-reload the Python process.
- This server normally runs in **stdio** mode from `.vscode/mcp.json`. In that mode, killing and recreating only the child process is not a reliable fix/validate loop because the MCP client session has already been initialized.
- After changing MCP-facing code, restart the server from VS Code using one of these paths:
  - `MCP: List Servers` → select `zencontrol` → `Restart`
  - the inline restart action in `.vscode/mcp.json`
  - the MCP server management UI in the Extensions or Chat customizations surfaces
- Do **not** assume a file watcher or background wrapper is sufficient for validating stdio MCP changes inside the active Copilot session.
- If the goal is a fix/validate loop, the expected workflow is: edit code, restart the `zencontrol` MCP server from VS Code, then retry the MCP tool call.
- Use `uv run zencontrol-mcp --log-level DEBUG` when reproducing startup issues outside VS Code.

## Things to Avoid

- Do **not** add synchronous blocking calls (`requests`, `time.sleep`).
- Do **not** store secrets in source code — credentials come from environment
  variables.
- Do **not** create tools that duplicate existing ones — extend the scope
  parameter instead.
- Do **not** return raw JSON dicts from tools — always format for human / LLM
  readability.
