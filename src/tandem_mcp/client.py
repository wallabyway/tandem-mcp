"""Async HTTP client for the Autodesk Tandem REST API."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import httpx

from .constants import (
    COLUMN_FAMILIES_DTPROPERTIES,
    COLUMN_FAMILIES_REFS,
    COLUMN_FAMILIES_STANDARD,
    COLUMN_FAMILIES_SYSTEMS,
    COLUMN_FAMILIES_XREFS,
    ELEMENT_FLAGS_DELETED,
    ELEMENT_FLAGS_LEVEL,
    ELEMENT_FLAGS_ROOM,
    ELEMENT_FLAGS_STREAM,
    ELEMENT_FLAGS_SYSTEM,
    ELEMENT_FLAGS_TICKET,
    MUTATE_ACTIONS_INSERT,
    QC_ELEMENT_FLAGS,
    QC_IS_ASSET,
    QC_KEY,
    QC_NAME,
    QC_ONAME,
    QC_OSYSTEM_CLASS,
    QC_ROOMS,
    QC_SYSTEM_CLASS,
    QC_XROOMS,
    COLUMN_FAMILIES_STATUS,
    COLUMN_NAMES_CATEGORY_ID,
    COLUMN_NAMES_ELEMENT_FLAGS,
    COLUMN_NAMES_NAME,
    COLUMN_NAMES_UNIFORMAT_CLASS,
    system_class_to_list,
    get_default_model_id,
)
from .auth import get_token
from .encoding import from_short_key_array, from_xref_key_array, to_full_key, to_system_id

BASE_URL = "https://developer.api.autodesk.com/tandem/v1"


class TandemClient:
    """Async wrapper around the Tandem Data REST API."""

    def __init__(self, client_id: str, client_secret: str, region: str | None = None) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._region = region

    async def _get_token(self) -> str:
        return await get_token(self._client_id, self._client_secret)

    def _headers(self, token: str, json_body: bool = False) -> dict:
        h: dict[str, str] = {"Authorization": f"Bearer {token}"}
        if self._region:
            h["Region"] = self._region
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    async def _get(self, endpoint: str, params: dict | None = None) -> Any:
        token = await self._get_token()
        async with httpx.AsyncClient() as http:
            r = await http.get(f"{BASE_URL}/{endpoint}", headers=self._headers(token), params=params, timeout=30)
            if not r.is_success:
                raise RuntimeError(f"Tandem API error: {r.status_code} — {r.text}")
            return r.json()

    async def _post(self, endpoint: str, data: Any = None, params: dict | None = None) -> Any:
        token = await self._get_token()
        async with httpx.AsyncClient() as http:
            r = await http.post(
                f"{BASE_URL}/{endpoint}",
                headers=self._headers(token, json_body=True),
                json=data,
                params=params,
                timeout=30,
            )
            if not r.is_success:
                raise RuntimeError(f"Tandem API error: {r.status_code} — {r.text}")
            if len(r.content) == 0:
                return None
            return r.json()

    # ── Groups ──────────────────────────────────────────────────────────

    async def get_groups(self) -> Any:
        return await self._get("groups")

    async def get_group_facilities(self, group_id: str) -> Any:
        return await self._get(f"groups/{group_id}/twins")

    # ── Facility ────────────────────────────────────────────────────────

    async def get_facility(self, facility_id: str) -> Any:
        return await self._get(f"twins/{facility_id}")

    async def get_facility_template(self, facility_id: str) -> Any:
        return await self._get(f"twins/{facility_id}/inlinetemplate")

    async def get_facility_history(self, facility_id: str, inputs: dict) -> Any:
        return await self._post(f"twins/{facility_id}/history", inputs)

    async def get_views(self, facility_id: str) -> Any:
        return await self._get(f"twins/{facility_id}/views")

    # ── Model / Elements ────────────────────────────────────────────────

    async def get_elements(
        self,
        model_id: str,
        element_ids: List[str] | None = None,
        column_families: List[str] | None = None,
        columns: List[str] | None = None,
        include_history: bool = False,
    ) -> list:
        inputs: Dict[str, Any] = {"includeHistory": include_history, "skipArrays": True}
        if column_families:
            inputs["families"] = column_families
        if columns:
            inputs["qualifiedColumns"] = columns
        if element_ids:
            inputs["keys"] = element_ids
        result = await self._post(f"modeldata/{model_id}/scan", inputs)
        # first element is column metadata — skip it
        return result[1:] if result else []

    async def get_element(self, model_id: str, key: str, column_families: List[str] | None = None) -> Any:
        families = column_families or [COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS, COLUMN_FAMILIES_XREFS]
        data = await self.get_elements(model_id, [key], families)
        return data[0] if data else None

    async def get_levels(self, model_id: str) -> list:
        elements = await self.get_elements(model_id, column_families=[COLUMN_FAMILIES_STANDARD])
        return [e for e in elements if isinstance(e, dict) and e.get(QC_ELEMENT_FLAGS) == ELEMENT_FLAGS_LEVEL]

    async def get_rooms(self, model_id: str) -> list:
        elements = await self.get_elements(model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS])
        return [e for e in elements if isinstance(e, dict) and e.get(QC_ELEMENT_FLAGS) == ELEMENT_FLAGS_ROOM]

    async def get_tagged_assets(self, model_id: str, include_history: bool = False) -> list:
        elements = await self.get_elements(
            model_id,
            column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_DTPROPERTIES, COLUMN_FAMILIES_REFS],
            include_history=include_history,
        )
        return [e for e in elements if isinstance(e, dict) and e.get(QC_IS_ASSET)]

    async def get_streams(self, model_id: str) -> list:
        elements = await self.get_elements(
            model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS, COLUMN_FAMILIES_XREFS]
        )
        return [e for e in elements if isinstance(e, dict) and e.get(QC_ELEMENT_FLAGS) == ELEMENT_FLAGS_STREAM]

    async def get_systems(self, model_id: str) -> list:
        elements = await self.get_elements(
            model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS, COLUMN_FAMILIES_SYSTEMS]
        )
        return [e for e in elements if isinstance(e, dict) and e.get(QC_ELEMENT_FLAGS) == ELEMENT_FLAGS_SYSTEM]

    async def get_tickets(self, model_id: str) -> list:
        elements = await self.get_elements(
            model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS, COLUMN_FAMILIES_XREFS]
        )
        return [e for e in elements if isinstance(e, dict) and e.get(QC_ELEMENT_FLAGS) == ELEMENT_FLAGS_TICKET]

    # ── Streams / Time Series ───────────────────────────────────────────

    async def get_stream_data(
        self, model_id: str, key: str, from_date: int | None = None, to_date: int | None = None
    ) -> Any:
        params: dict[str, Any] = {}
        if from_date is not None:
            params["from"] = from_date
        if to_date is not None:
            params["to"] = to_date
        return await self._get(f"timeseries/models/{model_id}/streams/{key}", params or None)

    async def get_stream_last_reading(self, model_id: str, keys: List[str]) -> Any:
        return await self._post(f"timeseries/models/{model_id}/streams", {"keys": keys})

    # ── Mutations ───────────────────────────────────────────────────────

    async def mutate_elements(
        self,
        model_id: str,
        keys: List[str],
        mutations: list,
        description: str,
    ) -> Any:
        inputs = {"keys": keys, "muts": mutations, "desc": description}
        return await self._post(f"modeldata/{model_id}/mutate", inputs)

    async def create_element(self, model_id: str, mutations: list, description: str) -> Any:
        inputs = {"muts": mutations, "desc": description}
        return await self._post(f"modeldata/{model_id}/create", inputs)

    # ── Composite: Spatial Queries ──────────────────────────────────────

    async def _get_model_ids(self, facility_id: str) -> list[str]:
        """Get all model IDs for a facility."""
        facility = await self.get_facility(facility_id)
        return [link["modelId"] for link in facility.get("links", [])]

    async def _find_level_key(self, model_id: str, level_name: str) -> str | None:
        """Find a level key by name (case-insensitive partial match)."""
        levels = await self.get_levels(model_id)
        needle = level_name.lower()
        for lv in levels:
            name = (lv.get(QC_ONAME) or lv.get(QC_NAME, "")).lower()
            if needle in name or name in needle:
                return lv.get(QC_KEY)
        return None

    async def _find_room_key(self, model_id: str, room_name: str) -> str | None:
        """Find a room key by name (case-insensitive partial match)."""
        rooms = await self.get_rooms(model_id)
        needle = room_name.lower()
        for rm in rooms:
            name = (rm.get(QC_ONAME) or rm.get(QC_NAME, "")).lower()
            if needle in name or name in needle:
                return rm.get(QC_KEY)
        return None

    async def get_rooms_on_level(self, facility_id: str, level_name: str) -> list[dict]:
        """Return all rooms on a given level across all models."""
        results = []
        for model_id in await self._get_model_ids(facility_id):
            level_key = await self._find_level_key(model_id, level_name)
            if level_key is None:
                continue
            rooms = await self.get_rooms(model_id)
            from .constants import QC_LEVEL
            for rm in rooms:
                if rm.get(QC_LEVEL) == level_key:
                    results.append({"key": rm.get(QC_KEY), "name": rm.get(QC_ONAME) or rm.get(QC_NAME), "model_id": model_id})
        return results

    async def get_assets_on_level(self, facility_id: str, level_name: str) -> list[dict]:
        """Return all tagged assets on a given level across all models."""
        results = []
        for model_id in await self._get_model_ids(facility_id):
            level_key = await self._find_level_key(model_id, level_name)
            if level_key is None:
                continue
            from .constants import QC_LEVEL
            assets = await self.get_tagged_assets(model_id)
            for a in assets:
                if a.get(QC_LEVEL) == level_key:
                    results.append({"key": a.get(QC_KEY), "name": a.get(QC_ONAME) or a.get(QC_NAME), "model_id": model_id})
        return results

    async def get_elements_in_room(self, facility_id: str, room_name: str) -> list[dict]:
        """Return all elements that reference a given room."""
        results = []
        for model_id in await self._get_model_ids(facility_id):
            room_key = await self._find_room_key(model_id, room_name)
            if room_key is None:
                continue
            elements = await self.get_elements(
                model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS]
            )
            for elem in elements:
                if not isinstance(elem, dict):
                    continue
                room_refs = elem.get(QC_ROOMS)
                if room_refs is None:
                    continue
                room_keys = from_short_key_array(room_refs)
                if room_key in room_keys:
                    results.append({
                        "key": elem.get(QC_KEY),
                        "name": elem.get(QC_ONAME) or elem.get(QC_NAME),
                        "flags": elem.get(QC_ELEMENT_FLAGS),
                        "model_id": model_id,
                    })
        return results

    async def get_streams_in_room(self, facility_id: str, room_name: str) -> list[dict]:
        """Return all streams associated with a given room (via xrefs)."""
        results = []
        for model_id in await self._get_model_ids(facility_id):
            room_key = await self._find_room_key(model_id, room_name)
            if room_key is None:
                continue
            streams = await self.get_streams(model_id)
            for s in streams:
                xroom_refs = s.get(QC_XROOMS)
                if xroom_refs is None:
                    continue
                xref_pairs = from_xref_key_array(xroom_refs)
                for _mid, ekey in xref_pairs:
                    if ekey == room_key:
                        results.append({
                            "key": s.get(QC_KEY),
                            "name": s.get(QC_ONAME) or s.get(QC_NAME),
                            "model_id": model_id,
                        })
                        break
        return results

    async def find_element_location(self, facility_id: str, element_name: str) -> list[dict]:
        """Find an element by name and return its level + room info."""
        results = []
        needle = element_name.lower()
        for model_id in await self._get_model_ids(facility_id):
            elements = await self.get_elements(
                model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS]
            )
            # build lookup maps
            level_map: dict[str, str] = {}
            room_map: dict[str, str] = {}
            for e in elements:
                if not isinstance(e, dict):
                    continue
                flags = e.get(QC_ELEMENT_FLAGS)
                if flags == ELEMENT_FLAGS_LEVEL:
                    level_map[e.get(QC_KEY)] = e.get(QC_ONAME) or e.get(QC_NAME, "")
                elif flags == ELEMENT_FLAGS_ROOM:
                    room_map[e.get(QC_KEY)] = e.get(QC_ONAME) or e.get(QC_NAME, "")

            for e in elements:
                if not isinstance(e, dict):
                    continue
                name = (e.get(QC_ONAME) or e.get(QC_NAME, "")).lower()
                if needle not in name:
                    continue
                from .constants import QC_LEVEL
                level_key = e.get(QC_LEVEL)
                level_name = level_map.get(level_key, "") if level_key else ""
                room_names = []
                room_refs = e.get(QC_ROOMS)
                if room_refs:
                    for rk in from_short_key_array(room_refs):
                        rn = room_map.get(rk)
                        if rn:
                            room_names.append(rn)
                results.append({
                    "key": e.get(QC_KEY),
                    "name": e.get(QC_ONAME) or e.get(QC_NAME),
                    "level": level_name,
                    "rooms": room_names,
                    "model_id": model_id,
                })
        return results

    # ── Composite: System Queries ───────────────────────────────────────

    async def get_systems_by_class(self, facility_id: str, class_filter: str) -> list[dict]:
        """List systems filtered by class name (e.g. 'Supply Air', 'HVAC', 'Power')."""
        needle = class_filter.lower()
        # expand shorthand
        hvac_terms = {"hvac", "heating", "cooling", "ventilation", "air conditioning"}
        is_hvac = needle in hvac_terms
        results = []
        for model_id in await self._get_model_ids(facility_id):
            systems = await self.get_systems(model_id)
            for s in systems:
                flags = s.get(QC_OSYSTEM_CLASS) or s.get(QC_SYSTEM_CLASS)
                if flags is None:
                    continue
                class_names = system_class_to_list(flags)
                matched = False
                for cn in class_names:
                    if needle in cn.lower():
                        matched = True
                        break
                    if is_hvac and any(term in cn.lower() for term in ["air", "hydronic"]):
                        matched = True
                        break
                if matched:
                    results.append({
                        "key": s.get(QC_KEY),
                        "name": s.get(QC_ONAME) or s.get(QC_NAME),
                        "classes": class_names,
                        "model_id": model_id,
                    })
        return results

    async def get_system_elements(self, facility_id: str, system_name: str) -> list[dict]:
        """Return all elements belonging to a named system."""
        results = []
        for model_id in await self._get_model_ids(facility_id):
            # find the system
            systems = await self.get_systems(model_id)
            system_id = None
            system_filter = None
            for s in systems:
                name = (s.get(QC_ONAME) or s.get(QC_NAME, "")).lower()
                if system_name.lower() in name:
                    key = to_full_key(s.get(QC_KEY), True)
                    system_id = to_system_id(key)
                    system_filter = s.get(QC_OSYSTEM_CLASS) or s.get(QC_SYSTEM_CLASS)
                    break
            if system_id is None:
                continue
            filter_names = system_class_to_list(system_filter) if system_filter else []
            # scan all elements for system membership
            elements = await self.get_elements(
                model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_SYSTEMS]
            )
            for elem in elements:
                if not isinstance(elem, dict):
                    continue
                flags = elem.get(QC_ELEMENT_FLAGS)
                if flags == ELEMENT_FLAGS_DELETED or flags == ELEMENT_FLAGS_SYSTEM:
                    continue
                # check if element has column m:{system_id}
                has_membership = False
                for col in elem:
                    match = re.match(r"^m:!?(.+)$", col)
                    if match and match.group(1) == system_id:
                        has_membership = True
                        break
                if has_membership:
                    results.append({
                        "key": elem.get(QC_KEY),
                        "name": elem.get(QC_ONAME) or elem.get(QC_NAME),
                        "model_id": model_id,
                    })
        return results

    async def get_systems_serving_room(self, facility_id: str, room_name: str) -> list[dict]:
        """Find all systems that have at least one member element in the given room."""
        # Step 1: find elements in the room
        room_elements = await self.get_elements_in_room(facility_id, room_name)
        if not room_elements:
            return []
        room_element_keys = {e["key"] for e in room_elements}

        # Step 2: for each model, find systems and check membership
        seen_systems: set[str] = set()
        results = []
        for model_id in await self._get_model_ids(facility_id):
            systems = await self.get_systems(model_id)
            for s in systems:
                key = to_full_key(s.get(QC_KEY), True)
                sid = to_system_id(key)
                if sid in seen_systems:
                    continue
                sfilter = s.get(QC_OSYSTEM_CLASS) or s.get(QC_SYSTEM_CLASS)
                class_names = system_class_to_list(sfilter) if sfilter else []

                # check if any room element belongs to this system
                elements = await self.get_elements(
                    model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_SYSTEMS]
                )
                member_in_room = False
                for elem in elements:
                    if not isinstance(elem, dict):
                        continue
                    if elem.get(QC_KEY) not in room_element_keys:
                        continue
                    for col in elem:
                        match = re.match(r"^m:!?(.+)$", col)
                        if match and match.group(1) == sid:
                            member_in_room = True
                            break
                    if member_in_room:
                        break
                if member_in_room:
                    seen_systems.add(sid)
                    results.append({
                        "key": s.get(QC_KEY),
                        "name": s.get(QC_ONAME) or s.get(QC_NAME),
                        "classes": class_names,
                        "model_id": model_id,
                    })
        return results
