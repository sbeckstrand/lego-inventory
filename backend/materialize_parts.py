"""One-off: materialise Part + SetPart rows from already-cached set data.

Run once:  docker compose exec -T app python /app/materialize_parts.py

Idempotent — materialize_set_parts() clears each set's lines before
re-inserting, so it's safe to re-run.
"""
from sqlalchemy import func, select

from app import service
from app.db import SessionLocal
from app.models import CatalogSet, Part, SetPart


def main() -> None:
    db = SessionLocal()
    catalogs = db.execute(select(CatalogSet)).scalars().all()
    cache: dict[tuple[str, str], Part] = {}

    for c in catalogs:
        service.materialize_set_parts(db, c, cache=cache)
        db.commit()

    parts = db.execute(select(func.count()).select_from(Part)).scalar()
    lines = db.execute(select(func.count()).select_from(SetPart)).scalar()
    print(f"sets processed={len(catalogs)}  set_part lines={lines}  distinct parts={parts}")


if __name__ == "__main__":
    main()
