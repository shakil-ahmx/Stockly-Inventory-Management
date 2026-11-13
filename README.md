# ▦ Stockly — Inventory Management (Flask + PostgreSQL)

REST API + a fast single-page dashboard (light / dark / auto, mobile friendly).

**Features** — product & category CRUD · audited stock changes (add / remove / set exact count, row-locked,
never negative) · search, category & stock-level filters, sortable columns, pagination · clickable
low-stock / out-of-stock cards · activity feed · CSV export · multi-currency display · optional login.

## Run with Docker
    docker compose up --build
    docker compose exec web flask --app run seed     # optional sample data
Open http://localhost:5000

## Run locally
    python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env                                   # set DATABASE_URL (createdb inventory first)
    flask --app run seed
    python run.py

## Optional password
Set `BASIC_AUTH=user:password` (env / `.env` / docker-compose) to put the UI **and** API behind a login prompt.
Do this before exposing the app on a public URL. `/api/health` stays open for uptime checks.

## API
| Method | Endpoint | Notes |
|---|---|---|
| GET | `/api/products` | `q`, `category_id` (0 = none), `status` (ok/low/out), `sort` (`-price`, `name`…), `page`, `per_page` ≤100 |
| GET | `/api/products/export.csv` | Same filters, Excel-safe CSV |
| POST | `/api/products` | `{sku,name,price,quantity,reorder_level,category_id,description}` — SKU is upper-cased |
| GET / DELETE | `/api/products/{id}` | |
| PUT / PATCH | `/api/products/{id}` | PUT needs sku+name, PATCH is partial. Quantity changes only via `/adjust` |
| POST | `/api/products/{id}/adjust` | `{"change": -3, "reason": "Sale"}` or `{"set": 120}` |
| GET | `/api/products/{id}/movements` | History (`limit` ≤200) |
| GET | `/api/movements` | Activity feed, cursor `?before=<id>` |
| GET / POST | `/api/categories` | List (with product counts) / create |
| PUT / DELETE | `/api/categories/{id}` | Rename / delete (products become uncategorized) |
| GET | `/api/stats` | Totals |
| GET | `/api/health` | DB ping |

Stock status: **out** = 0, **low** = 1…reorder level, **ok** = above reorder level.
Errors: `{"error": "...", "details": {"field": "..."}}` with 400 / 404 / 409 / 422 / 500.

## Tests
    pip install -r requirements-dev.txt
    pytest                                    # in-memory SQLite
    TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost/test pytest   # real Postgres

## Free-tier friendly
2 gunicorn workers × 2 threads, small connection pool, indexed queries, one aggregate query for stats,
paginated lists, long-lived cached static files (cache-busted per deploy), no frontend build step.
Works on Render / Railway / Fly / Neon / Supabase — set `DATABASE_URL`, start with `gunicorn run:app`.
