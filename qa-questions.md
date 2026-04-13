# Tandem MCP — QA Test Prompts

Test prompts for validating tool coverage. Each section targets a tool category.
Prompts are written as natural-language questions an LLM agent would receive.

> **Setup:** The agent needs access to at least one facility with tagged assets,
> MEP systems, and (ideally) Maximo-synced DT properties. The TBIT (LAX) facility
> used in the retrospective is the reference dataset.

---

## 1. Discovery & Navigation

| # | Prompt | Expected tools |
|---|--------|----------------|
| 1.1 | What account groups do I have access to? | `list_groups` |
| 1.2 | Show me all the facilities in my LAX campus group. | `list_groups` → `list_group_facilities` |
| 1.3 | Give me the details for the TBIT facility — name, address, and how many models it has. | `get_facility` |
| 1.4 | What data schema / property sets are available for TBIT? | `get_facility_template` |
| 1.5 | What saved views exist for this facility? | `list_views` |

---

## 2. Spatial — Levels & Rooms

| # | Prompt | Expected tools |
|---|--------|----------------|
| 2.1 | List all floors in the TBIT building. | `list_levels` |
| 2.2 | How many rooms are on Level 2? | `list_rooms_on_level` |
| 2.3 | Show me all the rooms in this facility. | `list_rooms` |
| 2.4 | What equipment is on Level 3? | `list_assets_on_level` |
| 2.5 | What elements are in the Server Room? | `list_elements_in_room` |
| 2.6 | Where is pump P-101 located? Which floor and room? | `find_element_location` |

---

## 3. Systems — MEP Discovery

| # | Prompt | Expected tools |
|---|--------|----------------|
| 3.1 | List all MEP systems in this facility. | `list_systems` |
| 3.2 | Show me only the HVAC systems. | `list_systems_by_class` |
| 3.3 | What fire protection systems does the building have? | `list_systems_by_class` |
| 3.4 | List all the elements (ducts, diffusers, etc.) that belong to the AHU-1 Supply Air system. | `list_system_elements` |

---

## 4. Spatial System Analysis (new tools)

These test the system-to-room and system-to-level spatial relationship tools.

| # | Prompt | Expected tools |
|---|--------|----------------|
| 4.1 | What rooms does the AHU-1 Supply Air system serve? | `list_rooms_served_by_system` |
| 4.2 | Which rooms are connected to the exhaust air system? | `list_rooms_served_by_system` |
| 4.3 | How does the domestic hot water system cover the building — which floors and rooms does it reach? | `get_system_spatial_coverage` |
| 4.4 | Give me a spatial coverage breakdown of the main HVAC supply air system — how many elements per floor, and which rooms on each floor? | `get_system_spatial_coverage` |
| 4.5 | What systems serve the main lobby? | `list_systems_serving_room` |
| 4.6 | Compare: which rooms does the supply air system reach versus the return air system? | `list_rooms_served_by_system` (x2) |
| 4.7 | Are there any rooms on Level 2 that have NO HVAC system coverage? | `list_rooms_on_level` + `list_rooms_served_by_system` (agent must combine) |

---

## 5. IoT Streams & Sensors

| # | Prompt | Expected tools |
|---|--------|----------------|
| 5.1 | What IoT streams / sensors exist in this facility? | `list_streams` |
| 5.2 | Are there any sensors in the Server Room? | `list_streams_in_room` |
| 5.3 | What is the latest reading from stream X? | `get_stream_last_reading` |
| 5.4 | Show me the temperature data for the past week from stream X. | `get_stream_data` |

---

## 6. Asset Intelligence — Schema & Properties

| # | Prompt | Expected tools |
|---|--------|----------------|
| 6.1 | What Maximo / DT property fields are available for this facility's models? | `get_model_schema` or `get_maximo_column_mapping` |
| 6.2 | Give me the mapping of Maximo property names to their column codes. | `get_maximo_column_mapping` |
| 6.3 | What does column z:iAs mean? | `get_model_schema` (with family_filter='z') |

---

## 7. Asset Intelligence — Inventory & Lifecycle

| # | Prompt | Expected tools |
|---|--------|----------------|
| 7.1 | List all tagged assets with their Maximo properties. | `list_tagged_assets_with_properties` |
| 7.2 | How many assets have Maximo data populated vs. empty? | `list_tagged_assets_with_properties` (include_empty=true) |
| 7.3 | Show me all the Air Handling Units. | `list_assets_by_classification` (classification='AHU' or '11.ME.AHU') |
| 7.4 | What Computer Room Air Conditioners (CRACs) do we have? | `list_assets_by_classification` (classification='CRU') |
| 7.5 | Which assets are currently decommissioned? | `list_assets_by_status` (status='DECOMMISSIONED') |
| 7.6 | Which assets are operating? | `list_assets_by_status` (status='OPERATING') |
| 7.7 | What equipment has less than 5 years of remaining life? | `list_aging_assets` (max_remain_life=5) |
| 7.8 | Show me all assets with lifecycle data, sorted by remaining life. | `list_aging_assets` (no threshold) |
| 7.9 | Which assets are nearing end of life but are still operating (exclude decommissioned)? | `list_aging_assets` (include_decommissioned=false) |
| 7.10 | Give me full details on asset TERTBTAHU005 — Maximo data, location, source/Revit info. | `get_asset_detail` |

---

## 8. Tickets & History

| # | Prompt | Expected tools |
|---|--------|----------------|
| 8.1 | Are there any open tickets / work orders in this facility? | `list_tickets` |
| 8.2 | What changes have been made to this facility recently? | `get_facility_history` |

---

## 9. Multi-Step / Conversational Scenarios

These require the agent to chain multiple tools or reason across results.

| # | Scenario | Expected flow |
|---|----------|---------------|
| 9.1 | "I'm a facility manager at LAX. Walk me through the TBIT campus — what buildings do I have, and give me a quick health check on the HVAC equipment." | `list_groups` → `list_group_facilities` → `list_systems_by_class` → `list_aging_assets` |
| 9.2 | "Find all CRACs that are past their design life, and tell me which rooms they're in." | `list_assets_by_classification` → filter by lifecycle → `find_element_location` per asset |
| 9.3 | "Which floor has the most aging HVAC equipment? Break it down by level." | `list_aging_assets` → `find_element_location` for each, then aggregate by level |
| 9.4 | "I want to understand the AHU-1 supply air system end-to-end: what elements make it up, what rooms does it reach, and are any of its components near end of life?" | `list_system_elements` → `list_rooms_served_by_system` or `get_system_spatial_coverage` → `get_asset_detail` for aged components |
| 9.5 | "Create a ticket for the air handling unit in the Server Room — mark it critical." | `find_element_location` or `list_elements_in_room` → `create_ticket` (priority=4) |
| 9.6 | "Compare HVAC coverage: which rooms on Level 2 are served by the supply air system vs. the return air system? Are any rooms missing return air?" | `list_rooms_on_level` + `list_rooms_served_by_system` (x2) → set difference |

---

## 10. Edge Cases & Error Handling

| # | Prompt | What to verify |
|---|--------|----------------|
| 10.1 | Get details for an element key that doesn't exist. | `get_asset_detail` returns `{"error": "Element not found"}` |
| 10.2 | List rooms served by a system name that doesn't match anything. | `list_rooms_served_by_system` returns `[]` |
| 10.3 | Find element location for a name with no matches. | `find_element_location` returns `[]` |
| 10.4 | Ask for stream data when no streams have data. | `get_stream_data` returns empty |
| 10.5 | Request aging assets on a facility with no Maximo data. | `list_aging_assets` returns `[]` |
