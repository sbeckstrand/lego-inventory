# Lego Inventory

A small web app for tracking the Lego **sets** you own — where each one is
stored, its condition, and whether it's still boxed, bagged, or assembled.
Set details (name, part count, image, parts list, minifigs) are pulled from the
[Rebrickable API](https://rebrickable.com/api/) and cached locally.

## Stack

- **FastAPI** + server-rendered Jinja templates (no JS build step)
- **PostgreSQL** via SQLAlchemy 2.0, migrations with **Alembic**
- **Rebrickable** for set data and images
- Set images cached to a mounted assets directory

## Data model

Two tables, so you can own several copies of the same set without duplicating
the fetched catalog data:

- **`catalog_set`** — API-derived, shared across copies. Keyed by Rebrickable
  set number (e.g. `75192-1`): name, year, part count, image, and the full
  parts + minifig lists (JSONB).
- **`owned_set`** — one row per physical set you own: purchased date, storage
  location, notes, condition (New / Like New / Moderate / Poor), and status
  (In box / In bags / Assembled).

## Local development

1. Get a free Rebrickable API key:
   <https://rebrickable.com/users/>  → Settings → API.

2. Create your `.env`:

   ```bash
   cp .env.example .env
   # then paste your key into REBRICKABLE_API_KEY
   ```

3. Start the stack:

   ```bash
   docker compose up --build
   ```

   The `app` container waits for Postgres, runs `alembic upgrade head`, then
   serves on <http://localhost:8000> (also reachable from your phone on the LAN
   at `http://<your-machine-ip>:8000`). Source is bind-mounted with live reload.

4. Open the app, click **+ Add set**, and enter a set number like `75192`.

## How this maps to prod (local k8s)

The dev compose file is intentionally shaped like the eventual deployment:

| Concern   | Local dev (compose)                     | Prod (k8s)                                  |
| --------- | --------------------------------------- | ------------------------------------------- |
| App       | `app` service (one container)           | Deployment + Service                        |
| Database  | throwaway `postgres:16` container       | your existing Postgres server via `DATABASE_URL` |
| Assets    | `./data/assets` bind mount at `/data/assets` | NFS-backed PVC mounted at `/data/assets` |
| Config    | `.env` + compose `environment`          | ConfigMap + Secret                          |

Because the container path (`/data/assets`) and env var names are identical,
moving to k8s is just a matter of swapping compose for a Helm chart — no code
changes. (Helm chart + CI are intentionally out of scope for now.)

## Migrations

```bash
# create a new migration after changing models.py
docker compose exec app alembic revision --autogenerate -m "describe change"
# apply
docker compose exec app alembic upgrade head
```

## Configuration

| Env var                | Default                                        | Purpose                        |
| ---------------------- | ---------------------------------------------- | ------------------------------ |
| `DATABASE_URL`         | `postgresql+psycopg://lego:lego@db:5432/lego`  | SQLAlchemy connection URL      |
| `REBRICKABLE_API_KEY`  | *(required)*                                   | Rebrickable API key            |
| `REBRICKABLE_BASE_URL` | `https://rebrickable.com/api/v3/lego`          | API base URL                   |
| `ASSETS_DIR`           | `/data/assets`                                 | Where set images are cached    |
