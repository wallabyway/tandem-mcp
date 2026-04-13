"""Tandem MCP Server — FastMCP tools for Autodesk Tandem digital twin platform."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .client import TandemClient
from .constants import (
    COLUMN_FAMILIES_DTPROPERTIES,
    COLUMN_FAMILIES_REFS,
    COLUMN_FAMILIES_STANDARD,
    COLUMN_FAMILIES_XREFS,
    MUTATE_ACTIONS_INSERT,
    COLUMN_NAMES_CATEGORY_ID,
    COLUMN_NAMES_ELEMENT_FLAGS,
    COLUMN_NAMES_NAME,
    COLUMN_NAMES_UNIFORMAT_CLASS,
    ELEMENT_FLAGS_TICKET,
    get_default_model_id,
)
from .instrumentation import configure_logging, log_tool

configure_logging()

mcp = FastMCP(
    "Tandem MCP Server",
    instructions=(
        "This server provides tools for querying and managing Autodesk Tandem digital twin facilities. "
        "IMPORTANT: You MUST call the get_knowledge_base tool BEFORE any other tool. "
        "It contains critical information about identifier formats (Maximo vs Tandem keys), "
        "LAWA naming conventions, and query strategies that prevent wasted API calls. "
        "Skipping it will cause you to misroute lookups and search unnecessary facilities."
    ),
)

KB_PATH = Path(__file__).resolve().parent.parent.parent / "kb.md"


@mcp.tool()
def get_knowledge_base() -> str:
    """IMPORTANT: Call this tool FIRST, before any other tool. Returns the Tandem domain knowledge base containing identifier formats, LAWA naming conventions, query strategies, and Maximo field mappings. Skipping this will cause misrouted lookups."""
    if KB_PATH.exists():
        return KB_PATH.read_text()
    return "Knowledge base not found."


# ── Shared singleton client ──────────────────────────────────────────

_client_instance: TandemClient | None = None


def _client() -> TandemClient:
    global _client_instance
    if _client_instance is not None:
        return _client_instance
    client_id = os.environ.get("TANDEM_CLIENT_ID", "")
    client_secret = os.environ.get("TANDEM_CLIENT_SECRET", "")
    if not client_id or not client_secret:
        raise RuntimeError("Set TANDEM_CLIENT_ID and TANDEM_CLIENT_SECRET environment variables")
    _client_instance = TandemClient(client_id=client_id, client_secret=client_secret)
    return _client_instance


# ═══════════════════════════════════════════════════════════════════════
# READ-ONLY / DISCOVERY TOOLS
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
@log_tool
async def list_groups() -> Any:
    """List all account groups. This is the entry point — use it to discover what facilities you have access to."""
    return await _client().get_groups()


@mcp.tool()
@log_tool
async def list_group_facilities(group_id: str) -> Any:
    """List all facilities in a group. Returns a dict of facility_id -> facility info."""
    return await _client().get_group_facilities(group_id)


@mcp.tool()
@log_tool
async def get_facility(facility_id: str) -> Any:
    """Get facility details including name, address, and linked models. The 'links' array contains model IDs needed for element queries."""
    return await _client().get_facility(facility_id)


@mcp.tool()
@log_tool
async def get_facility_template(facility_id: str) -> Any:
    """Get the facility's schema template — classifications, property sets, and custom attributes. Use this to understand what data is available."""
    return await _client().get_facility_template(facility_id)


@mcp.tool()
@log_tool
async def list_levels(facility_id: str) -> list:
    """List all levels (floors/storeys) across all models in a facility."""
    from .constants import QC_KEY, QC_NAME, QC_ONAME, QC_ELEVATION

    async def _per_model(model_id: str) -> list:
        levels = await _client().get_levels(model_id)
        return [
            {"key": lv.get(QC_KEY), "name": lv.get(QC_ONAME) or lv.get(QC_NAME), "elevation": lv.get(QC_ELEVATION), "model_id": model_id}
            for lv in levels
        ]
    return await _client()._fan_out(facility_id, _per_model)


@mcp.tool()
@log_tool
async def list_rooms(facility_id: str) -> list:
    """List all rooms/spaces across all models in a facility."""
    from .constants import QC_KEY, QC_NAME, QC_ONAME, QC_LEVEL

    async def _per_model(model_id: str) -> list:
        rooms = await _client().get_rooms(model_id)
        return [
            {"key": rm.get(QC_KEY), "name": rm.get(QC_ONAME) or rm.get(QC_NAME), "level_ref": rm.get(QC_LEVEL), "model_id": model_id}
            for rm in rooms
        ]
    return await _client()._fan_out(facility_id, _per_model)


