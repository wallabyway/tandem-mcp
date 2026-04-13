"""Async HTTP client for the Autodesk Tandem REST API."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Coroutine, Dict, List

import httpx

from .auth import get_token
from .cache import levels_cache, model_ids_cache, rooms_cache, scan_cache, schema_cache
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
    QC_CLASSIFICATION,
    QC_ELEMENT_FLAGS,
    QC_IS_ASSET,
    QC_KEY,
    QC_LEVEL,
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
    get_default_model_id,
    system_class_to_list,
)
from .encoding import from_short_key_array, from_xref_key_array, to_full_key, to_system_id
from .instrumentation import logger, timed

BASE_URL = "https://developer.api.autodesk.com/tandem/v1"


class TandemClient:
    """Async wrapper around the Tandem Data REST API with caching and connection pooling."""

    def __init__(self, client_id: str, client_secret: str, region: str | None = None) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._region = region
        self._http = httpx.AsyncClient(timeout=30)
        self._concurrency = asyncio.Semaphore(8)

    async def _get_token(self) -> str:
        return await get_token(self._client_id, self._client_secret)

    def _headers(self, token: str, json_body: bool = False) -> dict:
        h: dict[str, str] = {"Authorization": f"Bearer {token}"}
        if self._region:
            h["Region"] = self._region
        if json_body:
            h["Content-Type"] = "application/json"
        return h

    async def _request_with_retry(self, method: str, endpoint: str, **kwargs: Any) -> httpx.Response:
        """Execute an HTTP request with retry on 429 rate-limit responses."""
        url = f"{BASE_URL}/{endpoint}"
        for attempt in range(4):
            token = await self._get_token()
            headers = self._headers(token, json_body=(method == "POST"))
            if method == "GET":
                r = await self._http.get(url, headers=headers, **kwargs)
            else:
                r = await self._http.post(url, headers=headers, **kwargs)
            if r.status_code != 429:
                return r
            wait = float(r.headers.get("Retry-After", 1 + attempt))
            logger.warning("Rate limited (429) on %s, retrying in %.1fs…", endpoint, wait)
            await asyncio.sleep(wait)
        return r

    async def _get(self, endpoint: str, params: dict | None = None) -> Any:
        async with timed("api.GET", endpoint=endpoint) as ctx:
            r = await self._request_with_retry("GET", endpoint, params=params)
            if not r.is_success:
                raise RuntimeError(f"Tandem API error: {r.status_code} — {r.text}")
            return r.json()

    async def _post(self, endpoint: str, data: Any = None, params: dict | None = None) -> Any:
        async with timed("api.POST", endpoint=endpoint) as ctx:
            r = await self._request_with_retry("POST", endpoint, json=data, params=params)
            if not r.is_success:
                raise RuntimeError(f"Tandem API error: {r.status_code} — {r.text}")
            if len(r.content) == 0:
                return None
            return r.json()

    # ── Parallel fan-out helper ──────────────────────────────────────────

    async def _fan_out(
        self,
        facility_id: str,
        per_model_fn: Callable[[str], Coroutine[Any, Any, list]],
    ) -> list:
        """Run per_model_fn on all facility models in parallel (max 8 concurrent), flatten results."""
        model_ids = await self._get_model_ids(facility_id)

        async def _throttled(mid: str) -> list:
            async with self._concurrency:
                return await per_model_fn(mid)

        per_model = await asyncio.gather(*[_throttled(mid) for mid in model_ids])
        return [item for sublist in per_model for item in sublist]

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
        fam_key = ",".join(sorted(column_families)) if column_families else ""
        ids_key = ",".join(sorted(element_ids)) if element_ids else ""
        cache_key = f"{model_id}|{fam_key}|{ids_key}|{include_history}"

        cached = scan_cache.get(cache_key)
        if cached is not None:
            return cached

        inputs: Dict[str, Any] = {"includeHistory": include_history, "skipArrays": True}
        if column_families:
            inputs["families"] = column_families
        if columns:
            inputs["qualifiedColumns"] = columns
        if element_ids:
            inputs["keys"] = element_ids
        result = await self._post(f"modeldata/{model_id}/scan", inputs)
        result = result[1:] if result else []
        scan_cache.set(cache_key, result)
        return result

    async def get_element(self, model_id: str, key: str, column_families: List[str] | None = None) -> Any:
        families = column_families or [
            COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_DTPROPERTIES,
            COLUMN_FAMILIES_REFS, COLUMN_FAMILIES_XREFS,
        ]
        data = await self.get_elements(model_id, [key], families)
        return data[0] if data else None

    async def get_model_schema(self, model_id: str) -> Any:
        """Return the schema (attribute definitions) for a model — cached."""
        cache_key = f"raw:{model_id}"
        cached = schema_cache.get(cache_key)
        if cached is not None:
            return cached
        result = await self._get(f"modeldata/{model_id}/schema")
        schema_cache.set(cache_key, result)
        return result

    async def get_levels(self, model_id: str) -> list:
        cached = levels_cache.get(model_id)
        if cached is not None:
            return cached
        elements = await self.get_elements(model_id, column_families=[COLUMN_FAMILIES_STANDARD])
        result = [e for e in elements if isinstance(e, dict) and e.get(QC_ELEMENT_FLAGS) == ELEMENT_FLAGS_LEVEL]
        levels_cache.set(model_id, result)
        return result

    async def get_rooms(self, model_id: str) -> list:
        cached = rooms_cache.get(model_id)
        if cached is not None:
            return cached
        elements = await self.get_elements(model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS])
        result = [e for e in elements if isinstance(e, dict) and e.get(QC_ELEMENT_FLAGS) == ELEMENT_FLAGS_ROOM]
        rooms_cache.set(model_id, result)
        return result

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

    # ── Composite helpers ────────────────────────────────────────────────

    async def _get_model_ids(self, facility_id: str) -> list[str]:
        """Get all model IDs for a facility — cached."""
        cached = model_ids_cache.get(facility_id)
        if cached is not None:
            return cached
        facility = await self.get_facility(facility_id)
        result = [link["modelId"] for link in facility.get("links", [])]
        model_ids_cache.set(facility_id, result)
        return result

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

    # ── Composite: Spatial Queries (parallel) ────────────────────────────

    async def get_rooms_on_level(self, facility_id: str, level_name: str) -> list[dict]:
        """Return all rooms on a given level across all models."""
        async def _per_model(model_id: str) -> list[dict]:
            level_key = await self._find_level_key(model_id, level_name)
            if level_key is None:
                return []
            rooms = await self.get_rooms(model_id)
            return [
                {"key": rm.get(QC_KEY), "name": rm.get(QC_ONAME) or rm.get(QC_NAME), "model_id": model_id}
                for rm in rooms if rm.get(QC_LEVEL) == level_key
            ]
        return await self._fan_out(facility_id, _per_model)

    async def get_assets_on_level(self, facility_id: str, level_name: str) -> list[dict]:
        """Return all tagged assets on a given level across all models."""
        async def _per_model(model_id: str) -> list[dict]:
            level_key = await self._find_level_key(model_id, level_name)
            if level_key is None:
                return []
            assets = await self.get_tagged_assets(model_id)
            return [
                {"key": a.get(QC_KEY), "name": a.get(QC_ONAME) or a.get(QC_NAME), "model_id": model_id}
                for a in assets if a.get(QC_LEVEL) == level_key
            ]
        return await self._fan_out(facility_id, _per_model)

    async def get_elements_in_room(self, facility_id: str, room_name: str) -> list[dict]:
        """Return all elements that reference a given room."""
        async def _per_model(model_id: str) -> list[dict]:
            room_key = await self._find_room_key(model_id, room_name)
            if room_key is None:
                return []
            elements = await self.get_elements(
                model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS]
            )
            hits = []
            for elem in elements:
                if not isinstance(elem, dict):
                    continue
                room_refs = elem.get(QC_ROOMS)
                if room_refs is None:
                    continue
                if room_key in from_short_key_array(room_refs):
                    hits.append({
                        "key": elem.get(QC_KEY),
                        "name": elem.get(QC_ONAME) or elem.get(QC_NAME),
                        "flags": elem.get(QC_ELEMENT_FLAGS),
                        "model_id": model_id,
                    })
            return hits
        return await self._fan_out(facility_id, _per_model)

    async def get_streams_in_room(self, facility_id: str, room_name: str) -> list[dict]:
        """Return all streams associated with a given room (via xrefs)."""
        async def _per_model(model_id: str) -> list[dict]:
            room_key = await self._find_room_key(model_id, room_name)
            if room_key is None:
                return []
            streams = await self.get_streams(model_id)
            hits = []
            for s in streams:
                xroom_refs = s.get(QC_XROOMS)
                if xroom_refs is None:
                    continue
                for _mid, ekey in from_xref_key_array(xroom_refs):
                    if ekey == room_key:
                        hits.append({
                            "key": s.get(QC_KEY),
                            "name": s.get(QC_ONAME) or s.get(QC_NAME),
                            "model_id": model_id,
                        })
                        break
            return hits
        return await self._fan_out(facility_id, _per_model)

    async def find_element_location(self, facility_id: str, element_name: str) -> list[dict]:
        """Find an element by name and return its level + room info."""
        needle = element_name.lower()

        async def _per_model(model_id: str) -> list[dict]:
            elements = await self.get_elements(
                model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS]
            )
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

            hits = []
            for e in elements:
                if not isinstance(e, dict):
                    continue
                name = (e.get(QC_ONAME) or e.get(QC_NAME, "")).lower()
                if needle not in name:
                    continue
                level_key = e.get(QC_LEVEL)
                lvl_name = level_map.get(level_key, "") if level_key else ""
                room_names = []
                room_refs = e.get(QC_ROOMS)
                if room_refs:
                    for rk in from_short_key_array(room_refs):
                        rn = room_map.get(rk)
                        if rn:
                            room_names.append(rn)
                hits.append({
                    "key": e.get(QC_KEY),
                    "name": e.get(QC_ONAME) or e.get(QC_NAME),
                    "level": lvl_name,
                    "rooms": room_names,
                    "model_id": model_id,
                })
            return hits
        return await self._fan_out(facility_id, _per_model)

    # ── Composite: System Queries (parallel) ─────────────────────────────

    async def get_systems_by_class(self, facility_id: str, class_filter: str) -> list[dict]:
        """List systems filtered by class name (e.g. 'Supply Air', 'HVAC', 'Power')."""
        needle = class_filter.lower()
        hvac_terms = {"hvac", "heating", "cooling", "ventilation", "air conditioning"}
        is_hvac = needle in hvac_terms

        async def _per_model(model_id: str) -> list[dict]:
            systems = await self.get_systems(model_id)
            hits = []
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
                    hits.append({
                        "key": s.get(QC_KEY),
                        "name": s.get(QC_ONAME) or s.get(QC_NAME),
                        "classes": class_names,
                        "model_id": model_id,
                    })
            return hits
        return await self._fan_out(facility_id, _per_model)

    async def get_system_elements(self, facility_id: str, system_name: str) -> list[dict]:
        """Return all elements belonging to a named system."""
        async def _per_model(model_id: str) -> list[dict]:
            systems = await self.get_systems(model_id)
            system_id = None
            for s in systems:
                name = (s.get(QC_ONAME) or s.get(QC_NAME, "")).lower()
                if system_name.lower() in name:
                    key = to_full_key(s.get(QC_KEY), True)
                    system_id = to_system_id(key)
                    break
            if system_id is None:
                return []
            elements = await self.get_elements(
                model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_SYSTEMS]
            )
            hits = []
            for elem in elements:
                if not isinstance(elem, dict):
                    continue
                flags = elem.get(QC_ELEMENT_FLAGS)
                if flags == ELEMENT_FLAGS_DELETED or flags == ELEMENT_FLAGS_SYSTEM:
                    continue
                for col in elem:
                    match = re.match(r"^m:!?(.+)$", col)
                    if match and match.group(1) == system_id:
                        hits.append({
                            "key": elem.get(QC_KEY),
                            "name": elem.get(QC_ONAME) or elem.get(QC_NAME),
                            "model_id": model_id,
                        })
                        break
            return hits
        return await self._fan_out(facility_id, _per_model)

    async def get_systems_serving_room(self, facility_id: str, room_name: str) -> list[dict]:
        """Find all systems that have at least one member element in the given room."""
        room_elements = await self.get_elements_in_room(facility_id, room_name)
        if not room_elements:
            return []
        room_element_keys = {e["key"] for e in room_elements}

        async def _per_model(model_id: str) -> list[dict]:
            systems = await self.get_systems(model_id)
            elements = await self.get_elements(
                model_id, column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_SYSTEMS]
            )
            hits = []
            for s in systems:
                key = to_full_key(s.get(QC_KEY), True)
                sid = to_system_id(key)
                sfilter = s.get(QC_OSYSTEM_CLASS) or s.get(QC_SYSTEM_CLASS)
                class_names = system_class_to_list(sfilter) if sfilter else []
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
                    hits.append({
                        "key": s.get(QC_KEY),
                        "name": s.get(QC_ONAME) or s.get(QC_NAME),
                        "classes": class_names,
                        "model_id": model_id,
                    })
            return hits

        all_hits = await self._fan_out(facility_id, _per_model)
        seen: set[str] = set()
        deduped = []
        for h in all_hits:
            if h["key"] not in seen:
                seen.add(h["key"])
                deduped.append(h)
        return deduped

    # ── Composite: Spatial System Analysis (parallel) ────────────────────

    async def _resolve_system_member_elements(
        self, facility_id: str, system_name: str
    ) -> list[tuple[str, dict]]:
        """Find all elements belonging to a system, with refs included. Returns (model_id, element) pairs."""
        async def _per_model(model_id: str) -> list[tuple[str, dict]]:
            systems = await self.get_systems(model_id)
            system_id = None
            for s in systems:
                name = (s.get(QC_ONAME) or s.get(QC_NAME, "")).lower()
                if system_name.lower() in name:
                    key = to_full_key(s.get(QC_KEY), True)
                    system_id = to_system_id(key)
                    break
            if system_id is None:
                return []
            elements = await self.get_elements(
                model_id,
                column_families=[COLUMN_FAMILIES_STANDARD, COLUMN_FAMILIES_REFS, COLUMN_FAMILIES_SYSTEMS],
            )
            hits: list[tuple[str, dict]] = []
            for elem in elements:
                if not isinstance(elem, dict):
                    continue
                flags = elem.get(QC_ELEMENT_FLAGS)
                if flags == ELEMENT_FLAGS_DELETED or flags == ELEMENT_FLAGS_SYSTEM:
                    continue
                for col in elem:
                    match = re.match(r"^m:!?(.+)$", col)
                    if match and match.group(1) == system_id:
                        hits.append((model_id, elem))
                        break
            return hits

        model_ids = await self._get_model_ids(facility_id)

        async def _throttled(mid: str) -> list[tuple[str, dict]]:
            async with self._concurrency:
                return await _per_model(mid)

        per_model = await asyncio.gather(*[_throttled(mid) for mid in model_ids])
        return [item for sublist in per_model for item in sublist]

    async def get_rooms_served_by_system(self, facility_id: str, system_name: str) -> list[dict]:
        """Given a system name, return all rooms that contain at least one member element."""
        members = await self._resolve_system_member_elements(facility_id, system_name)
        if not members:
            return []

        room_key_to_info: dict[str, dict] = {}
        model_rooms: dict[str, dict[str, str]] = {}

        for model_id, elem in members:
            if model_id not in model_rooms:
                rooms = await self.get_rooms(model_id)
                model_rooms[model_id] = {
                    r.get(QC_KEY): r.get(QC_ONAME) or r.get(QC_NAME, "")
                    for r in rooms
                }

            room_refs = elem.get(QC_ROOMS)
            if not room_refs:
                continue
            for rk in from_short_key_array(room_refs):
                if rk in room_key_to_info:
                    room_key_to_info[rk]["element_count"] += 1
                    continue
                room_name = model_rooms.get(model_id, {}).get(rk, rk)
                room_key_to_info[rk] = {
                    "key": rk,
                    "name": room_name,
                    "model_id": model_id,
                    "element_count": 1,
                }

        return sorted(room_key_to_info.values(), key=lambda r: r["name"])

    async def get_system_spatial_coverage(self, facility_id: str, system_name: str) -> dict:
        """Return a spatial coverage summary: which levels and rooms a system touches."""
        members = await self._resolve_system_member_elements(facility_id, system_name)
        if not members:
            return {"system": system_name, "total_elements": 0, "levels": []}

        level_rooms: dict[str, dict] = {}
        model_lookups: dict[str, tuple[dict[str, str], dict[str, str]]] = {}

        for model_id, elem in members:
            if model_id not in model_lookups:
                levels = await self.get_levels(model_id)
                rooms = await self.get_rooms(model_id)
                lmap = {lv.get(QC_KEY): lv.get(QC_ONAME) or lv.get(QC_NAME, "") for lv in levels}
                rmap = {rm.get(QC_KEY): rm.get(QC_ONAME) or rm.get(QC_NAME, "") for rm in rooms}
                model_lookups[model_id] = (lmap, rmap)

            lmap, rmap = model_lookups[model_id]
            level_key = elem.get(QC_LEVEL)
            level_name = lmap.get(level_key, "Unknown") if level_key else "Unknown"

            if level_name not in level_rooms:
                level_rooms[level_name] = {"level": level_name, "rooms": {}, "element_count": 0}

            level_rooms[level_name]["element_count"] += 1

            room_refs = elem.get(QC_ROOMS)
            if room_refs:
                for rk in from_short_key_array(room_refs):
                    rname = rmap.get(rk, rk)
                    level_rooms[level_name]["rooms"][rname] = (
                        level_rooms[level_name]["rooms"].get(rname, 0) + 1
                    )

        levels_summary = []
        for info in sorted(level_rooms.values(), key=lambda x: x["level"]):
            levels_summary.append({
                "level": info["level"],
                "element_count": info["element_count"],
                "room_count": len(info["rooms"]),
                "rooms": [
                    {"name": rname, "element_count": cnt}
                    for rname, cnt in sorted(info["rooms"].items())
                ],
            })

        return {
            "system": system_name,
            "total_elements": len(members),
            "total_rooms": sum(lv["room_count"] for lv in levels_summary),
            "total_levels": len(levels_summary),
            "levels": levels_summary,
        }

    # ── Schema & Column Mapping ─────────────────────────────────────────

    async def _build_schema_map(self, model_id: str, family_filter: str | None = None) -> dict[str, dict]:
        """Build a mapping from qualified column (e.g. 'z:iAs') to attribute metadata — cached."""
        cache_key = f"map:{model_id}:{family_filter or 'all'}"
        cached = schema_cache.get(cache_key)
        if cached is not None:
            return cached
        schema = await self.get_model_schema(model_id)
        result: dict[str, dict] = {}
        attrs = schema if isinstance(schema, list) else schema.get("attributes", []) if isinstance(schema, dict) else []
        for attr in attrs:
            if not isinstance(attr, dict):
                continue
            fam = attr.get("fam", "")
            col = attr.get("col", "")
            if family_filter and fam != family_filter:
                continue
            qc = f"{fam}:{col}"
            result[qc] = {
                "name": attr.get("name", col),
                "category": attr.get("category", ""),
                "data_type": attr.get("dataType"),
                "description": attr.get("description", ""),
                "id": attr.get("id", ""),
            }
        schema_cache.set(cache_key, result)
        return result

    def _decode_element_props(self, element: dict, schema_map: dict[str, dict]) -> dict[str, Any]:
        """Translate z: qualified columns to human-readable names using a schema map."""
        decoded: dict[str, Any] = {}
        for qc, value in element.items():
            if not qc.startswith("z:"):
                continue
            meta = schema_map.get(qc)
            if meta:
                decoded[meta["name"]] = value
            else:
                decoded[qc] = value
        return decoded

    # ── Composite: Asset Intelligence (parallel) ─────────────────────────

    async def get_tagged_assets_with_properties(
        self, facility_id: str, model_id: str | None = None, include_empty: bool = False
    ) -> list[dict]:
        """Return tagged assets with decoded DT/Maximo properties."""
        model_ids = [model_id] if model_id else await self._get_model_ids(facility_id)

        async def _per_model(mid: str) -> list[dict]:
            async with self._concurrency:
                schema_map = await self._build_schema_map(mid, "z")
                assets = await self.get_tagged_assets(mid)
                hits = []
                for a in assets:
                    dt_props = self._decode_element_props(a, schema_map)
                    if not include_empty and not dt_props:
                        continue
                    hits.append({
                        "key": a.get(QC_KEY),
                        "name": a.get(QC_ONAME) or a.get(QC_NAME),
                        "classification": a.get(QC_CLASSIFICATION),
                        "model_id": mid,
                        "properties": dt_props,
                    })
                return hits

        per_model = await asyncio.gather(*[_per_model(mid) for mid in model_ids])
        return [item for sublist in per_model for item in sublist]

    async def get_assets_by_status(self, facility_id: str, status: str) -> list[dict]:
        """Filter tagged assets by their Maximo/DT status field."""
        all_assets = await self.get_tagged_assets_with_properties(facility_id, include_empty=False)
        needle = status.lower()
        return [
            a for a in all_assets
            if any(
                isinstance(v, str) and needle in v.lower()
                for k, v in a.get("properties", {}).items()
                if "status" in k.lower()
            )
        ]

    async def get_aging_assets(
        self, facility_id: str, max_remain_life: float | None = None, include_decommissioned: bool = True
    ) -> list[dict]:
        """Find assets where remaining life is below a threshold or design life exceeded."""
        all_assets = await self.get_tagged_assets_with_properties(facility_id, include_empty=False)
        results = []
        for a in all_assets:
            props = a.get("properties", {})
            remain_life = None
            design_life = None
            status = None
            for k, v in props.items():
                kl = k.lower()
                if "remainlife" in kl or "remain_life" in kl:
                    try:
                        remain_life = float(v)
                    except (ValueError, TypeError):
                        pass
                elif "designlife" in kl or "design_life" in kl:
                    try:
                        design_life = float(v)
                    except (ValueError, TypeError):
                        pass
                elif "status" in kl:
                    status = str(v)
            if not include_decommissioned and status and "decommission" in status.lower():
                continue
            if remain_life is not None:
                if max_remain_life is None or remain_life <= max_remain_life:
                    a["remain_life"] = remain_life
                    a["design_life"] = design_life
                    a["status"] = status
                    results.append(a)
        results.sort(key=lambda x: x.get("remain_life", 999))
        return results

    async def get_assets_by_classification(self, facility_id: str, classification: str) -> list[dict]:
        """Filter tagged assets by classification code or partial match."""
        all_assets = await self.get_tagged_assets_with_properties(facility_id, include_empty=True)
        needle = classification.lower()
        return [
            a for a in all_assets
            if needle in (a.get("classification", "") or "").lower()
            or needle in (a.get("name", "") or "").lower()
        ]

    async def get_asset_detail(self, facility_id: str, element_key: str, model_id: str | None = None) -> dict:
        """Get a single asset with ALL properties decoded to human-readable names."""
        mid = model_id or get_default_model_id(facility_id)
        elem = await self.get_element(mid, element_key)
        if elem is None and model_id is None:
            for m in await self._get_model_ids(facility_id):
                if m == mid:
                    continue
                elem = await self.get_element(m, element_key)
                if elem is not None:
                    mid = m
                    break
        if elem is None:
            return {"error": "Element not found"}

        schema_map = await self._build_schema_map(mid)
        dt_props = self._decode_element_props(elem, schema_map)

        level_key = elem.get(QC_LEVEL)
        level_name = ""
        if level_key:
            lv = await self.get_element(mid, level_key, [COLUMN_FAMILIES_STANDARD])
            if lv:
                level_name = lv.get(QC_ONAME) or lv.get(QC_NAME, "")

        room_names = []
        room_refs = elem.get(QC_ROOMS)
        if room_refs:
            for rk in from_short_key_array(room_refs):
                rm = await self.get_element(mid, rk, [COLUMN_FAMILIES_STANDARD])
                if rm:
                    room_names.append(rm.get(QC_ONAME) or rm.get(QC_NAME, ""))

        source_props = {}
        for qc, value in elem.items():
            if qc.startswith("r:"):
                meta = schema_map.get(qc)
                source_props[meta["name"] if meta else qc] = value

        return {
            "key": elem.get(QC_KEY),
            "name": elem.get(QC_ONAME) or elem.get(QC_NAME),
            "classification": elem.get(QC_CLASSIFICATION),
            "level": level_name,
            "rooms": room_names,
            "model_id": mid,
            "properties": dt_props,
            "source": source_props,
        }

    async def get_maximo_column_mapping(self, facility_id: str) -> dict[str, str]:
        """Return a simple {human_name: qualified_column} mapping for DT properties across all models."""
        model_ids = await self._get_model_ids(facility_id)

        async def _per_model(mid: str) -> list[tuple[str, str]]:
            async with self._concurrency:
                schema_map = await self._build_schema_map(mid, "z")
                return [(meta.get("name", qc), qc) for qc, meta in schema_map.items()]

        per_model = await asyncio.gather(*[_per_model(mid) for mid in model_ids])
        merged: dict[str, str] = {}
        for pairs in per_model:
            for name, qc in pairs:
                if name not in merged:
                    merged[name] = qc
        return merged
