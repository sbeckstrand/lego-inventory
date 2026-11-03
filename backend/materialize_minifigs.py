"""One-off: materialise Minifig + SetMinifig rows from already-cached set data.

Run once:  docker compose exec -T app python /app/materialize_minifigs.py

Idempotent — materialize_set_minifigs() clears each set's lines before
re-inserting, so it's safe to re-run.
"""
from sqlalchemy import func, select

from app import service
from app.db import SessionLocal
from app.models import CatalogSet, Minifig, SetMinifig


def main() -> None:
    db = SessionLocal()
    catalogs = db.execute(select(CatalogSet)).scalars().all()
    cache: dict[str, Minifig] = {}

    for c in catalogs:
        service.materialize_set_minifigs(db, c, cache=cache)
        db.commit()

    figs = db.execute(select(func.count()).select_from(Minifig)).scalar()
    lines = db.execute(select(func.count()).select_from(SetMinifig)).scalar()
    print(f"sets processed={len(catalogs)}  set_minifig lines={lines}  distinct minifigs={figs}")


if __name__ == "__main__":
    main()
