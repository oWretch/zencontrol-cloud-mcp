# Contributing to zencontrol-mcp

Thanks for your interest in contributing! This guide covers everything you need
to get started.

## Development Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/oWretch/zencontrol-mcp.git
   cd zencontrol-mcp
   ```

2. **Install dependencies (including dev tools):**

   ```bash
   uv sync
   ```

   This installs all runtime and development dependencies in an isolated virtual
   environment.

3. **Copy the environment template:**

   ```bash
   cp .env.example .env
   ```

   Fill in your `ZENCONTROL_CLIENT_ID` and `ZENCONTROL_CLIENT_SECRET`.

## Code Style

- **Linter / formatter:** [Ruff](https://docs.astral.sh/ruff/) handles both
  linting and formatting.
- **Type hints** are required on all function signatures.
- **Docstrings** (Google style) are expected on public modules, classes, and
  functions.

Run the checks locally before pushing:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

Auto-fix simple issues:

```bash
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```

## Project Structure

```text
src/zencontrol_mcp/
├── server.py          # FastMCP server setup, lifespan, CLI entry point
├── tools/             # MCP tool definitions (one file per domain)
│   ├── __init__.py    # register_all_tools() — imports all tool modules
│   ├── sites.py       # list_sites, get_site_details
│   ├── devices.py     # list_groups, list_devices
│   └── control.py     # control_light, set_colour
├── api/               # HTTP client layer
│   ├── client.py      # ZenControlClient — low-level httpx wrapper
│   └── rest.py        # ZenControlAPI — high-level domain methods
├── models/            # Pydantic schemas for API request/response types
│   └── schemas.py
└── auth/              # OAuth 2.0 and token management
    ├── oauth.py       # Authorization Code flow helpers
    ├── proxy.py       # OAuth proxy server for redirect handling
    └── token_store.py # Encrypted on-disk token persistence
```

## Adding a New Tool

1. **Create a file** in `src/zencontrol_mcp/tools/` (or add to an existing one
   if the tool fits an existing domain).

2. **Define a `register(mcp)` function** that uses `@mcp.tool()` to register
   one or more tools:

   ```python
   from __future__ import annotations

   from typing import TYPE_CHECKING

   from fastmcp import Context

   if TYPE_CHECKING:
       from fastmcp import FastMCP
       from zencontrol_mcp.api.rest import ZenControlAPI


   def register(mcp: FastMCP) -> None:
       @mcp.tool()
       async def my_new_tool(ctx: Context, site_id: str) -> str:
           """Short description shown to the AI assistant."""
           api: ZenControlAPI = ctx.lifespan_context["api"]
           result = await api.some_method(site_id)
           return format_result(result)
   ```

3. **Import and call** your register function in
   `src/zencontrol_mcp/tools/__init__.py`:

   ```python
   from zencontrol_mcp.tools.my_module import register as register_my_tools

   def register_all_tools(mcp: FastMCP) -> None:
       ...
       register_my_tools(mcp)
   ```

4. **Add tests** in `tests/` — see the testing section below.

### Tool Design Conventions

- **Scope-parameterised pattern:** prefer a single tool with a `scope_type`
  parameter over many near-identical variant tools. For example, `list_groups`
  accepts `scope_type` (site, floor, map, gateway) and `scope_id` rather than
  having `list_site_groups`, `list_floor_groups`, etc.
- **Return formatted strings**, not raw JSON — the output is consumed by an LLM,
  not a machine.
- Access the API client via `ctx.lifespan_context["api"]`.

## Testing

Tests live in the `tests/` directory and are run with
[pytest](https://docs.pytest.org/):

```bash
uv run pytest
uv run pytest -v              # verbose
uv run pytest tests/test_X.py # single file
```

## Documentation

Generate full server API docs from Python docstrings as Markdown:

```bash
uv run python scripts/generate_docs.py
```

The generated API reference is written to `docs/reference/api.md`.

When changing public tools, models, or API client behavior, regenerate docs and
include updated `docs/reference/` files in the same change.

### Payload Shape Compatibility

ZenControl may return some label fields either as wrapped sync objects
(`{"value": "..."}`) or as plain strings (`"..."`).

Keep model parsing tolerant of both shapes to avoid regressions in hierarchy
tools such as `get_site_details`.

### Guidelines

- **Mock HTTP calls** with [respx](https://github.com/lundberg/respx) — never
  hit the real ZenControl API in tests.
- **Async tests** use [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
  — mark them with `@pytest.mark.asyncio`.
- Test that tools return the expected **formatted strings** for known API
  responses.
- Aim for high coverage of the `tools/` and `api/` layers; auth flows are
  harder to unit-test and can rely on integration tests.

### Example Test

```python
import pytest
import respx
from httpx import Response

@pytest.mark.asyncio
async def test_list_sites(respx_mock):
    respx_mock.get("https://api.zencontrol.com/v2/sites").mock(
        return_value=Response(200, json=[{"id": "s1", "name": "HQ"}])
    )
    # … invoke the tool and assert the formatted output
```

## Pull Request Process

1. **Create a feature branch** from `main`.
2. Make your changes, keeping commits focused and well-described.
3. Ensure all checks pass:
   ```bash
   uv run ruff check src/ tests/
   uv run ruff format --check src/ tests/
   uv run pytest
   ```
4. Open a pull request against `main` with a clear description of what changed
   and why.
5. Address review feedback — the PR will be squash-merged once approved.

## Maintainer Operations

This section is for maintainers responsible for reliability, release quality,
and long-term project consistency.

### Maintenance Goals

- Keep MCP tool contracts stable and clearly documented.
- Keep auth and transport behavior explicit and safe.
- Ensure tests cover formatting and payload-shape edge cases.

### Architecture Snapshot

- Entry point: `src/zencontrol_mcp/server.py`
- REST client layer: `src/zencontrol_mcp/api/client.py`, `src/zencontrol_mcp/api/rest.py`
- Live API websocket layer: `src/zencontrol_mcp/api/live.py`
- Auth/token storage: `src/zencontrol_mcp/auth/`
- Tool registration and surface area: `src/zencontrol_mcp/tools/`
- Models/schemas: `src/zencontrol_mcp/models/schemas.py`

### Standard Local Validation

```bash
uv sync
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pytest
```

### MCP Change Validation Loop

For MCP-facing changes in VS Code:

1. Edit code.
2. Restart the `zencontrol` MCP server from VS Code MCP tooling.
3. Re-run tool calls from the client.

Do not rely on hot-reload assumptions for stdio-mode validation.

### Documentation Responsibilities

When changing behavior in tools, API methods, transport/auth, or schemas:

1. Update user-facing behavior notes in `README.md`.
2. Update contributor/maintainer process notes in `CONTRIBUTING.md`.
3. Update coding-agent constraints in `AGENTS.md` when implementation conventions change.
4. Regenerate reference docs:

```bash
uv run python scripts/generate_docs.py
```

### Release Checklist

1. Bump version in `pyproject.toml`.
2. Run lint, format check, and tests.
3. Regenerate `docs/reference/api.md`.
4. Verify docs mention any new tools, env vars, or behavior changes.
5. Create tag/release notes with a user-impact summary.

### Common Regression Risks

- Payload shape drift in ZenControl API responses.
- Scope handling regressions that allow unintended cross-site actions.
- Tool output formatting regressions (LLM-facing string quality).
- Live API entitlement assumptions (401/403 behavior).

### Recommended Test Coverage for New Features

- Positive path with representative payloads.
- Error path with clear surfaced message.
- Scope-constrained behavior.
- Response formatting assertions where practical.
