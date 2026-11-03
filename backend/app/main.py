import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .routers import minifigs as minifigs_router
from .routers import parts as parts_router
from .routers import sets as sets_router

settings = get_settings()

app = FastAPI(title="Lego Inventory")

_base_dir = os.path.dirname(__file__)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_base_dir, "static")),
    name="static",
)

# Serve cached assets (set images) straight off the mount.
os.makedirs(settings.assets_dir, exist_ok=True)
app.mount("/assets", StaticFiles(directory=settings.assets_dir), name="assets")

app.include_router(sets_router.router)
app.include_router(parts_router.router)
app.include_router(minifigs_router.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
