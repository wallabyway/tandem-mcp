# Tandem MCP Server — Implementation Plan

## Overview

Build an MCP server using **FastMCP** (Python) that wraps the Autodesk Tandem REST API, based on patterns from [autodesk-tandem/tutorial-rest-python](https://github.com/autodesk-tandem/tutorial-rest-python). Auth token is read from a `.token` file (populated externally by a separate auth tool).

## Auth Strategy

- Read bearer token from `.token` file at project root on each request
- No OAuth flow in this server — token lifecycle managed externally
- Pass token via `Authorization: Bearer <token>` header
- Base URL: `https://developer.api.autodesk.com/tandem/v1`

## Selected Tools (Curated for Usefulness)

### Read-Only / Discovery Tools

| Tool | Description | Why useful |
|------|-------------|------------|
| `list_groups` | List all account groups | Entry point — discover what you have access to |
| `list_group_facilities` | List facilities in a group | Navigate from group → facilities |
| `get_facility` | Get facility details (name, models, links) | Core lookup for any facility work |
| `get_facility_template` | Get classifications, property sets, schema | Needed to understand facility structure |
| `list_facility_models` | List models linked to a facility | Navigate from facility → models |
| `list_levels` | List levels in a model | Spatial navigation |
| `list_rooms` | List rooms in a model | Spatial navigation |
| `list_tagged_assets` | List tagged/tracked assets in a model | Core asset management |
| `get_element` | Get a single element by key with properties | Drill into any element |
| `list_elements` | Query elements with column/family filters | Flexible element search |
| `list_systems` | List MEP systems in a model | Systems overview |
| `list_streams` | List IoT streams in a model | IoT data discovery |
| `get_stream_data` | Get time-series data for a stream (with date range) | Read sensor/IoT data |
| `get_stream_last_reading` | Get latest reading for streams | Quick IoT status check |
| `list_tickets` | List tickets/issues in a model | Issue tracking |
| `get_facility_history` | Get change history for a facility | Audit trail |
| `list_views` | List saved views for a facility | View management |

### Write Tools

| Tool | Description | Why useful |
|------|-------------|------------|
| `mutate_elements` | Batch update element properties | Core write operation for property edits |
| `create_element` | Create a new element (asset, stream, etc.) | Add new tracked items |
| `create_ticket` | Create a new ticket/issue | Issue management |

### Excluded (and why)

- **Document upload/download** — complex multi-step flow with ACC integration, not practical via MCP
- **Stream secret management** — admin/infra concern, not day-to-day
- **Stream config overrides / thresholds** — niche admin operations
- **Delete operations** (elements, stream data) — destructive, dangerous via AI tool
- **Classification assignment** — requires deep template knowledge, error-prone
- **View creation** — complex JSON structure with camera/cutPlanes, API marked "NOT SUPPORTED"

### Spatial Query Tools (composite / higher-level)

These tools combine multiple API calls to answer common spatial questions. They read `kb.md` for domain context.

| Tool | Description | Why useful |
|------|-------------|------------|
| `list_rooms_on_level` | Given a facility + level name/key, return all rooms on that level | "What rooms are on Floor 3?" |
| `list_assets_on_level` | Given a facility + level name/key, return all tagged assets on that level | "What equipment is on Level 2?" |
| `list_elements_in_room` | Given a facility + room name/key, return all elements in that room | "What's in Server Room 101?" |
| `list_streams_in_room` | Given a facility + room name/key, return all IoT streams for that room | "What sensors are in the cafeteria?" |
| `find_element_location` | Given an element name, return its level + room(s) | "Where is pump P-101?" |

### System Query Tools (composite / higher-level)

| Tool | Description | Why useful |
|------|-------------|------------|
| `list_systems_by_class` | Filter systems by class (HVAC, plumbing, electrical, fire, etc.) | "Show me all HVAC systems" |
| `list_system_elements` | Given a system name/key, return all member elements across models | "What elements are in AHU-1 Supply Air?" |
| `list_systems_serving_room` | Given a room, find all systems that have members in that room | "What systems serve the data center?" |

## Project Structure

```
tandem-mcp-au/
├── plan.md              # This file
├── kb.md                # Knowledge base — glossary, classifications, personas, query strategies
├── .token               # Bearer token (gitignored, created externally)
├── .gitignore
├── pyproject.toml       # Project config, dependencies
├── README.md            # Setup instructions (if requested)
└── src/
    └── tandem_mcp/
        ├── __init__.py
        ├── server.py    # FastMCP server definition + all tools
        ├── client.py    # Tandem REST API client (adapted from tutorial)
        ├── constants.py # Column families, flags, qualified column names
        └── encoding.py  # Base64/key encoding utilities
```

## Dependencies

- `fastmcp` — MCP server framework
- `httpx` — async HTTP client (preferred over `requests` for FastMCP)

## Implementation Steps

### 1. Project scaffolding
- Create `pyproject.toml` with dependencies
- Create `.gitignore` (include `.token`, `__pycache__`, etc.)
- Create package structure under `src/tandem_mcp/`

### 2. Port core utilities
- `constants.py` — copy relevant constants from tutorial (column families, element flags, qualified columns)
- `encoding.py` — copy key encoding/decoding functions needed for interpreting API responses

### 3. Build async API client (`client.py`)
- Async wrapper using `httpx.AsyncClient`
- Token read from `.token` file on each call
- Methods for each API endpoint we're exposing
- Region support via optional config

### 4. Define MCP tools (`server.py`)
- One `@mcp.tool()` per selected tool above
- Each tool: validate inputs → call client → format response
- Return structured data (dicts/lists) that FastMCP serializes
- Include clear docstrings — these become the tool descriptions in MCP

### 5. Wire up and test
- Entry point via `fastmcp` CLI or `mcp.run()`
- Test with MCP Inspector or Claude Desktop

## Key Design Decisions

1. **Async everywhere** — FastMCP supports async; Tandem API is I/O-bound, async is a natural fit
2. **Token from file** — simple, no OAuth complexity; user manages token refresh separately
3. **Two tiers of tools** — simple 1:1 API wrappers + composite "smart" tools for spatial/system queries
4. **kb.md as LLM context** — the server reads `kb.md` and includes it as a system prompt / resource so the LLM knows how to interpret Tandem data, translate user jargon, and chain tools correctly
5. **Return raw-ish data** — let the LLM interpret Tandem's response format rather than over-processing
6. **No caching** — token and data can change; keep it stateless
7. **Composite tools do the joins** — spatial and system queries require multi-step API calls with key decoding; the MCP tool handles this so the LLM doesn't have to
