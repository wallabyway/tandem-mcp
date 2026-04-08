# Tandem MCP — LLM Agent Retrospective

> **Date:** 2026-04-07
> **Session Goal:** Explore TBIT (LAX) facility assets via the Tandem MCP, identify aging HVAC equipment using Maximo lifecycle data.

---

## 1. What Worked Well

### Facility Discovery Flow
The `list_groups` → `list_group_facilities` chain worked cleanly. A single call to each produced the full picture: 9 facilities in the LAX campus, with model IDs, building names, templates, and creation dates. This matches the KB's recommended query strategy and required no guesswork.

### Tagged Asset Inventory
`list_tagged_assets` returned all 199 HVAC assets across 8 models in one call. The response included element keys, names, classification codes, level references, and model IDs — enough to categorize and count equipment types without additional calls.

### Maximo Template Discovery
`get_facility_template` returned the full Maximo Solution property set with UUIDs, data types, and classification hierarchy. This revealed the exact fields we needed: `RemainLife`, `DesignLife`, `YRBuilt`, `HealthScore`, `StatusDescription`.

### DT Properties via list_elements
Once we discovered that `column_families: ["n", "z"]` was needed, `list_elements` with specific `element_ids` returned the full Maximo data. This was the breakthrough that unlocked the lifecycle analysis.

---

## 2. What Was Painful

### Getting DT Properties Required Trial and Error
The default `get_element` tool returns only standard (`n:`), refs (`l:`), and xrefs (`x:`) families. The Maximo lifecycle data lives in the `z:` (DtProperties) family, which is **not returned by default**. It took 6+ failed attempts across different tool names and parameter combinations before discovering that `list_elements` with `column_families: ["n", "z"]` was the correct approach.

### Opaque Qualified Column Names
The `z:` properties come back as short encoded IDs like `z:iAs`, `z:gQs`, `z:jAs`. There is no tool to map these to their human-readable Maximo names (RemainLife, DesignLife, YRBuilt). The agent had to manually correlate values against the template UUIDs and infer the mapping from data patterns (e.g., `z:jAs` = "2013" is likely YRBuilt, `z:9wo` = "OPERATING" is likely StatusDescription).

### No Filtering on DT Properties
To find decommissioned or low-remaining-life assets, the agent had to:
1. Get all tagged asset keys from `list_tagged_assets`
2. Batch those keys into `list_elements` calls with `column_families: ["n", "z"]`
3. Manually inspect the returned `z:` properties to find status and lifecycle fields

This required multiple round-trips with hand-picked element IDs. A filtered query (e.g., "all assets where status = DECOMMISSIONED") would have been a single call.

### Many Assets Not Synced to Maximo
Of ~199 tagged assets, only ~28 had full Maximo property data populated. The rest had minimal data (just a room code). There was no way to know this upfront — the agent had to query a sample and discover the gap empirically.

### Stream Data Was Empty
Both TBIT streams ("Test" and "Heat Map") returned empty data. The agent correctly queried `get_stream_last_reading` and `get_stream_data`, but there was no way to know streams were empty without calling both tools.

### Tool Schema Discovery Was Blind
The MCP server's tools directory was empty (no JSON descriptor files). The agent had to guess parameter names, get validation errors, and iterate. For example: `stream_key` vs `stream_keys`, `group_urn` vs `group_id`, the need for `facility_id` on `get_element`.

---

## 3. Key Domain Knowledge Acquired

### Tandem Property Families
| Family | Prefix | Contains |
|--------|--------|----------|
| Standard | `n:` | Name, classification, category, flags |
| DtProperties | `z:` | User-defined / Maximo-synced properties |
| Refs | `l:` | Level, room, parent, family type refs |
| Xrefs | `x:` | Cross-model references |
| Systems | `m:` | System membership |
| Source | `r:` | Original Revit/IFC properties |
| Status | `s:` | Element status flags |

### Maximo → Tandem Column Mapping (TBIT)
| Maximo Field | Tandem Column | Data Type | Example |
|---|---|---|---|
| RemainLife | `z:iAs` | Double | 8.47 |
| DesignLife | `z:gQs` | Double | 20 |
| YRBuilt | `z:jAs` | String | "2013" |
| HealthScore | `z:ggs` | Double | 1656 |
| StatusDescription | `z:9wo` | String | "OPERATING" |
| Description | `z:6Ao` | String | "Air Handling Unit" |
| PluscmodelNum | `z:_Ao` | String | "EPQN-270" |
| AssetId (tag) | `z:hws` | String | "TERTBTAHU005" |
| SerialNum | `z:7go` | String | "THXM377610" |
| OrgId | `z:zAo` | String | "LAWA" |
| SiteId | `z:_Qo` | String | "TERTBT" |
| Priority | `z:5Qo` | Integer | 4 |
| Maximo ID | `z:lQs` | Integer | 11864 |
| ClassstructureId | `z:6Qo` | String | "104315" |
| FailureCode / Uniformat | `z:hAs` | String | "D3052" |
| ChangeBy | `z:hQs` | String | "MAXADMIN" |
| SystemNum | `z:_go` | String | "HVAC" |

> **Note:** These column IDs are model-specific. Other models or facilities may use different short codes. Always retrieve the schema to build the mapping.

### Maximo Classification Hierarchy (Mechanical Equipment)
The relevant subcategories for HVAC lifecycle analysis:
- `11.ME.AHU` — Air Handling Unit (DesignLife: 20 yr)
- `11.ME.CRU` — Computer Room Air Conditioner (DesignLife: 15 yr)
- `11.ME.MAU` — Makeup Air Unit
- `11.ME.FCU` — Fan Coil Unit
- `11.ME.CU` — Condensing Unit
- `11.ME.FE` — Exhaust Fan

