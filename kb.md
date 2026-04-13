# Tandem MCP Knowledge Base

> **Purpose**: This file is read by the LLM before executing any Tandem tools. It provides domain context so the LLM can translate natural-language facility questions into correct API calls. This is a living document — add to it as you learn more about the domain, personas, and query patterns.

---

## 1. Glossary

### BIM & Digital Twin Terms

| Term | Definition |
|------|-----------|
| **BIM** | Building Information Modeling — a 3D model-based process that gives architecture, engineering, and construction (AEC) professionals the tools to plan, design, construct, and manage buildings and infrastructure. |
| **Digital Twin** | A virtual replica of a physical facility, kept in sync with real-world conditions through IoT sensors, manual updates, and imported BIM models. Tandem is Autodesk's digital twin platform. |
| **IFC** | Industry Foundation Classes — an open, vendor-neutral data schema for describing building and construction data. Tandem's classification system is rooted in IFC concepts. |
| **Revit** | Autodesk's BIM authoring tool. Most Tandem models originate as Revit exports. Revit categories (e.g., Mechanical Equipment, Ducts) map to Tandem category IDs. |
| **Facility** | A building, campus, or site managed as a single entity in Tandem. A facility contains one or more **models** (BIM files). A facility has a URN like `urn:adsk.dtt:{id}`. |
| **Model** | A single BIM file imported into a facility. Each model has its own element namespace. A model has a URN like `urn:adsk.dtm:{id}`. A facility's "default model" shares the same ID as the facility (replace `dtt` with `dtm`). |
| **Element** | Any object in a model — a wall, door, pipe, sensor, room, level, system, ticket, or generic asset. Every element has a unique **key** (base64-encoded 20-byte ID). |
| **Asset** | An element that has been "tagged" for tracking (maintenance, lifecycle, etc.). Not all elements are assets — only those explicitly marked with `is_asset = true`. Assets are the primary focus of facility management workflows. |
| **Level** | A floor/storey in a building. Elements reference their level. Levels are logical elements (flag `0x01000001`). |
| **Room / Space** | An enclosed area on a level. Rooms have boundaries and can contain equipment. Elements reference their room(s) via the `l:r` (refs:rooms) column. In IFC, these are called **IfcSpace**. |
| **Stream** | An IoT data channel — a logical element (flag `0x01000003`) that receives time-series sensor data. Streams are linked to physical assets and spaces. |
| **System** | A connected group of BIM elements that form a functional unit — e.g., an HVAC supply air system, a hot water plumbing loop, or an electrical power circuit. Systems can span multiple models and buildings. |
| **Ticket** | A work order or issue (flag `0x01000007`). Has priority, open/close dates, and links to affected elements. Analogous to a Maximo work order. |
| **Classification** | A hierarchical taxonomy applied to elements. In Tandem, this is typically **Uniformat II** or **OmniClass** based, stored in the facility template. |
| **Uniformat II** | A classification system for building elements organized by functional systems (e.g., D3050 = Terminal & Package Units, D7070 = Sensors). Used for the `uniformat_class` field on elements. |
| **OmniClass** | A broader construction classification system. Tables 21 (Elements) and 23 (Products) are most relevant. |
| **Family Type** | A Revit concept — the template/definition an element instance is based on (e.g., "VAV Box - 12in" is a family type; each installed unit is an instance). |
| **Column Family** | Tandem's internal data grouping. Think of it like a database column family: `n` = standard props, `z` = DT properties, `r` = source/Revit props, `l` = local refs, `x` = cross-model refs, `m` = system membership, `s` = status. |
| **Qualified Column** | A `family:column` identifier like `n:n` (standard:name) or `l:r` (refs:rooms). Used in scan queries to fetch specific data. |
| **Mutation** | A write operation expressed as `[action, family, column, value]`. Actions: `i` = insert, `c` = insert if different, `d` = delete value, `a` = delete entire row. |
| **Group** | An organizational container for facilities at the account level. Think "portfolio" or "campus". |
| **Template** | A facility's schema definition — contains classification hierarchies, property set definitions, and custom attributes. |

### MEP System Classes

Systems in Tandem are categorized by class. The system class is stored as a bitmask. The recognized system classes are:

