"""Thin client for the Rebrickable v3 API.

Docs: https://rebrickable.com/api/v3/docs/
Only the few endpoints we need: set details, set parts, set minifigs.
"""
from __future__ import annotations

import httpx

from .config import get_settings

settings = get_settings()

# Rebrickable caps page_size at 1000.
_PAGE_SIZE = 1000


class RebrickableError(Exception):
    pass


def _client() -> httpx.Client:
    if not settings.rebrickable_api_key:
        raise RebrickableError(
            "REBRICKABLE_API_KEY is not set — add it to your .env file."
        )
    return httpx.Client(
        base_url=settings.rebrickable_base_url,
        headers={"Authorization": f"key {settings.rebrickable_api_key}"},
        timeout=30.0,
    )


def normalize_set_num(set_num: str) -> str:
    """Rebrickable set numbers carry a variant suffix, e.g. ``75192-1``.

    People usually type just ``75192``; default the variant to ``-1``.
    """
    set_num = set_num.strip()
    if set_num and "-" not in set_num:
        set_num = f"{set_num}-1"
    return set_num


def _get_all(client: httpx.Client, url: str) -> list[dict]:
    """Follow Rebrickable pagination (``next`` is an absolute URL)."""
    results: list[dict] = []
    next_url: str | None = url
    while next_url:
        resp = client.get(next_url)
        resp.raise_for_status()
        data = resp.json()
        results.extend(data.get("results", []))
        next_url = data.get("next")
    return results


def get_set(set_num: str) -> dict:
    with _client() as client:
        resp = client.get(f"/sets/{set_num}/")
        if resp.status_code == 404:
            raise RebrickableError(f"Set '{set_num}' was not found on Rebrickable.")
        resp.raise_for_status()
        return resp.json()


def get_set_parts(set_num: str) -> list[dict]:
    with _client() as client:
        raw = _get_all(client, f"/sets/{set_num}/parts/?page_size={_PAGE_SIZE}")
    parts = []
    for item in raw:
        part = item.get("part") or {}
        color = item.get("color") or {}
        parts.append(
            {
                "part_num": part.get("part_num"),
                "name": part.get("name"),
                "img_url": part.get("part_img_url"),
                "color": color.get("name"),
                "quantity": item.get("quantity"),
                "is_spare": item.get("is_spare", False),
            }
        )
    return parts


def get_set_minifigs(set_num: str) -> list[dict]:
    with _client() as client:
        raw = _get_all(client, f"/sets/{set_num}/minifigs/?page_size={_PAGE_SIZE}")
    figs = []
    for item in raw:
        figs.append(
            {
                "fig_num": item.get("set_num"),
                "name": item.get("set_name"),
                "quantity": item.get("quantity"),
                "img_url": item.get("set_img_url"),
            }
        )
    return figs


# Themes are static, so cache them process-wide to avoid re-fetching parents.
_theme_cache: dict[int, dict] = {}


def get_theme(theme_id: int) -> dict:
    if theme_id in _theme_cache:
        return _theme_cache[theme_id]
    with _client() as client:
        resp = client.get(f"/themes/{theme_id}/")
        resp.raise_for_status()
        data = resp.json()
    _theme_cache[theme_id] = data
    return data


def resolve_theme(theme_id: int | None) -> dict:
    """Resolve a set's theme to its top-level name.

    Rebrickable themes are hierarchical (e.g. a "Star Wars" subtheme points at
    the top-level "Star Wars"). We walk up ``parent_id`` so sets group under the
    theme people actually filter by. Returns the direct name too, as a fallback.
    """
    result: dict = {"theme_id": theme_id, "theme_name": None, "theme": None}
    if not theme_id:
        return result
    try:
        theme = get_theme(theme_id)
    except Exception:  # noqa: BLE001 — theme is best-effort metadata
        return result

    result["theme_name"] = theme.get("name")
    root = theme
    seen = {theme.get("id")}
    while root.get("parent_id"):
        parent_id = root["parent_id"]
        if parent_id in seen:
            break
        seen.add(parent_id)
        try:
            root = get_theme(parent_id)
        except Exception:  # noqa: BLE001
            break
    result["theme"] = root.get("name")
    return result


# --- Parts & colors (for the add-loose-part flow) ---

_part_cache: dict[str, dict] = {}
_colors_cache: list[dict] | None = None


def get_part(part_num: str) -> dict:
    part_num = part_num.strip()
    if part_num in _part_cache:
        return _part_cache[part_num]
    with _client() as client:
        resp = client.get(f"/parts/{part_num}/")
        if resp.status_code == 404:
            raise RebrickableError(f"Part '{part_num}' was not found on Rebrickable.")
        resp.raise_for_status()
        data = resp.json()
    _part_cache[part_num] = data
    return data


def get_part_color_image(part_num: str, color_id: int | None) -> str | None:
    """Element image for a specific part+color, if available (best-effort)."""
    if color_id is None:
        return None
    try:
        with _client() as client:
            resp = client.get(f"/parts/{part_num}/colors/{color_id}/")
            if resp.status_code != 200:
                return None
            return resp.json().get("part_img_url")
    except Exception:  # noqa: BLE001
        return None


def get_colors() -> list[dict]:
    """All Rebrickable colors as [{'id', 'name'}], sorted by name (cached)."""
    global _colors_cache
    if _colors_cache is not None:
        return _colors_cache
    with _client() as client:
        raw = _get_all(client, "/colors/?page_size=1000")
    colors = [{"id": c.get("id"), "name": c.get("name")} for c in raw]
    colors.sort(key=lambda c: (c["name"] or "").lower())
    _colors_cache = colors
    return colors


def get_minifig(fig_num: str) -> dict:
    fig_num = fig_num.strip()
    with _client() as client:
        resp = client.get(f"/minifigs/{fig_num}/")
        if resp.status_code == 404:
            raise RebrickableError(f"Minifig '{fig_num}' was not found on Rebrickable.")
        resp.raise_for_status()
        return resp.json()


# --- Search (find items by name instead of needing an exact id) ---

def _search(path: str, query: str, limit: int = 24) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    with _client() as client:
        resp = client.get(path, params={"search": query, "page_size": limit})
        resp.raise_for_status()
        return resp.json().get("results", [])


def search_sets(query: str) -> list[dict]:
    return [
        {
            "set_num": s.get("set_num"),
            "name": s.get("name"),
            "year": s.get("year"),
            "num_parts": s.get("num_parts"),
            "img_url": s.get("set_img_url"),
        }
        for s in _search("/sets/", query)
    ]


def search_parts(query: str) -> list[dict]:
    return [
        {
            "part_num": p.get("part_num"),
            "name": p.get("name"),
            "img_url": p.get("part_img_url"),
        }
        for p in _search("/parts/", query)
    ]


def search_minifigs(query: str) -> list[dict]:
    return [
        {
            "fig_num": m.get("set_num"),
            "name": m.get("name"),
            "img_url": m.get("set_img_url"),
        }
        for m in _search("/minifigs/", query)
    ]
