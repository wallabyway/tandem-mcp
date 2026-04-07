# Tandem MCP Server

**Talk to your buildings.** This MCP server connects AI coding assistants to [Autodesk Tandem](https://intandem.autodesk.com/) — the digital twin platform for facilities and infrastructure. Ask questions in plain English, get answers from live BIM data: assets, sensors, rooms, systems, and work orders.

> *"What HVAC systems serve the data center on Level 2?"*
> *"Show me the last 24 hours of temperature readings in Server Room 101."*
> *"Create a ticket for the broken pump in Building A basement."*

No REST calls. No query syntax. Just tools your AI assistant already knows how to use.

---

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Installation](#installation)
  - [Claude Code](#claude-code)
  - [Cursor](#cursor)
  - [Kimi Code](#kimi-code)
  - [Codex (OpenAI)](#codex-openai)
- [Authentication](#authentication)
- [Tools Reference](#tools-reference)
- [Knowledge Base (kb.md)](#knowledge-base-kbmd)
  - [1. Glossary — Speak the Language](#1-glossary--speak-the-language)
  - [2. Spatial Hierarchy — How Buildings Are Organized](#2-spatial-hierarchy--how-buildings-are-organized)
  - [3. Systems — Connected Infrastructure](#3-systems--connected-infrastructure)
  - [4. Classifications — The Schema Behind BIM](#4-classifications--the-schema-behind-bim)
  - [5. Personas & Query Strategy — Who's Asking and How to Answer](#5-personas--query-strategy--whos-asking-and-how-to-answer)

---

## Overview

Tandem MCP exposes **27 tools** across four categories:

| Category | Count | Examples |
|----------|-------|---------|
| **Read / Discovery** | 16 | List groups, facilities, levels, rooms, assets, streams, tickets, history |
| **Spatial Queries** | 5 | Rooms on a level, assets on a floor, elements in a room, find element location |
| **System Queries** | 3 | Systems by class, system members, systems serving a room |
| **Write** | 3 | Mutate element properties, create elements, create tickets |

The server also exposes `kb.md` — a domain knowledge base — as an MCP resource. The LLM reads it to understand BIM jargon, facility management workflows, and how to translate natural-language questions into the right tool calls.

---

## Quick Start

```bash
# Clone and install
git clone <this-repo>
cd tandem-mcp-au
uv venv && uv pip install -e "."

# Set your APS (Autodesk Platform Services) credentials
export TANDEM_CLIENT_ID="your-client-id"
export TANDEM_CLIENT_SECRET="your-client-secret"

# Test it
uv run fastmcp run src/tandem_mcp/server.py
```

The server uses **2-legged OAuth** (client_credentials grant) — the same flow as the [Autodesk tutorial](https://github.com/autodesk-tandem/tutorial-rest-python). Tokens are automatically fetched and cached in `.token` with expiry tracking. No manual token management needed.

---

## Installation

### Claude Code

```bash
claude mcp add \
  -e TANDEM_CLIENT_ID=your-client-id \
  -e TANDEM_CLIENT_SECRET=your-client-secret \
  tandem-mcp -- \
  uv run --project /path/to/tandem-mcp-au \
  fastmcp run src/tandem_mcp/server.py
```

Verify with:
```bash
claude mcp list
```

### Cursor

Create `.cursor/mcp.json` in your project root (or `~/.cursor/mcp.json` for global):

```json
{
  "mcpServers": {
    "tandem-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--project", "/path/to/tandem-mcp-au",
        "fastmcp", "run", "src/tandem_mcp/server.py"
      ],
      "env": {
        "TANDEM_CLIENT_ID": "your-client-id",
        "TANDEM_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### Kimi Code

Create `.kimi/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "tandem-mcp": {
      "command": "uv",
      "args": [
        "run",
        "--project", "/path/to/tandem-mcp-au",
        "fastmcp", "run", "src/tandem_mcp/server.py"
      ],
      "transport": "stdio",
      "env": {
        "TANDEM_CLIENT_ID": "your-client-id",
        "TANDEM_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### Codex (OpenAI)

Add to `~/.codex/config.toml` (or `.codex/config.toml` for project scope):

```toml
[mcp_servers.tandem-mcp]
command = "uv"
args = [
  "run",
  "--project", "/path/to/tandem-mcp-au",
  "fastmcp", "run", "src/tandem_mcp/server.py"
]
enabled = true

[mcp_servers.tandem-mcp.env]
TANDEM_CLIENT_ID = "your-client-id"
TANDEM_CLIENT_SECRET = "your-client-secret"
```

> **Note:** Replace `/path/to/tandem-mcp-au` with the absolute path to your clone in all configs above.

---

## Authentication

The server uses **2-legged OAuth** (client_credentials grant) — the same approach as the [Autodesk Tandem Python tutorial](https://github.com/autodesk-tandem/tutorial-rest-python). You need an APS (Autodesk Platform Services) app with access to your Tandem facility.

Set two environment variables:

| Variable | Description |
|----------|-------------|
| `TANDEM_CLIENT_ID` | Your APS app client ID |
| `TANDEM_CLIENT_SECRET` | Your APS app client secret |

The server automatically:
1. Requests a token from `https://developer.api.autodesk.com/authentication/v2/token`
2. Caches it in `.token` (gitignored) with expiry tracking
3. Refreshes automatically when the token expires (with a 60s safety margin)

No manual token management needed. Scopes requested: `data:read data:write`.

---

## Tools Reference

### Read / Discovery
| Tool | Description |
|------|-------------|
| `list_groups` | List all account groups (entry point) |
| `list_group_facilities` | List facilities in a group |
| `get_facility` | Get facility details and linked models |
| `get_facility_template` | Get classifications, property sets, schema |
| `list_levels` | List floors/storeys across all models |
| `list_rooms` | List rooms/spaces across all models |
| `list_tagged_assets` | List tracked assets across all models |
| `get_element` | Get full details for a single element |
| `list_elements` | Query elements with column/family filters |
| `list_systems` | List MEP systems (HVAC, plumbing, electrical, etc.) |
| `list_streams` | List IoT streams/sensors |
| `get_stream_data` | Get time-series data for a stream |
| `get_stream_last_reading` | Get latest sensor reading |
| `list_tickets` | List work orders/issues |
| `get_facility_history` | Get change audit trail |
| `list_views` | List saved views |

### Spatial Queries
| Tool | Description |
|------|-------------|
| `list_rooms_on_level` | "What rooms are on Floor 3?" |
| `list_assets_on_level` | "What equipment is on Level 2?" |
| `list_elements_in_room` | "What's in Server Room 101?" |
| `list_streams_in_room` | "What sensors are in the cafeteria?" |
| `find_element_location` | "Where is pump P-101?" |

### System Queries
| Tool | Description |
|------|-------------|
| `list_systems_by_class` | "Show me all HVAC systems" |
| `list_system_elements` | "What's connected to AHU-1 Supply Air?" |
| `list_systems_serving_room` | "What systems serve the data center?" |

### Write
| Tool | Description |
|------|-------------|
| `mutate_elements` | Update properties on elements |
| `create_element` | Create a new element (asset, stream, etc.) |
| `create_ticket` | Create a work order/issue |

---

## Knowledge Base (kb.md)

The `kb.md` file is the secret sauce. It's a living document that teaches the LLM how to think about buildings, so it can translate your questions into the right API calls. Here's what's inside and why it matters.

### 1. Glossary — Speak the Language

BIM and facility management are full of domain-specific terms that an LLM won't know out of the box. The glossary defines **30+ terms** — from fundamentals like *Facility*, *Model*, and *Element* to Tandem-specific concepts like *Qualified Columns* (`n:n` = standard name), *Column Families* (the `m:` prefix for system membership), and *Mutations* (the `[action, family, column, value]` write format).

Without this, the LLM would have no idea that `l:r` means "this element's room reference" or that `0x01000003` means "this is a stream." With it, the LLM can interpret raw API responses and explain them in human terms.

### 2. Spatial Hierarchy — How Buildings Are Organized

Buildings are spatial. A facility contains models, models contain levels, levels contain rooms, rooms contain equipment. The kb documents this hierarchy and — critically — explains **how these relationships are stored** in the Tandem data model: level refs in `l:l`, room refs in `l:r`, cross-model room refs in `x:r`.

This section includes a lookup table mapping common questions ("What rooms are on Level 3?") to the exact tool sequence needed to answer them. The LLM uses this as a playbook.

### 3. Systems — Connected Infrastructure

A building isn't just rooms and equipment — it's interconnected *systems*. An HVAC supply air system might connect an air handler on the roof to VAV boxes on every floor to diffusers in every room, spanning multiple BIM models. The kb explains system membership (the `m:` column family), system class bitmasks (22 types from Supply Air to Storm Drainage), and how to trace system topology.

This enables questions like *"what systems serve the server room?"* — which requires finding room elements, checking their system memberships, and resolving system names.

### 4. Classifications — The Schema Behind BIM

Tandem organizes elements using **Uniformat II**, a hierarchical classification system used across the AEC industry. The kb maps out the full hierarchy — from A (Substructure) through D (Services, where HVAC lives at D30 and Electrical at D50) to G (Sitework). It explains how classifications connect to property sets and how the facility template defines what's available.

This helps the LLM understand that when a user asks about "mechanical equipment," they're talking about elements classified under D30-D50, not just anything with "mechanical" in the name.

### 5. Personas & Query Strategy — Who's Asking and How to Answer

Different people ask different questions. A **Facility Manager** cares about asset counts, energy performance, and capital planning. A **Maintenance Technician** needs to find equipment by tag number and check work order status. A **BIM Manager** wants to audit classification coverage and data completeness.

The kb profiles four personas with example questions, documents **CMMS integration patterns** (how Tandem tickets map to Maximo work orders), and provides a **decision tree** the LLM follows to route any natural-language question to the right tool sequence. This is what turns a generic chatbot into a domain-aware facility assistant.

---

## Project Structure

```
tandem-mcp-au/
├── README.md            ← You are here
├── plan.md              # Implementation plan
├── kb.md                # Knowledge base (LLM reads this)
├── .token               # Bearer token (gitignored)
├── .gitignore
├── pyproject.toml
└── src/
    └── tandem_mcp/
        ├── __init__.py
        ├── server.py    # FastMCP server + all 27 tools
        ├── client.py    # Async Tandem REST API client
        ├── constants.py # Column families, flags, qualified columns
        └── encoding.py  # Base64 key encoding/decoding
```

---

## License

MIT