| Class | Typical Examples |
|-------|-----------------|
| Supply Air | AHU supply ducts, VAV boxes, diffusers |
| Return Air | Return ducts, return grilles |
| Exhaust Air | Exhaust fans, kitchen hoods |
| Hydronic Supply | Chilled water supply, hot water supply pipes |
| Hydronic Return | Chilled/hot water return pipes |
| Domestic Hot Water | Hot water heaters, HW pipes, mixing valves |
| Domestic Cold Water | Cold water mains, CW pipes |
| Sanitary | Waste pipes, floor drains, sanitary fixtures |
| Power | Electrical panels, circuits, transformers |
| Vent | Plumbing vents |
| Controls | BAS/BMS control points, actuators |
| Fire Protection Wet | Sprinkler mains, wet risers |
| Fire Protection Dry | Dry risers, dry standpipes |
| Fire Protection Pre-Action | Pre-action sprinkler systems |
| Communication | Comm backbone, data jacks |
| Data Circuit | Network switches, data runs |
| Telephone | Phone lines, PBX |
| Security | Access control, CCTV |
| Fire Alarm | Detectors, pull stations, NAC panels |
| Nurse Call | Patient call systems |
| Cable Tray Conduit | Cable trays, conduit runs |
| Storm | Storm drains, roof drains |

---

## 2. Spatial Hierarchy & Relationships

Understanding how space is organized in Tandem is critical for answering location-based questions.

```
Facility (building/campus)
 └── Model (BIM file — may be one per discipline: Arch, MEP, Struct)
      └── Level (floor/storey — logical element)
           └── Room / Space (enclosed area on a level)
                └── Elements (equipment, fixtures, sensors inside the room)
```

### Key spatial relationships in the data model:

| Relationship | How it's stored | Column |
|-------------|----------------|--------|
| Element → Level | Element has a `level` ref pointing to a level key | `l:l` (refs:level) |
| Element → Room(s) | Element has `rooms` ref (encoded key array) | `l:r` (refs:rooms) or `x:r` (xrefs:rooms for cross-model) |
| Room → Level | Room element has a `level` ref | `l:l` |
| System → Elements | Elements have system membership columns in the `m` (systems) family | `m:{system_id}` |
| Element → Parent | Hosted elements reference their parent (e.g., outlet on wall) | `l:p` (refs:parent) or `x:p` (xrefs:parent) |
| Stream → Room | Stream has xref to room | `x:r` |
| Stream → Level | Stream has ref to level | `l:l` |

### Cross-model references (xrefs)

A facility often has multiple models (Architectural, MEP, Structural). Elements can reference rooms or parents in a different model via **xrefs** (`x:` family). An xref key = 16-byte model ID + 24-byte element key. This is how an MEP element (in the MEP model) can reference a room (in the Architectural model).

### Common spatial queries and how to execute them:

| Question | Tool sequence |
|----------|--------------|
| "What rooms are on Level 3?" | `list_levels` → find Level 3 key → `list_rooms` → filter rooms where `l:l` == level key |
| "What equipment is in Room 201?" | `list_rooms` → find Room 201 key → `list_elements` with refs family → filter where `l:r` contains room key |
| "What assets are on this floor?" | `list_levels` → find level key → `list_tagged_assets` → filter where `l:l` == level key |
| "Where is pump P-101?" | `list_elements` → search by name → read `l:l` for level and `l:r` for room |
| "What's the IoT data for this room?" | Find room → `list_streams` → filter streams with `x:r` matching room → `get_stream_data` |

---

## 3. Systems & Connected Infrastructure

Systems represent functional networks of connected building elements. They are critical for:
- Understanding how buildings work (airflow, water flow, power distribution)
- Troubleshooting — if a VAV box is failing, what system is it part of? What else is on that system?
- Maintenance planning — scheduling system-wide inspections

### System hierarchy:
```
System (e.g., "AHU-1 Supply Air")
 ├── Subsystem (optional nesting)
 ├── Element: Supply Duct (model A)
 ├── Element: VAV Box (model A)
 ├── Element: Diffuser (model B)  ← cross-model membership
 └── Element: Thermostat/Sensor (stream)
```

### How system membership works:
- Each system has a **system ID** derived from its element key
- Member elements have a column in the `m` (systems) family: `m:{system_id}`
- Elements can belong to **multiple systems**
- System class bitmask on the system element defines what type of system it is
- Member elements also have a system class bitmask — the match between system filter and element class determines membership

### Common system queries:

