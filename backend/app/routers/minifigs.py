from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import rebrickable, service
from ..db import get_db
from ..models import CatalogSet, LooseMinifig, Minifig, OwnedSet, SetMinifig
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
    return (
        select(OwnedSet.set_num.label("set_num"), func.count().label("copies"))
        .group_by(OwnedSet.set_num)
        .subquery()
    )


@router.get("/minifigs")
def minifigs_index(
    request: Request,
    db: Session = Depends(get_db),
    view: str = "cards",
    sort: str = "total",
    dir: str = "desc",
    q: str = "",
    membership: str = "",
    min_qty: str = "",
    max_qty: str = "",
    page: str = "1",
):
    owned = _owned_copies_subq()
    set_agg = (
        select(
            SetMinifig.minifig_id.label("minifig_id"),
            func.sum(SetMinifig.quantity * owned.c.copies).label("in_sets"),
            func.count(func.distinct(SetMinifig.set_num)).label("set_count"),
        )
        .join(owned, owned.c.set_num == SetMinifig.set_num)
        .group_by(SetMinifig.minifig_id)
        .subquery()
    )

    in_sets = func.coalesce(set_agg.c.in_sets, 0)
    set_count = func.coalesce(set_agg.c.set_count, 0)
    loose_qty = func.coalesce(LooseMinifig.quantity, 0)
    total = in_sets + loose_qty

    base = (
        select(
            Minifig,
            in_sets.label("in_sets"),
            set_count.label("set_count"),
            loose_qty.label("loose"),
            total.label("total"),
        )
        .outerjoin(set_agg, set_agg.c.minifig_id == Minifig.id)
        .outerjoin(LooseMinifig, LooseMinifig.minifig_id == Minifig.id)
        .where(or_(set_agg.c.minifig_id.isnot(None), LooseMinifig.minifig_id.isnot(None)))
    )

    if q:
        like = f"%{q.strip()}%"
        base = base.where(or_(Minifig.name.ilike(like), Minifig.fig_num.ilike(like)))
    if membership == "in_sets":
        base = base.where(set_agg.c.minifig_id.isnot(None))
    elif membership == "has_loose":
        base = base.where(LooseMinifig.minifig_id.isnot(None))
    elif membership == "loose_only":
        base = base.where(set_agg.c.minifig_id.is_(None), LooseMinifig.minifig_id.isnot(None))

    lo, hi = _int_or_none(min_qty), _int_or_none(max_qty)
    if lo is not None:
        base = base.where(total >= lo)
    if hi is not None:
        base = base.where(total <= hi)

    sort_map = {
        "name": Minifig.name,
        "fig_num": Minifig.fig_num,
        "in_sets": in_sets,
        "loose": loose_qty,
        "total": total,
        "set_count": set_count,
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
        base.order_by(order_col, Minifig.name.asc())
        .limit(_PAGE_SIZE)
        .offset((page_num - 1) * _PAGE_SIZE)
    ).all()
    items = [
        {
            "fig": r[0],
            "in_sets": r.in_sets,
            "set_count": r.set_count,
            "loose": r.loose,
            "total": r.total,
        }
        for r in rows
    ]

    return templates.TemplateResponse(
        "minifigs_index.html",
        {
            "request": request,
            "items": items,
            "view": view,
            "sort": sort,
            "dir": dir,
            "total_count": total_count,
            "page": page_num,
            "pages": pages,
            "f": {"q": q, "membership": membership, "min_qty": min_qty, "max_qty": max_qty},
        },
    )


@router.get("/minifigs/new")
def new_minifig(request: Request, fig_num: str = "", q: str = ""):
    results = []
    if q:
        try:
            results = rebrickable.search_minifigs(q)
        except rebrickable.RebrickableError:
            results = []
    return templates.TemplateResponse(
        "minifig_new.html",
        {
            "request": request,
            "q": q,
            "results": results,
            "form": {"fig_num": fig_num} if fig_num else None,
            "error": None,
        },
    )


@router.post("/minifigs")
def create_minifig(
    request: Request,
    db: Session = Depends(get_db),
    fig_num: str = Form(...),
    quantity: str = Form("1"),
    notes: str = Form(""),
):
    qty = _int_or_none(quantity) or 0
    form = {"fig_num": fig_num, "quantity": quantity, "notes": notes}

    def _error(msg: str):
        return templates.TemplateResponse(
            "minifig_new.html",
            {"request": request, "q": "", "results": [], "form": form, "error": msg},
            status_code=400,
        )

    if qty <= 0:
        return _error("Quantity must be a positive number.")

    try:
        mf = service.add_loose_minifig(db, fig_num, qty, notes or None)
    except rebrickable.RebrickableError as exc:
        return _error(str(exc))

    db.commit()
    return RedirectResponse(url=f"/minifigs/{mf.id}", status_code=303)


@router.get("/minifigs/{minifig_id}")
def minifig_detail(minifig_id: int, request: Request, db: Session = Depends(get_db)):
    fig = db.get(Minifig, minifig_id)
    if fig is None:
        raise HTTPException(status_code=404, detail="Minifig not found")

    owned = _owned_copies_subq()
    rows = db.execute(
        select(
            CatalogSet,
            SetMinifig.quantity.label("qty"),
            owned.c.copies.label("copies"),
        )
        .join(SetMinifig, SetMinifig.set_num == CatalogSet.set_num)
        .join(owned, owned.c.set_num == CatalogSet.set_num)
        .where(SetMinifig.minifig_id == minifig_id)
        .order_by(CatalogSet.name)
    ).all()

    set_rows = [
        {"set": r[0], "qty": r.qty, "copies": r.copies, "contrib": r.qty * r.copies}
        for r in rows
    ]
    in_sets = sum(sr["contrib"] for sr in set_rows)
    set_count = len({sr["set"].set_num for sr in set_rows})

    loose = db.execute(
        select(LooseMinifig).where(LooseMinifig.minifig_id == minifig_id)
    ).scalar_one_or_none()
    loose_qty = loose.quantity if loose else 0

    return templates.TemplateResponse(
        "minifig_detail.html",
        {
            "request": request,
            "fig": fig,
            "set_rows": set_rows,
            "in_sets": in_sets,
            "set_count": set_count,
            "loose": loose,
            "loose_qty": loose_qty,
            "total": in_sets + loose_qty,
        },
    )


@router.post("/minifigs/{minifig_id}/loose")
def set_loose(
    minifig_id: int,
    db: Session = Depends(get_db),
    quantity: str = Form(...),
    notes: str = Form(""),
):
    fig = db.get(Minifig, minifig_id)
    if fig is None:
        raise HTTPException(status_code=404, detail="Minifig not found")

    qty = _int_or_none(quantity) or 0
    loose = db.execute(
        select(LooseMinifig).where(LooseMinifig.minifig_id == minifig_id)
    ).scalar_one_or_none()

    if qty <= 0:
        if loose is not None:
            db.delete(loose)
    elif loose is not None:
        loose.quantity = qty
        loose.notes = notes or None
    else:
        db.add(LooseMinifig(minifig_id=minifig_id, quantity=qty, notes=notes or None))

    db.commit()
    return RedirectResponse(url=f"/minifigs/{minifig_id}", status_code=303)
