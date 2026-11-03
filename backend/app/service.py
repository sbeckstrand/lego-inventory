"""Business logic that ties the API client, storage, and database together."""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import rebrickable, storage
from .models import (
    CatalogSet,
    LooseMinifig,
    LoosePart,
    Minifig,
    Part,
    SetMinifig,
    SetPart,
)


def get_or_create_part(
    db: Session,
    part_num: str,
    color_name: str,
    name: str,
    img_url: str | None,
    color_id: int | None = None,
    cache: dict[tuple[str, str], Part] | None = None,
) -> Part:
    """Find a part by (part_num, color_name) or create it.

    ``cache`` is an optional in-memory map used to avoid repeated lookups when
    materialising many sets at once.
    """
    key = (part_num, color_name)
    if cache is not None and key in cache:
        return cache[key]

    part = db.execute(
        select(Part).where(Part.part_num == part_num, Part.color_name == color_name)
    ).scalar_one_or_none()

    if part is None:
        part = Part(
            part_num=part_num,
            color_name=color_name,
            name=name,
            img_url=img_url,
            color_id=color_id,
        )
        db.add(part)
        db.flush()
    else:
        if not part.img_url and img_url:
            part.img_url = img_url
        if part.color_id is None and color_id is not None:
            part.color_id = color_id

    if cache is not None:
        cache[key] = part
    return part


def materialize_set_parts(
    db: Session,
    catalog: CatalogSet,
    cache: dict[tuple[str, str], Part] | None = None,
) -> None:
    """Replace the materialised SetPart rows for a set from its cached parts."""
    db.execute(delete(SetPart).where(SetPart.set_num == catalog.set_num))
    for line in catalog.parts or []:
        part_num = line.get("part_num")
        if not part_num:
            continue
        color_name = line.get("color") or "Unknown"
        part = get_or_create_part(
            db,
            part_num=part_num,
            color_name=color_name,
            name=line.get("name") or part_num,
            img_url=line.get("img_url"),
            cache=cache,
        )
        db.add(
            SetPart(
                set_num=catalog.set_num,
                part_id=part.id,
                quantity=line.get("quantity") or 0,
                is_spare=bool(line.get("is_spare")),
            )
        )
    db.flush()


def get_or_create_minifig(
    db: Session,
    fig_num: str,
    name: str,
    img_url: str | None,
    cache: dict[str, Minifig] | None = None,
) -> Minifig:
    """Find a minifig by fig number or create it."""
    if cache is not None and fig_num in cache:
        return cache[fig_num]

    mf = db.execute(
        select(Minifig).where(Minifig.fig_num == fig_num)
    ).scalar_one_or_none()

    if mf is None:
        mf = Minifig(fig_num=fig_num, name=name, img_url=img_url)
        db.add(mf)
        db.flush()
    elif not mf.img_url and img_url:
        mf.img_url = img_url

    if cache is not None:
        cache[fig_num] = mf
    return mf


def materialize_set_minifigs(
    db: Session,
    catalog: CatalogSet,
    cache: dict[str, Minifig] | None = None,
) -> None:
    """Replace the materialised SetMinifig rows for a set from its cache."""
    db.execute(delete(SetMinifig).where(SetMinifig.set_num == catalog.set_num))
    for line in catalog.minifigs or []:
        fig_num = line.get("fig_num")
        if not fig_num:
            continue
        mf = get_or_create_minifig(
            db,
            fig_num=fig_num,
            name=line.get("name") or fig_num,
            img_url=line.get("img_url"),
            cache=cache,
        )
        db.add(
            SetMinifig(
                set_num=catalog.set_num,
                minifig_id=mf.id,
                quantity=line.get("quantity") or 0,
            )
        )
    db.flush()


def fetch_and_cache_catalog(db: Session, set_num: str) -> CatalogSet:
    """Fetch a set's design data from Rebrickable and upsert the catalog row.

    Also materialises the set's part and minifig lines for aggregation. The
    caller is responsible for committing the session.
    """
    set_num = rebrickable.normalize_set_num(set_num)

    data = rebrickable.get_set(set_num)
    parts = rebrickable.get_set_parts(set_num)
    minifigs = rebrickable.get_set_minifigs(set_num)
    theme_info = rebrickable.resolve_theme(data.get("theme_id"))
    image_path = storage.download_set_image(set_num, data.get("set_img_url"))

    catalog = db.get(CatalogSet, set_num)
    if catalog is None:
        catalog = CatalogSet(set_num=set_num)
        db.add(catalog)

    catalog.name = data.get("name") or set_num
    catalog.year = data.get("year")
    catalog.num_parts = data.get("num_parts") or 0
    catalog.theme_id = theme_info["theme_id"]
    catalog.theme = theme_info["theme"] or theme_info["theme_name"]
    catalog.image_url = data.get("set_img_url")
    catalog.image_path = image_path
    catalog.parts = parts
    catalog.minifigs = minifigs

    db.flush()
    materialize_set_parts(db, catalog)
    materialize_set_minifigs(db, catalog)
    return catalog


def add_loose_part(
    db: Session,
    part_num: str,
    color_id: int | None,
    color_name: str,
    quantity: int,
    notes: str | None = None,
) -> Part:
    """Fetch a part from Rebrickable and add/increment a loose-part entry.

    Loose parts are never tied to a set. Returns the Part. Caller commits.
    """
    part_num = rebrickable.get_part(part_num).get("part_num") or part_num.strip()
    data = rebrickable.get_part(part_num)
    name = data.get("name") or part_num
    img = rebrickable.get_part_color_image(part_num, color_id) or data.get("part_img_url")

    part = get_or_create_part(
        db,
        part_num=part_num,
        color_name=color_name,
        name=name,
        img_url=img,
        color_id=color_id,
    )
    if img and not part.img_url:
        part.img_url = img

    loose = db.execute(
        select(LoosePart).where(LoosePart.part_id == part.id)
    ).scalar_one_or_none()
    if loose is None:
        loose = LoosePart(part_id=part.id, quantity=quantity, notes=notes or None)
        db.add(loose)
    else:
        loose.quantity += quantity
        if notes:
            loose.notes = notes

    db.flush()
    return part


def add_loose_minifig(
    db: Session,
    fig_num: str,
    quantity: int,
    notes: str | None = None,
) -> Minifig:
    """Fetch a minifig from Rebrickable and add/increment a loose-minifig entry.

    Loose minifigs are never tied to a set. Returns the Minifig. Caller commits.
    """
    data = rebrickable.get_minifig(fig_num)
    fig_num = data.get("set_num") or fig_num.strip()
    # The /minifigs/ endpoints return the name as `name` (the /sets/.../minifigs/
    # inventory endpoint is the one that uses `set_name`).
    name = data.get("name") or fig_num
    img = data.get("set_img_url")

    mf = get_or_create_minifig(db, fig_num=fig_num, name=name, img_url=img)
    if img and not mf.img_url:
        mf.img_url = img

    loose = db.execute(
        select(LooseMinifig).where(LooseMinifig.minifig_id == mf.id)
    ).scalar_one_or_none()
    if loose is None:
        loose = LooseMinifig(minifig_id=mf.id, quantity=quantity, notes=notes or None)
        db.add(loose)
    else:
        loose.quantity += quantity
        if notes:
            loose.notes = notes

    db.flush()
    return mf