| Question | Tool sequence |
|----------|--------------|
| "What systems serve this room?" | Find room → find elements in room → check their `m:` columns → resolve system names |
| "List all HVAC systems" | `list_systems` → filter by system class (Supply Air, Return Air, Exhaust Air, Hydronic) |
| "What elements are in System X?" | `list_elements` with systems family → filter where `m:{system_id}` exists |
| "What's the system topology?" | `list_systems` → check parent refs → build hierarchy tree |

---

## 4. Classification System

Tandem uses a hierarchical classification system stored in the **facility template**. Classifications are typically based on:

### Uniformat II (most common in Tandem)
```
A  SUBSTRUCTURE
  A10  Foundations
  A20  Basement Construction
B  SHELL
  B10  Superstructure
  B20  Exterior Enclosure
  B30  Roofing
C  INTERIORS
  C10  Interior Construction
  C20  Stairs
  C30  Interior Finishes
D  SERVICES
  D10  Conveying (elevators, escalators)
  D20  Plumbing
    D2010  Plumbing Fixtures
    D2020  Domestic Water Distribution
    D2030  Sanitary Waste
    D2040  Rain Water Drainage
    D2090  Other Plumbing Systems
  D30  HVAC
    D3010  Energy Supply (boilers, chillers)
    D3020  Heat Generating Systems
    D3030  Cooling Generating Systems
    D3040  Distribution Systems (ductwork, piping)
    D3050  Terminal & Package Units (VAV, FCU, unit heaters)
    D3060  Controls & Instrumentation
    D3070  Systems Testing & Balancing
    D3090  Other HVAC Systems
  D40  Fire Protection
  D50  Electrical
    D5010  Electrical Service & Distribution
    D5020  Lighting & Branch Wiring
    D5030  Communications & Security
    D5090  Other Electrical Systems
  D60  Data Communications
  D70  Electronic Safety & Security
    D7070  Sensors
E  EQUIPMENT & FURNISHINGS
F  SPECIAL CONSTRUCTION
G  BUILDING SITEWORK
```

### How classification works in Tandem:
1. The **facility template** defines available classifications (retrieved via `get_facility_template`)
2. Each element can have a classification assigned (`n:v` column)
3. Classifications enable filtering, reporting, and property set assignment
4. Property sets are associated with classifications — assigning a classification unlocks relevant properties

---

## 5. Personas & Use Cases

### Facility Manager
- **Concerns**: Building performance, tenant comfort, energy costs, regulatory compliance, capital planning
- **Typical questions**:
  - "How many assets do we have on Level 3?"
  - "Show me all HVAC equipment due for replacement"
  - "What's the temperature reading in the server room?"
  - "List all open tickets for Building A"
  - "What systems serve the cafeteria?"

### Facility Operator
- **Concerns**: Daily operations, alarm response, equipment status, comfort complaints
- **Typical questions**:
  - "What's the latest sensor reading for AHU-1?"
  - "Which VAV boxes are on the supply air system for Floor 5?"
  - "Show me stream data for the last 24 hours for the chiller"
  - "What equipment is in Mechanical Room 101?"
  - "Create a ticket for the broken pump in B2"

### BIM Manager
- **Concerns**: Model quality, data completeness, classification coverage, naming standards
- **Typical questions**:
  - "How many elements are unclassified?"
  - "List all family types in the MEP model"
  - "What properties are defined for classification D3050?"
  - "Show me the facility template structure"
  - "Which elements are missing room assignments?"

### Maintenance Technician / Crew
- **Concerns**: Work orders, equipment location, repair history, parts
- **Typical questions**:
  - "Where is asset TAG-12345?"
  - "What floor and room is pump P-101 in?"
  - "Show me the maintenance history for this asset"
  - "What's the priority on ticket #4521?"
  - "List all open tickets assigned to mechanical systems"

### Integration with CMMS (e.g., Maximo, ServiceNow)
- Tandem **tickets** map to CMMS **work orders**
- Tandem **assets** map to CMMS **asset records**
- Tandem **streams** provide real-time data that triggers CMMS preventive/predictive maintenance
- Common integration pattern: stream threshold exceeded → create Tandem ticket → sync to Maximo work order
- The `correlation_id` on mutations enables tracking changes across systems

### Daily Activities (Maximo-style workflows)
- **Preventive Maintenance (PM)**: Scheduled tasks (filter changes, belt inspections) tied to assets by classification
- **Corrective Maintenance (CM)**: Break-fix work triggered by tickets or alarms
- **Rounds/Inspections**: Technicians walk floors checking equipment — spatial queries help plan routes
- **Condition Monitoring**: Stream data (temperature, vibration, pressure) monitored for anomalies

