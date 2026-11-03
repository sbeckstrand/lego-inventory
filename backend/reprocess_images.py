"""One-off: re-cache every set image as a normalised transparent PNG.

Run once:  docker compose exec -T app python /app/reprocess_images.py

Re-downloads each set image from its stored source URL, strips solid
backgrounds, downscales, saves as .png, updates catalog_set.image_path, and
removes the old file. Idempotent — safe to re-run.
"""
import os
import time

from sqlalchemy import select

from app import storage
from app.db import SessionLocal
from app.models import CatalogSet


def main() -> None:
    db = SessionLocal()
    rows = db.execute(select(CatalogSet)).scalars().all()
    updated = skipped = failed = 0

    for c in rows:
        if not c.image_url:
            skipped += 1
            continue
        old = c.image_path
        new = storage.download_set_image(c.set_num, c.image_url)
        if not new:
            failed += 1
            print(f"  ! {c.set_num}: failed")
            continue
        c.image_path = new
        db.commit()
        if old and old != new:
            old_path = os.path.join(storage.settings.assets_dir, old)
            try:
                if os.path.exists(old_path):
                    os.remove(old_path)
            except OSError:
                pass
        updated += 1
        print(f"  + {c.set_num} -> {new}")
        time.sleep(0.15)

    print(f"\nupdated={updated} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