@mcp.tool()
@log_tool
async def list_tagged_assets(facility_id: str) -> list:
    """List all tagged/tracked assets across all models in a facility. Assets are elements explicitly marked for lifecycle management."""
    from .constants import QC_KEY, QC_NAME, QC_ONAME, QC_CLASSIFICATION, QC_LEVEL

    async def _per_model(model_id: str) -> list:
        assets = await _client().get_tagged_assets(model_id)
        return [
            {"key": a.get(QC_KEY), "name": a.get(QC_ONAME) or a.get(QC_NAME), "classification": a.get(QC_CLASSIFICATION), "level_ref": a.get(QC_LEVEL), "model_id": model_id}
            for a in assets
        ]
    return await _client()._fan_out(facility_id, _per_model)


@mcp.tool()
@log_tool
async def get_element(facility_id: str, element_key: str, model_id: str | None = None) -> Any:
    """Get full details for a single element by its key. If model_id is not provided, uses the default model."""
    mid = model_id or get_default_model_id(facility_id)
    return await _client().get_element(mid, element_key)


@mcp.tool()
@log_tool
async def list_elements(
    model_id: str,
    column_families: list[str] | None = None,
    columns: list[str] | None = None,
    element_ids: list[str] | None = None,
) -> list:
    """Query elements from a model with optional filters. Column families: 'n'=standard, 'z'=DT props, 'r'=source, 'l'=refs, 'x'=xrefs, 'm'=systems, 's'=status."""
    families = column_families or [COLUMN_FAMILIES_STANDARD]
    return await _client().get_elements(model_id, element_ids=element_ids, column_families=families, columns=columns)


@mcp.tool()
@log_tool
async def list_systems(facility_id: str) -> list:
    """List all MEP systems (HVAC, plumbing, electrical, fire protection, etc.) across all models."""
    from .constants import QC_KEY, QC_NAME, QC_ONAME, QC_OSYSTEM_CLASS, QC_SYSTEM_CLASS, system_class_to_list

    async def _per_model(model_id: str) -> list:
        systems = await _client().get_systems(model_id)
        return [
            {
                "key": s.get(QC_KEY),
                "name": s.get(QC_ONAME) or s.get(QC_NAME),
                "classes": system_class_to_list(f) if (f := s.get(QC_OSYSTEM_CLASS) or s.get(QC_SYSTEM_CLASS)) else [],
                "model_id": model_id,
            }
            for s in systems
        ]
    return await _client()._fan_out(facility_id, _per_model)


@mcp.tool()
@log_tool
async def list_streams(facility_id: str) -> list:
    """List all IoT streams (sensors/data channels) across all models in a facility."""
    from .constants import QC_KEY, QC_NAME, QC_ONAME

    async def _per_model(model_id: str) -> list:
        streams = await _client().get_streams(model_id)
        return [
            {"key": s.get(QC_KEY), "name": s.get(QC_ONAME) or s.get(QC_NAME), "model_id": model_id}
            for s in streams
        ]
    return await _client()._fan_out(facility_id, _per_model)


@mcp.tool()
@log_tool
async def get_stream_data(
    model_id: str,
    stream_key: str,
    from_date: int | None = None,
    to_date: int | None = None,
) -> Any:
    """Get time-series data for a stream. Dates are Unix timestamps in milliseconds. Returns sensor readings over the time range."""
    return await _client().get_stream_data(model_id, stream_key, from_date, to_date)


@mcp.tool()
@log_tool
async def get_stream_last_reading(model_id: str, stream_keys: list[str]) -> Any:
    """Get the latest reading for one or more streams. Quick way to check current sensor status."""
    return await _client().get_stream_last_reading(model_id, stream_keys)


@mcp.tool()
@log_tool
async def list_tickets(facility_id: str) -> list:
    """List all tickets (work orders/issues) across all models in a facility."""
    from .constants import QC_KEY, QC_NAME, QC_ONAME, QC_PRIORITY

    async def _per_model(model_id: str) -> list:
        tickets = await _client().get_tickets(model_id)
        return [
            {"key": t.get(QC_KEY), "name": t.get(QC_ONAME) or t.get(QC_NAME), "priority": t.get(QC_PRIORITY), "model_id": model_id}
            for t in tickets
        ]
    return await _client()._fan_out(facility_id, _per_model)