---

## 4. Suggested New MCP Tools

The following tools would dramatically reduce the number of calls and eliminate the guesswork that dominated this session.

### Tool 1: `get_model_schema`
**Purpose:** Return the qualified column mapping for a model — translates `z:iAs` → `RemainLife`, `z:gQs` → `DesignLife`, etc.

```
Parameters:
  model_id: str           — required
  family_filter: str      — optional, e.g. "z" to get only DT properties

Returns:
  List of { id, family, column, name, category, dataType, description }
```

**Why:** This is the single most impactful missing tool. Without it, agents cannot interpret `z:` property values. The Tandem REST API already exposes this via `GET /modeldata/{modelId}/schema` — it just needs to be wrapped.

---

### Tool 2: `list_tagged_assets_with_properties`
**Purpose:** Combine `list_tagged_assets` + `list_elements` with `z:` family in one call. Returns asset data with all DT (Maximo) properties included.

```
Parameters:
  facility_id: str        — required
  model_id: str           — optional (all models if omitted)
  include_empty: bool     — optional, default false (skip assets with no DT props)

Returns:
  List of assets with standard props + DT props, with human-readable field names
```

**Why:** This session required 4+ calls to achieve what this single tool would do. It's the most common Maximo integration query.

---

### Tool 3: `list_assets_by_status`
**Purpose:** Filter tagged assets by their Maximo status (OPERATING, DECOMMISSIONED, NOT READY, etc.).

```
Parameters:
  facility_id: str        — required
  status: str             — required, e.g. "DECOMMISSIONED"

Returns:
  List of matching assets with key lifecycle fields
```

**Why:** The "what needs replacement?" question is the #1 facility management query. Currently requires fetching all assets, then client-side filtering.

---

### Tool 4: `list_aging_assets`
**Purpose:** Find assets where RemainLife is below a threshold or DesignLife has been exceeded.

```
Parameters:
  facility_id: str        — required
  max_remain_life: float  — optional, e.g. 5.0 (years)
  include_decommissioned: bool — optional, default true

Returns:
  List of assets sorted by RemainLife ascending, with Maximo lifecycle fields
```

**Why:** This is the core capital planning query. An agent shouldn't need to fetch 199 assets, batch-query their z: properties, infer the column mapping, and manually sort — it should be a single call.

---

### Tool 5: `list_assets_by_classification`
**Purpose:** Filter tagged assets by Maximo category code (e.g., `11.ME.AHU`, `11.ME.CRU`).

```
Parameters:
  facility_id: str        — required
  classification: str     — required, e.g. "11.ME.CRU" or partial "11.ME" for all mechanical

Returns:
  List of matching assets with standard + lifecycle props
```

**Why:** Facility managers think in terms of equipment types, not element keys. "Show me all my CRUs" is a natural question that currently requires fetching everything and filtering.

---

### Tool 6: `get_asset_detail`
**Purpose:** Get a single asset with ALL properties decoded — standard, DT/Maximo, refs, source — with human-readable field names instead of qualified columns.

```
Parameters:
  facility_id: str        — required
  element_key: str        — required
  model_id: str           — optional

Returns:
  {
    name, classification, level, room, status,
    maximo: { assetId, description, manufacturer, modelNum, serialNum,
              yrBuilt, designLife, remainLife, healthScore, status, ... },
    source: { revit_family, revit_type, ... }
  }
```

**Why:** `get_element` returns raw qualified columns. A new agent has no way to interpret `z:iAs: 8.47` without the schema mapping. This tool does the translation.

---

### Tool 7: `get_maximo_column_mapping`
**Purpose:** Lightweight alternative to full schema — returns just the Maximo property name ↔ qualified column mapping for a facility.

```
Parameters:
  facility_id: str        — required

Returns:
  { "RemainLife": "z:iAs", "DesignLife": "z:gQs", "YRBuilt": "z:jAs", ... }
```

**Why:** If a full `get_model_schema` is too heavy, this focused mapping lets agents immediately understand which columns to request and how to interpret responses.

---

## 5. Priority Ranking for Tool Implementation

| Priority | Tool | Impact | Effort |
|----------|------|--------|--------|
| **P0** | `get_model_schema` | Unlocks all DT property interpretation | Low (API already exists) |
| **P0** | `list_tagged_assets_with_properties` | Eliminates the most common multi-call pattern | Medium |
| **P1** | `list_aging_assets` | Direct answer to the #1 FM question | Medium |
| **P1** | `get_asset_detail` | Makes single-asset queries instantly useful | Medium |
| **P2** | `list_assets_by_status` | Filtered queries save round-trips | Low |
| **P2** | `list_assets_by_classification` | Category-based filtering | Low |
| **P3** | `get_maximo_column_mapping` | Convenience shortcut | Low |

---

## 6. Other Improvements

### Populate Tool Descriptors
The MCP tools directory was empty — no JSON schema files were generated. New agents had no way to discover available tools or their parameter signatures without calling them and reading validation errors. Ensure `FastMCP` exports tool descriptors to the file system.

### Include z: Family in get_element by Default
The current `get_element` only returns `n:`, `l:`, `x:` families. For tagged assets (where `n:ia = 1`), the DT properties are almost always what the user is asking about. Consider returning `z:` by default for assets, or adding an `include_dt_properties` flag.

### Add Property Name Resolution to list_elements
When `column_families` includes `"z"`, optionally resolve the qualified column names to human-readable names in the response. This avoids the need for a separate schema call.

### Batch Asset Queries Across Models
Tools like `list_tagged_assets` already iterate all models, but `list_elements` operates on a single model. For facilities with 26 models like TBIT, querying DT properties requires knowing which model each asset belongs to and batching accordingly. A facility-level asset property query would be much more efficient.
