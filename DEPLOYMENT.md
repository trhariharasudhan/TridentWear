# TridentWear Deployment Notes

TridentWear serves the FastAPI API and static storefront from one origin. Keep frontend API calls relative, for example `/api/v1/products`, so localhost, Render, Railway, and a VPS all use the same route shape.

## Local

```powershell
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8020
```

Open `http://127.0.0.1:8000`.

## Render

Use a Python or Docker service.

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set environment variables from `.env.example`. Use strong production values for `TRIDENT_JWT_SECRET` and `TRIDENT_SESSION_SECRET`.

## Railway

`railway.json` uses:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Deploy with `DB_MODE=json` for the current file-backed setup, or configure `DB_MODE=postgres` and `PG_DSN` when the database migration is complete.

## VPS

Install Python dependencies, copy the repo, set environment variables, then run the same command behind a reverse proxy:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Terminate HTTPS at Nginx/Caddy and proxy to `127.0.0.1:8000`.

## Production Checklist

- Set `ENVIRONMENT=production`.
- Set strong `TRIDENT_JWT_SECRET` and `TRIDENT_SESSION_SECRET`.
- Set `TRIDENT_OTP_PROVIDER` to a real SMS provider implementation before public launch. The `dev` provider prints OTPs and is only for local/staging.
- Set Razorpay live keys after test checkout is signed off.
- Confirm `/api/v1/products`, `/products`, `/cart`, `/checkout`, `/login`, `/register`, `/track`, and `/admin` return 200.
- Confirm `/assets/css/styles.css` and page JS files return 200.
- Back up the `db/` directory if using JSON storage.
- Move to Postgres before high traffic or multi-instance deployment.

## PostgreSQL Migration

The app is still safe to run with JSON while staging launch flows. For production readiness, use the staged Postgres path:

```powershell
pip install -r requirements.txt
alembic upgrade head
python backend/scripts/migrate_json_to_postgres.py --dry-run
python backend/scripts/migrate_json_to_postgres.py
python backend/scripts/verify_data_parity.py
```

Keep JSON files untouched until parity is confirmed and backups exist. Only archive them manually with:

```powershell
python backend/scripts/verify_data_parity.py --archive-json
```

Recommended cutover:

1. Run with `DB_MODE=json` locally.
2. Run migration dry-run and fix any validation issues.
3. Run Alembic and migration on staging.
4. Test `DB_MODE=dual_write`.
5. Switch to `DB_MODE=postgres` after parity and smoke tests pass.

## Staging Test Orders

Checkout includes a staging test-order option. Orders created with `test_mode=true` are marked `TEST` in admin and do not reduce product stock. Do not use test orders for real fulfillment.

## Observability

Backend API responses include `request_id`. Structured logs write to `logs/app.log` with request, status, timing, and user context where available. The frontend stores recent runtime errors in local storage under `tridentwear-frontend-errors` for staging triage.