---

## 6. Query Strategy Guide

When the LLM receives a natural-language question about a facility, use this decision tree:

### Step 1: What are they asking about?
- **A specific asset by Maximo identifier** (e.g., "TERTBTEXF012") → see "Resolving Maximo identifiers" in Section 7. Do NOT use `find_element_location` — it only searches BIM element names, not Maximo property values.
- **A specific asset with full details** → `get_asset_detail` (requires Tandem element key, not a Maximo ID)
- **A specific element by BIM name** → `find_element_location` (searches the element `name` field, e.g., "AIRHANDLER", "Pump P-101")
- **Asset lifecycle / aging / replacement** → `list_aging_assets` (filters by RemainLife)
- **Assets by status (operating, decommissioned)** → `list_assets_by_status`
- **Assets by equipment type** → `list_assets_by_classification` (e.g., "AHU", "11.ME.CRU")
- **All assets with Maximo data** → `list_tagged_assets_with_properties`
- **Everything on a floor/level** → `list_assets_on_level` or `list_rooms_on_level`
- **Everything in a room** → `list_elements_in_room`
- **A system or connected equipment** → `list_systems_by_class`, `list_system_elements`
- **Sensor/IoT data** → `list_streams` → `get_stream_data` or `get_stream_last_reading`
- **Work orders/issues** → `list_tickets`, `create_ticket`
- **Building overview/structure** → `get_facility`, `list_levels`, `list_rooms`
- **Schema/column mapping** → `get_model_schema` (critical for interpreting `z:` properties)
- **Classification/template info** → `get_facility_template`

### Step 2: Do you have the facility URN?
- If no → `list_groups` → `list_group_facilities` → pick the facility
- If yes → proceed to the relevant query
- **Cost tip**: `list_group_facilities` returns all facility metadata (building names, model lists, addresses, templates) in a single call. Do NOT call `get_facility` on each facility individually to find the right one — that costs N calls instead of 1.
- **Narrowing scope**: When a query spans all facilities (e.g., "find the oldest AHU"), don't blindly search every facility. Check the `template` field in `list_group_facilities` results first — only facilities with a Maximo-type template (e.g., `"name": "Maximo Solution"`) will have lifecycle data like YRBuilt, RemainLife, and DesignLife. Skip facilities with `template: null` for asset/lifecycle queries.

### Step 3: Do you need model IDs?
- Most element queries require a **model ID**, not a facility ID
- `get_facility` returns `links[]` with `modelId` for each model
- The **default model** ID = facility ID with `dtt` replaced by `dtm`
- For cross-model queries, iterate all models

### Step 4: Interpret the results
- Element keys are base64-encoded — use them as opaque identifiers
- Room references (`l:r`) are encoded key arrays — need decoding to get individual room keys
- System membership is in the `m:` family columns
- Names may be in `n:n` (current name) or `n:!n` (original name from Revit)
- Properties prefixed with `!` are "original" (from source model), unprefixed are "current" (may be overridden)

---

## 7. DT Properties & Maximo Integration (the `z:` family)

### Critical: The `z:` column family

The **DtProperties** family (`z:`) stores user-defined and CMMS-synced properties — this is where Maximo lifecycle data lives. It is **not returned by default** in most queries. You must explicitly request it.

- Use `column_families: ["n", "z"]` (or `["n", "z", "l"]` if you also need refs)
- The `get_element` and `get_asset_detail` tools include `z:` automatically
- `list_tagged_assets_with_properties` returns assets with all DT properties decoded

### Opaque column IDs

Properties in the `z:` family have short encoded IDs like `z:iAs`, `z:gQs`, `z:jAs`. These are **model-specific** — the same Maximo field may have a different column ID in each model. To decode them:

1. Call `get_model_schema` to get the column-to-name mapping
2. Or use `get_asset_detail` which does the translation automatically

### Common Maximo fields you'll encounter