@mcp.tool()
@log_tool
async def get_facility_history(
    facility_id: str,
    min_timestamp: int | None = None,
    max_timestamp: int | None = None,
    include_changes: bool = True,
) -> Any:
    """Get change history for a facility. Timestamps in milliseconds. Shows who changed what and when."""
    inputs: dict[str, Any] = {"includeChanges": include_changes}
    if min_timestamp is not None:
        inputs["min"] = min_timestamp
    if max_timestamp is not None:
        inputs["max"] = max_timestamp
    return await _client().get_facility_history(facility_id, inputs)


@mcp.tool()
@log_tool
async def list_views(facility_id: str) -> Any:
    """List saved views for a facility."""
    return await _client().get_views(facility_id)


# ═══════════════════════════════════════════════════════════════════════
# SPATIAL QUERY TOOLS (composite — multiple API calls)
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
@log_tool
async def list_rooms_on_level(facility_id: str, level_name: str) -> list:
    """Find all rooms on a given level/floor. Searches by level name (case-insensitive partial match). Example: 'Level 3', 'Floor 2', 'B1'."""
    return await _client().get_rooms_on_level(facility_id, level_name)


@mcp.tool()
@log_tool
async def list_assets_on_level(facility_id: str, level_name: str) -> list:
    """Find all tagged assets on a given level/floor. Use this to answer 'what equipment is on Floor 3?'."""
    return await _client().get_assets_on_level(facility_id, level_name)


@mcp.tool()
@log_tool
async def list_elements_in_room(facility_id: str, room_name: str) -> list:
    """Find all elements in a given room/space. Searches by room name (case-insensitive partial match). Example: 'Server Room', 'Lobby', '201'."""
    return await _client().get_elements_in_room(facility_id, room_name)


@mcp.tool()
@log_tool
async def list_streams_in_room(facility_id: str, room_name: str) -> list:
    """Find all IoT streams/sensors associated with a room. Use this to find what sensor data is available for a space."""
    return await _client().get_streams_in_room(facility_id, room_name)


@mcp.tool()
@log_tool
async def find_element_location(facility_id: str, element_name: str) -> list:
    """Find an element by name and return its location (level + room). Use this to answer 'where is pump P-101?'. Searches case-insensitively."""
    return await _client().find_element_location(facility_id, element_name)


# ═══════════════════════════════════════════════════════════════════════
# SYSTEM QUERY TOOLS (composite — multiple API calls)
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
@log_tool
async def list_systems_by_class(facility_id: str, class_filter: str) -> list:
    """Filter systems by class. Examples: 'Supply Air', 'HVAC', 'Power', 'Fire Protection', 'Domestic Hot Water'. 'HVAC' matches all air and hydronic systems."""
    return await _client().get_systems_by_class(facility_id, class_filter)


@mcp.tool()
@log_tool
async def list_system_elements(facility_id: str, system_name: str) -> list:
    """Get all elements belonging to a named system. Example: 'AHU-1 Supply Air'. Returns elements across all models."""
    return await _client().get_system_elements(facility_id, system_name)


@mcp.tool()
@log_tool
async def list_systems_serving_room(facility_id: str, room_name: str) -> list:
    """Find all systems that have member elements in a given room. Use this to answer 'what systems serve the data center?'."""
    return await _client().get_systems_serving_room(facility_id, room_name)


# ═══════════════════════════════════════════════════════════════════════
# SPATIAL SYSTEM ANALYSIS TOOLS (system ↔ room/level relationships)
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
@log_tool
async def list_rooms_served_by_system(facility_id: str, system_name: str) -> list:
    """Find all rooms that a named system touches — the reverse of list_systems_serving_room. Returns each room with a count of how many system member elements are in it. Use this to answer 'what rooms does AHU-1 Supply Air serve?'. Searches system name case-insensitively."""
    return await _client().get_rooms_served_by_system(facility_id, system_name)


@mcp.tool()
@log_tool
async def get_system_spatial_coverage(facility_id: str, system_name: str) -> dict:
    """Get a spatial coverage summary for a system — which levels and rooms it reaches, with element counts. Returns a hierarchy: system → levels → rooms, showing how many member elements exist at each location. Use this for HVAC coverage analysis, e.g. 'how does the supply air system cover the building?'."""
    return await _client().get_system_spatial_coverage(facility_id, system_name)


# ═══════════════════════════════════════════════════════════════════════
# ASSET INTELLIGENCE TOOLS (composite — schema-aware)
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
@log_tool
async def get_model_schema(model_id: str, family_filter: str | None = None) -> Any:
    """Get the column schema for a model — maps qualified columns (e.g. 'z:iAs') to human-readable names. Use family_filter='z' to get only DT/Maximo properties. This is essential for interpreting z: property values."""
    client = _client()
    if family_filter:
        return await client._build_schema_map(model_id, family_filter)
    return await client.get_model_schema(model_id)


