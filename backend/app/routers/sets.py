from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session, joinedload

from .. import rebrickable, service
from ..db import get_db
from ..models import CatalogSet, Condition, OwnedSet, Status
from ..web import templates

router = APIRouter()

_CONDITIONS = list(Condition)
_STATUSES = list(Status)

# Columns the table view can sort on, keyed by the `sort` query param.
_SORT_COLUMNS = {
    "name": CatalogSet.name,
    "set_num": OwnedSet.set_num,
    "theme": CatalogSet.theme,
    "num_parts": CatalogSet.num_parts,
    "year": CatalogSet.year,
    "storage_location": OwnedSet.storage_location,
    "purchased_date": OwnedSet.purchased_date,
    "created_at": OwnedSet.created_at,
}

# Order condition/status by quality/workflow rather than alphabetically.
_CONDITION_ORDER = case(
    *[(OwnedSet.condition == c.value, i) for i, c in enumerate(Condition)],
    else_=len(Condition),
)
_STATUS_ORDER = case(
    *[(OwnedSet.status == s.value, i) for i, s in enumerate(Status)],
    else_=len(Status),
)


def _int_or_none(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_date(value: str) -> date | None:
    value = (value or "").strip()
    return date.fromisoformat(value) if value else None


@router.get("/")
def index(
    request: Request,
    db: Session = Depends(get_db),
    view: str = "cards",
    sort: str = "created_at",
    dir: str = "desc",
    q: str = "",
    theme: str = "",
    status: str = "",
    condition: str = "",
    min_parts: str = "",
    max_parts: str = "",
    year_min: str = "",
    year_max: str = "",
):
    stmt = select(OwnedSet).join(CatalogSet).options(joinedload(OwnedSet.catalog))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                CatalogSet.name.ilike(like),
                OwnedSet.set_num.ilike(like),
                OwnedSet.notes.ilike(like),
                OwnedSet.storage_location.ilike(like),
            )
        )
    if theme:
        stmt = stmt.where(CatalogSet.theme == theme)
    if status:
        stmt = stmt.where(OwnedSet.status == status)
    if condition:
        stmt = stmt.where(OwnedSet.condition == condition)

    lo, hi = _int_or_none(min_parts), _int_or_none(max_parts)
    if lo is not None:
        stmt = stmt.where(CatalogSet.num_parts >= lo)
    if hi is not None:
        stmt = stmt.where(CatalogSet.num_parts <= hi)

    y_lo, y_hi = _int_or_none(year_min), _int_or_none(year_max)
    if y_lo is not None:
        stmt = stmt.where(CatalogSet.year >= y_lo)
    if y_hi is not None:
        stmt = stmt.where(CatalogSet.year <= y_hi)

    if sort == "condition":
        order_col = _CONDITION_ORDER
    elif sort == "status":
        order_col = _STATUS_ORDER
    else:
        order_col = _SORT_COLUMNS.get(sort, OwnedSet.created_at)
    order_col = order_col.asc() if dir == "asc" else order_col.desc()
    stmt = stmt.order_by(order_col, CatalogSet.name.asc())

    rows = db.execute(stmt).scalars().all()

    themes = (
        db.execute(
            select(CatalogSet.theme)
            .join(OwnedSet)
            .where(CatalogSet.theme.isnot(None))
            .distinct()
            .order_by(CatalogSet.theme)
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "sets": rows,
            "view": view,
            "sort": sort,
            "dir": dir,
            "themes": themes,
            "conditions": _CONDITIONS,
            "statuses": _STATUSES,
            "f": {
                "q": q,
                "theme": theme,
                "status": status,
                "condition": condition,
                "min_parts": min_parts,
                "max_parts": max_parts,
                "year_min": year_min,
                "year_max": year_max,
            },
        },
    )


@router.get("/sets/new")
def new_set(request: Request, set_num: str = "", q: str = ""):
    results = []
    if q:
        try:
            results = rebrickable.search_sets(q)
        except rebrickable.RebrickableError:
            results = []
    return templates.TemplateResponse(
        "new.html",
        {
            "request": request,
            "conditions": _CONDITIONS,
            "statuses": _STATUSES,
            "form": {"set_num": set_num} if set_num else None,
            "q": q,
            "results": results,
        },
    )


@router.post("/sets")
def create_set(
    request: Request,
    db: Session = Depends(get_db),
    set_num: str = Form(...),
    purchased_date: str = Form(""),
    storage_location: str = Form(""),
    notes: str = Form(""),
    condition: str = Form(Condition.NEW.value),
    status: str = Form(Status.IN_BOX.value),
):
    form = {
        "set_num": set_num,
        "purchased_date": purchased_date,
        "storage_location": storage_location,
        "notes": notes,
        "condition": condition,
        "status": status,
    }
    try:
        catalog = service.fetch_and_cache_catalog(db, set_num)
    except rebrickable.RebrickableError as exc:
        return templates.TemplateResponse(
            "new.html",
            {
                "request": request,
                "error": str(exc),
                "conditions": _CONDITIONS,
                "statuses": _STATUSES,
                "form": form,
            },
            status_code=400,
        )

    owned = OwnedSet(
        set_num=catalog.set_num,
        purchased_date=_parse_date(purchased_date),
        storage_location=storage_location or None,
        notes=notes or None,
        condition=condition,
        status=status,
    )
    db.add(owned)
    db.commit()
    return RedirectResponse(url=f"/sets/{owned.id}", status_code=303)


@router.get("/sets/{owned_id}")
def set_detail(owned_id: int, request: Request, db: Session = Depends(get_db)):
    owned = db.get(OwnedSet, owned_id)
    if owned is None:
        raise HTTPException(status_code=404, detail="Set not found")
    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "owned": owned,
            "catalog": owned.catalog,
            "conditions": _CONDITIONS,
            "statuses": _STATUSES,
        },
    )


@router.post("/sets/{owned_id}/edit")
def edit_set(
    owned_id: int,
    db: Session = Depends(get_db),
    purchased_date: str = Form(""),
    storage_location: str = Form(""),
    notes: str = Form(""),
    condition: str = Form(...),
    status: str = Form(...),
):
    owned = db.get(OwnedSet, owned_id)
    if owned is None:
        raise HTTPException(status_code=404, detail="Set not found")

    owned.purchased_date = _parse_date(purchased_date)
    owned.storage_location = storage_location or None
    owned.notes = notes or None
    owned.condition = condition
    owned.status = status
    db.commit()
    return RedirectResponse(url=f"/sets/{owned_id}", status_code=303)


@router.post("/sets/{owned_id}/refresh")
def refresh_set(owned_id: int, db: Session = Depends(get_db)):
    owned = db.get(OwnedSet, owned_id)
    if owned is None:
        raise HTTPException(status_code=404, detail="Set not found")
    service.fetch_and_cache_catalog(db, owned.set_num)
    db.commit()
    return RedirectResponse(url=f"/sets/{owned_id}", status_code=303)


@router.post("/sets/{owned_id}/delete")
def delete_set(owned_id: int, db: Session = Depends(get_db)):
    owned = db.get(OwnedSet, owned_id)
    if owned is not None:
        db.delete(owned)
        db.commit()
    return RedirectResponse(url="/", status_code=303)