| Maximo Field | Meaning | Data Type | Example |
|---|---|---|---|
| RemainLife | Remaining useful life (years) | Double | 8.47 |
| DesignLife | Expected total lifespan (years) | Double | 20 |
| YRBuilt | Year installed | String | "2013" |
| HealthScore | Condition score | Double | 90 |
| StatusDescription | Operating status | String | "OPERATING" |
| Description | Equipment description | String | "Air Handling Unit" |
| PluscmodelNum | Manufacturer model number | String | "YC-99X128X460" |
| AssetId | Numeric Maximo asset ID | Integer | 3067 |
| SystemNum | Maximo system identifier (site+type+number) | String | "TERTBTEXF012" |
| SerialNum | Serial number | String | "THXM377610" |
| OrgId | Organization | String | "LAWA" |
| SiteId | Site code | String | "LAX" |
| SaddressCode | Site/location prefix code | String | "TERTBT" |
| Priority | Work priority | Integer | 4 |
| FailureCode | Failure classification code | String | "HVAC" |
| ClassstructureId | Maximo classification structure ID | String | "1295" |
| TemplateId | Maximo PM template | String | "D3052" |

### Maximo classification hierarchy (Mechanical Equipment)

Facilities with Maximo integration use classification codes like these for HVAC:

| Code | Equipment Type | Typical DesignLife |
|------|---------------|-------------------|
| `11.ME.AHU` | Air Handling Unit | 20 years |
| `11.ME.CRU` | Computer Room Air Conditioner | 15 years |
| `11.ME.MAU` | Makeup Air Unit | 20 years |
| `11.ME.FCU` | Fan Coil Unit | 20 years |
| `11.ME.CU` | Condensing Unit | 15 years |
| `11.ME.FE` | Exhaust Fan | 25 years |

### Key patterns for Maximo queries

| Question | Tool to use |
|----------|------------|
| "What are all the Maximo fields for this asset?" | `get_asset_detail` — returns decoded field names |
| "Show me aging HVAC equipment" | `list_aging_assets` — filters by RemainLife threshold |
| "What's decommissioned?" | `list_assets_by_status` with status "DECOMMISSIONED" |
| "Show me all AHUs" | `list_assets_by_classification` with "11.ME.AHU" or "AHU" |
| "What Maximo columns are available?" | `get_model_schema` with family_filter "z" |
| "Get all assets with their Maximo data" | `list_tagged_assets_with_properties` |

### Data coverage warning

Not all tagged assets will have Maximo data populated. A facility may have 200 tagged assets but only 30 synced to Maximo. Assets without CMMS sync will have minimal `z:` properties (sometimes just a room code). There is no way to know upfront — query and check.

### Resolving Maximo identifiers to Tandem element keys

Users often refer to assets by their Maximo `SystemNum` (e.g., "TERTBTEXF012") rather than the internal Tandem element key. **`get_asset_detail` requires a Tandem element key** (base64-encoded), NOT a Maximo identifier. **`find_element_location` searches BIM element names** (e.g., "AIRHANDLER"), NOT Maximo property values — it will not find a Maximo SystemNum.

Resolution path:
1. Identify the target facility from the identifier's prefix (see naming conventions below)
2. Call `list_tagged_assets_with_properties` on that facility
3. Search the results for the identifier in the `SystemNum`, `AssetNum`, or `NewAssetNum` properties
4. Use the matching element's `key` field to call `get_asset_detail`

### LAWA asset naming conventions

LAWA (Los Angeles World Airports) uses a structured `SystemNum` format:

```
TERTBTEXF012
├── TER  = Terminal
├── TBT  = Tom Bradley Terminal (TBIT)
├── EXF  = Equipment type (Exhaust Fan)
└── 012  = Instance number
```

Common site prefixes and their facilities:

| Prefix | Facility |
|--------|----------|
| TERTBT | Tom Bradley International Terminal (TBIT) |
| TERT02 | Terminal 2 |
| TERT03 | Terminal 3 |
| TERT04 | Terminal 4 |
| TERT06 | Terminal 6 |
| TERT07 | Terminal 7 |

If a user provides an identifier starting with one of these prefixes, go directly to that facility — do not search all facilities.

---

## 8. Data Freshness & Caveats

- **Streams**: Real-time data. `get_stream_last_reading` for current state, `get_stream_data` for historical range.
- **Elements/Assets**: Updated when BIM model is re-imported or properties are manually changed via Tandem UI or API mutations.
- **Tickets**: Created/updated via API or Tandem UI. Check `open_date` and `close_date` for status.
- **History**: Available per-model and per-facility. Timestamps in **milliseconds** since Unix epoch.
- **Deleted elements**: Flagged with `ELEMENT_FLAGS_DELETED (0xfffffffe)`, not physically removed. Filter them out.
- **Multi-model**: Always check all models in a facility for complete results unless you know which model contains the data.