@mcp.tool()
@log_tool
async def list_tagged_assets_with_properties(
    facility_id: str,
    model_id: str | None = None,
    include_empty: bool = False,
) -> list:
    """List all tagged assets with their DT/Maximo properties decoded to human-readable names. Set include_empty=true to include assets without DT properties. This is the go-to tool for asset inventory with lifecycle data."""
    return await _client().get_tagged_assets_with_properties(facility_id, model_id, include_empty)


@mcp.tool()
@log_tool
async def list_assets_by_status(facility_id: str, status: str) -> list:
    """Filter tagged assets by Maximo status. Examples: 'OPERATING', 'DECOMMISSIONED', 'NOT READY'. Searches case-insensitively across any status-like property field."""
    return await _client().get_assets_by_status(facility_id, status)


@mcp.tool()
@log_tool
async def list_aging_assets(
    facility_id: str,
    max_remain_life: float | None = None,
    include_decommissioned: bool = True,
) -> list:
    """Find assets nearing end of life. Filters by RemainLife <= max_remain_life (years). Returns results sorted by remaining life ascending. If max_remain_life is omitted, returns all assets with lifecycle data. The #1 capital planning query."""
    return await _client().get_aging_assets(facility_id, max_remain_life, include_decommissioned)


@mcp.tool()
@log_tool
async def list_assets_by_classification(facility_id: str, classification: str) -> list:
    """Filter tagged assets by classification code or name. Examples: '11.ME.AHU' for Air Handling Units, '11.ME.CRU' for CRACs, 'AHU' for partial match. Includes DT/Maximo properties in results."""
    return await _client().get_assets_by_classification(facility_id, classification)


@mcp.tool()
@log_tool
async def get_asset_detail(facility_id: str, element_key: str, model_id: str | None = None) -> dict:
    """Get full details for a single asset with ALL properties decoded — standard, DT/Maximo, source/Revit — with human-readable field names. Also resolves level and room names. This is the best tool for drilling into a specific asset."""
    return await _client().get_asset_detail(facility_id, element_key, model_id)


@mcp.tool()
@log_tool
async def get_maximo_column_mapping(facility_id: str) -> dict:
    """Get a lightweight mapping of Maximo property names to their qualified column codes for a facility. Returns e.g. {'RemainLife': 'z:iAs', 'DesignLife': 'z:gQs', ...}. Use this to quickly understand which columns to request and how to interpret z: property values without fetching the full schema."""
    return await _client().get_maximo_column_mapping(facility_id)


# ═══════════════════════════════════════════════════════════════════════
# WRITE TOOLS
# ═══════════════════════════════════════════════════════════════════════


@mcp.tool()
@log_tool
async def mutate_elements(
    model_id: str,
    keys: list[str],
    mutations: list[list],
    description: str,
) -> Any:
    """Update properties on one or more elements. Each mutation is [action, family, column, value]. Actions: 'i'=insert, 'c'=insert-if-different, 'd'=delete. Example: [['i', 'n', 'n', 'New Name']] to rename."""
    return await _client().mutate_elements(model_id, keys, mutations, description)


@mcp.tool()
@log_tool
async def create_element(
    model_id: str,
    mutations: list[list],
    description: str,
) -> Any:
    """Create a new element in a model. Provide mutations to set initial properties. Returns the new element key. Example for a generic asset: [['i','n','n','My Asset'], ['i','n','a', 16777221], ['i','n','c', 1120]]."""
    return await _client().create_element(model_id, mutations, description)


@mcp.tool()
@log_tool
async def create_ticket(
    facility_id: str,
    name: str,
    priority: int = 0,
    description: str = "Create ticket",
) -> Any:
    """Create a new ticket (work order/issue) in the facility's default model. Priority: 0=none, 1=low, 2=medium, 3=high, 4=critical."""
    model_id = get_default_model_id(facility_id)
    mutations = [
        [MUTATE_ACTIONS_INSERT, COLUMN_FAMILIES_STANDARD, COLUMN_NAMES_NAME, name],
        [MUTATE_ACTIONS_INSERT, COLUMN_FAMILIES_STANDARD, COLUMN_NAMES_ELEMENT_FLAGS, ELEMENT_FLAGS_TICKET],
        [MUTATE_ACTIONS_INSERT, COLUMN_FAMILIES_STANDARD, "pr", priority],
    ]
    return await _client().create_element(model_id, mutations, description)
