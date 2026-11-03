from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import rebrickable, service
from ..db import get_db
from ..models import CatalogSet, LoosePart, OwnedSet, Part, SetPart
from ..web import templates

router = APIRouter()

_PAGE_SIZE = 60


def _int_or_none(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _owned_copies_subq():
    """How many physical copies of each set you own (for weighting parts)."""
    return (
        select(OwnedSet.set_num.label("set_num"), func.count().label("copies"))
        .group_by(OwnedSet.set_num)
        .subquery()
    )


@router.get("/parts")
def parts_index(
    request: Request,
    db: Session = Depends(get_db),
    view: str = "cards",
    sort: str = "total",
    dir: str = "desc",
    q: str = "",
    color: str = "",
    membership: str = "",
    min_qty: str = "",
    max_qty: str = "",
    page: str = "1",
):
    owned = _owned_copies_subq()
    set_agg = (
        select(
            SetPart.part_id.label("part_id"),
            func.sum(SetPart.quantity * owned.c.copies).label("in_sets"),
            func.count(func.distinct(SetPart.set_num)).label("set_count"),
        )
        .join(owned, owned.c.set_num == SetPart.set_num)
        .group_by(SetPart.part_id)
        .subquery()
    )

    in_sets = func.coalesce(set_agg.c.in_sets, 0)
    set_count = func.coalesce(set_agg.c.set_count, 0)
    loose_qty = func.coalesce(LoosePart.quantity, 0)
    total = in_sets + loose_qty

    base = (
        select(
            Part,
            in_sets.label("in_sets"),
            set_count.label("set_count"),
            loose_qty.label("loose"),
            total.label("total"),
        )
        .outerjoin(set_agg, set_agg.c.part_id == Part.id)
        .outerjoin(LoosePart, LoosePart.part_id == Part.id)
        # only parts you actually own: in an owned set, or added loose
        .where(or_(set_agg.c.part_id.isnot(None), LoosePart.part_id.isnot(None)))
    )

    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            or_(
                Part.name.ilike(like),
                Part.part_num.ilike(like),
                Part.color_name.ilike(like),
            )
        )
    if color:
        base = base.where(Part.color_name == color)
    if membership == "in_sets":
        base = base.where(set_agg.c.part_id.isnot(None))
    elif membership == "has_loose":
        base = base.where(LoosePart.part_id.isnot(None))
    elif membership == "loose_only":
        base = base.where(set_agg.c.part_id.is_(None), LoosePart.part_id.isnot(None))

    lo, hi = _int_or_none(min_qty), _int_or_none(max_qty)
    if lo is not None:
        base = base.where(total >= lo)
    if hi is not None:
        base = base.where(total <= hi)

    sort_map = {
        "name": Part.name,
        "part_num": Part.part_num,
        "color": Part.color_name,
        "in_sets": in_sets,
        "set_count": set_count,
        "loose": loose_qty,
        "total": total,
    }
    order_col = sort_map.get(sort, total)
    order_col = order_col.asc() if dir == "asc" else order_col.desc()

    total_count = db.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar() or 0
    page_num = max(_int_or_none(page) or 1, 1)
    pages = max((total_count + _PAGE_SIZE - 1) // _PAGE_SIZE, 1)
    page_num = min(page_num, pages)

    rows = db.execute(
        base.order_by(order_col, Part.name.asc())
        .limit(_PAGE_SIZE)
        .offset((page_num - 1) * _PAGE_SIZE)
    ).all()
    items = [
        {
            "part": r[0],
            "in_sets": r.in_sets,
            "set_count": r.set_count,
            "loose": r.loose,
            "total": r.total,
        }
        for r in rows
    ]

    colors = db.execute(
        select(Part.color_name)
        .where(Part.color_name.isnot(None))
        .distinct()
        .order_by(Part.color_name)
    ).scalars().all()

    return templates.TemplateResponse(
        "parts_index.html",
        {
            "request": request,
            "items": items,
            "view": view,
            "sort": sort,
            "dir": dir,
            "colors": colors,
            "total_count": total_count,
            "page": page_num,
            "pages": pages,
            "f": {
                "q": q,
                "color": color,
                "membership": membership,
                "min_qty": min_qty,
                "max_qty": max_qty,
            },
        },
    )


@router.get("/parts/new")
def new_part(request: Request, part_num: str = "", q: str = ""):
    try:
        colors = rebrickable.get_colors()
    except rebrickable.RebrickableError:
        colors = []
    results = []
    if q:
        try:
            results = rebrickable.search_parts(q)
        except rebrickable.RebrickableError:
            results = []
    return templates.TemplateResponse(
        "part_new.html",
        {
            "request": request,
            "colors": colors,
            "form": {"part_num": part_num} if part_num else None,
            "error": None,
            "q": q,
            "results": results,
        },
    )


@router.post("/parts")
def create_part(
    request: Request,
    db: Session = Depends(get_db),
    part_num: str = Form(...),
    color_id: str = Form(...),
    quantity: str = Form("1"),
    notes: str = Form(""),
):
    try:
        colors = rebrickable.get_colors()
    except rebrickable.RebrickableError:
        colors = []
    color_name = next(
        (c["name"] for c in colors if str(c["id"]) == color_id), "Unknown"
    )
    qty = _int_or_none(quantity) or 0
    form = {"part_num": part_num, "color_id": color_id, "quantity": quantity, "notes": notes}

    def _error(msg: str):
        return templates.TemplateResponse(
            "part_new.html",
            {"request": request, "colors": colors, "form": form, "error": msg},
            status_code=400,
        )

    if qty <= 0:
        return _error("Quantity must be a positive number.")

    try:
        part = service.add_loose_part(
            db, part_num, _int_or_none(color_id), color_name, qty, notes or None
        )
    except rebrickable.RebrickableError as exc:
        return _error(str(exc))

    db.commit()
    return RedirectResponse(url=f"/parts/{part.id}", status_code=303)


@router.get("/parts/{part_id}")
def part_detail(part_id: int, request: Request, db: Session = Depends(get_db)):
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")

    owned = _owned_copies_subq()
    rows = db.execute(
        select(
            CatalogSet,
            SetPart.quantity.label("qty"),
            SetPart.is_spare.label("is_spare"),
            owned.c.copies.label("copies"),
        )
        .join(SetPart, SetPart.set_num == CatalogSet.set_num)
        .join(owned, owned.c.set_num == CatalogSet.set_num)
        .where(SetPart.part_id == part_id)
        .order_by(CatalogSet.name)
    ).all()

    set_rows = [
        {
            "set": r[0],
            "qty": r.qty,
            "is_spare": r.is_spare,
            "copies": r.copies,
            "contrib": r.qty * r.copies,
        }
        for r in rows
    ]
    in_sets = sum(sr["contrib"] for sr in set_rows)
    set_count = len({sr["set"].set_num for sr in set_rows})

    loose = db.execute(
        select(LoosePart).where(LoosePart.part_id == part_id)
    ).scalar_one_or_none()
    loose_qty = loose.quantity if loose else 0

    return templates.TemplateResponse(
        "part_detail.html",
        {
            "request": request,
            "part": part,
            "set_rows": set_rows,
            "in_sets": in_sets,
            "set_count": set_count,
            "loose": loose,
            "loose_qty": loose_qty,
            "total": in_sets + loose_qty,
        },
    )


@router.post("/parts/{part_id}/loose")
def set_loose(
    part_id: int,
    db: Session = Depends(get_db),
    quantity: str = Form(...),
    notes: str = Form(""),
):
    part = db.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="Part not found")

    qty = _int_or_none(quantity) or 0
    loose = db.execute(
        select(LoosePart).where(LoosePart.part_id == part_id)
    ).scalar_one_or_none()

    if qty <= 0:
        if loose is not None:
            db.delete(loose)
    elif loose is not None:
        loose.quantity = qty
        loose.notes = notes or None
    else:
        db.add(LoosePart(part_id=part_id, quantity=qty, notes=notes or None))

    db.commit()
    return RedirectResponse(url=f"/parts/{part_id}", status_code=303)
