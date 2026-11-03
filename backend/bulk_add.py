"""One-off bulk importer for the initial garage inventory.

Run ONCE:  docker compose exec -T -e FORCE=1 app python /app/bulk_add.py

Creates one owned row per physical copy listed below. A set is fetched from
Rebrickable only the first time it's seen (catalog data is cached in the DB),
so duplicates and rate limits are handled gracefully. Individual failures are
reported and skipped — safe to patch those up afterwards. Re-running the whole
script would duplicate every owned row, so it refuses if the inventory is
already populated (set FORCE=1 to override).

Notes for this run:
  - 76409 is omitted from Bin 1 because it was already added by hand.
  - Bin 8 ("opened") maps to location "Bin 8" + status "In bags".
  - MOC-* entries are skipped (not served by the Rebrickable /sets/ endpoint).
"""
import os
import time

import httpx
from sqlalchemy import func, select

from app import rebrickable, service
from app.db import SessionLocal
from app.models import CatalogSet, OwnedSet

IN_BAGS_BINS = {"Bin 8"}

BINS: dict[str, list[str]] = {
    # 76409 intentionally omitted — already in the inventory.
    "Bin 1": ["76382", "40577", "76383", "40577", "76385", "76396", "76384",
              "76397", "76398", "76388", "76424", "76392", "76388", "40419",
              "30392", "30392", "30677", "30692", "30651"],
    "Bin 2": ["75357", "75389", "75254", "75433", "75330", "40557", "30654",
              "30728", "75391", "75345", "75448", "75265", "75436", "75345",
              "75345", "75320", "75266", "75344", "75411", "75310", "75266"],
    "Bin 3": ["75380", "75362", "75312", "75300", "40806", "75269", "75333",
              "75333", "40917", "75280", "40665", "75372", "74266", "75426",
              "77046", "71752", "30662", "60333", "30661", "30558", "30671",
              "30663", "30590", "30434", "30434", "30434", "30390", "30687"],
    "Bin 4": ["76389", "76395", "76439", "76387", "76386", "43264", "73217",
              "43210", "10369", "43212", "40486", "21164", "40527", "21177",
              "30572"],
    "Bin 5": ["66786", "76781", "76780", "10329", "77093", "21340", "21331",
              "77256", "40422"],
    "Bin 6": ["31109", "11717", "40772", "40772", "40772", "40393", "31134",
              "40468", "66789", "31102", "40417", "76914", "42167", "40220",
              "30687", "30724", "30726", "30716", "30732", "30716"],
    "Bin 7": ["66790", "76323", "76334", "76207", "40573", "10372", "40709",
              "76158", "76307", "76335", "76202", "76202", "21329", "76308",
              "76337", "11206", "10789", "76275", "76253", "10781", "76171",
              "30679", "30652", "30454", "30443", "30443"],
    "Bin 8": ["76432", "40460", "43242", "21319", "62179", "40619", "10361",
              "MOC-163584", "76321", "76383", "MOC-155049", "40516", "31147",
              "76382", "76385", "40425", "31140", "75423", "70795", "75387",
              "76317", "10311", "75387", "10361", "76384", "21357", "11203"],
}


def status_for(bin_name: str) -> str:
    return "In bags" if bin_name in IN_BAGS_BINS else "In box"


def ensure_catalog(db, set_num: str, attempts: int = 4) -> None:
    """Fetch+cache a set, retrying on rate-limit (429). A 404 raises at once."""
    for i in range(attempts):
        try:
            service.fetch_and_cache_catalog(db, set_num)
            db.commit()
            return
        except rebrickable.RebrickableError:
            db.rollback()
            raise
        except httpx.HTTPStatusError as exc:
            db.rollback()
            if exc.response is not None and exc.response.status_code == 429 and i < attempts - 1:
                time.sleep(2 * (i + 1))
                continue
            raise


def main() -> None:
    db = SessionLocal()

    existing = db.execute(select(func.count()).select_from(OwnedSet)).scalar() or 0
    if existing and os.environ.get("FORCE") != "1":
        print(f"Refusing: owned_set already has {existing} rows. Set FORCE=1 to add anyway.")
        return

    added = 0
    skipped_moc: list[str] = []
    failed: list[tuple[str, str]] = []
    ensured: set[str] = set()

    for bin_name, nums in BINS.items():
        status = status_for(bin_name)
        for raw in nums:
            if raw.upper().startswith("MOC"):
                skipped_moc.append(raw)
                continue
            set_num = rebrickable.normalize_set_num(raw)
            try:
                if set_num not in ensured:
                    if db.get(CatalogSet, set_num) is None:
                        ensure_catalog(db, set_num)
                        time.sleep(0.4)
                    ensured.add(set_num)
                db.add(OwnedSet(set_num=set_num, storage_location=bin_name, status=status))
                db.commit()
                added += 1
                print(f"  + {raw:>12} -> {bin_name}")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                failed.append((raw, f"{type(exc).__name__}: {str(exc)[:100]}"))
                print(f"  ! {raw:>12} FAILED: {type(exc).__name__}: {str(exc)[:80]}")

    print("\n==== IMPORT SUMMARY ====")
    print(f"owned rows added:      {added}")
    print(f"distinct sets fetched: {len(ensured)}")
    print(f"skipped MOCs ({len(skipped_moc)}): {', '.join(skipped_moc) or '-'}")
    print(f"failed ({len(failed)}):")
    for raw, reason in failed:
        print(f"    {raw}: {reason}")


if __name__ == "__main__":
    main()
