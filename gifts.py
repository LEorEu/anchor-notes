"""Fetch room gift catalog (id → name, price). Best-effort, never raises."""
from __future__ import annotations

import logging
from typing import Dict

import httpx

log = logging.getLogger(__name__)

# These endpoints return JSON like {"error":0, "data":{"giftList":[{"id":..,"name":..,"priceInfo":{...}}]}}
# v3 is the comprehensive web catalog (~150 gifts/room incl. effects, fan-club, privilege).
# Schema drifts; we only read what we need and fall back gracefully.
_ENDPOINTS = [
    "https://gift.douyucdn.cn/api/gift/v3/web/list?rid={rid}",
    "https://gift.douyucdn.cn/api/gift/v2/web/list?rid={rid}",
]


async def fetch_gift_catalog(room_id: int) -> Dict[int, dict]:
    """Return {gift_id: {"name": str, "price_yuchi": int}}."""
    catalog: Dict[int, dict] = {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url_tpl in _ENDPOINTS:
            url = url_tpl.format(rid=room_id)
            try:
                r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                r.raise_for_status()
                data = r.json()
            except Exception as e:
                log.warning("gift fetch failed for %s: %s", url, e)
                continue
            for item in _extract_gift_list(data):
                gid = _coerce_int(item.get("id") or item.get("gid") or item.get("gfid"))
                if gid is None:
                    continue
                # v3: priceInfo.price stored as 鱼翅 × 100 (centi-yuchi to avoid decimals);
                # v2 'pc' is also centi-yuchi. Convert to real 鱼翅 for downstream consumers.
                price_info = item.get("priceInfo") or {}
                centi = _coerce_int(
                    price_info.get("price")
                    or item.get("pc")
                    or item.get("price")
                ) or 0
                price_yuchi = centi / 100.0  # float — lets cheap gifts (赞 = 0.1) keep precision
                catalog.setdefault(gid, {
                    "name": str(item.get("name") or item.get("gn") or f"礼物#{gid}"),
                    "price_yuchi": price_yuchi,
                })
            if catalog:
                break
    log.info("loaded %d gifts for room %d", len(catalog), room_id)
    return catalog


def _extract_gift_list(data) -> list:
    """Walk a few common JSON shapes to find a gift array."""
    if not isinstance(data, dict):
        return []
    d = data.get("data", data)
    for key in ("giftList", "list", "gift_list", "items"):
        v = d.get(key) if isinstance(d, dict) else None
        if isinstance(v, list):
            return v
    if isinstance(d, list):
        return d
    return []


def _coerce_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except Exception:
            return None
