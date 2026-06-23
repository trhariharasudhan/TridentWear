# TridentWear — Operations Runbook

This document serves as the guide for systems administrators, developers, and DevOps engineers managing the TridentWear production application.

---

## 1. Deployment Procedures

### Railway Deployment
1. Connect the GitHub repository to the Railway project.
2. In the Railway dashboard, provision a **PostgreSQL Database** service.
3. Railway automatically sets `DATABASE_URL` for the backend service.
4. Set all required environment variables under the **Variables** tab of the backend service (see `docs/ENV_SETUP.md`).
5. Ensure the build command is set to:
   ```bash
   pip install -r requirements.txt
   ```
6. Ensure the start command runs the migrations before starting the server:
   ```bash
   alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
   ```

### Render Deployment
1. Create a new **PostgreSQL Database** on Render. Copy the Internal Database URL.
2. Create a new **Web Service** pointing to the TridentWear repository.
3. Add the following environment variables:
   * `ENVIRONMENT=production`
   * `DB_MODE=postgres`
   * `DATABASE_URL=your-copied-database-url`
   * (Other variables from `docs/ENV_SETUP.md`)
4. Set the build command:
   ```bash
   pip install -r requirements.txt
   ```
5. Set the start command:
   ```bash
   alembic upgrade head && uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
   ```

---

## 2. Database Migrations

Database schemas are managed using Alembic. 

### Running Migrations Manually
When SSHed into the host or running in a release step, execute:
```bash
alembic upgrade head
```

### Rollback Migration
To revert the last applied migration:
```bash
alembic downgrade -1
```

### Create a New Migration
If models in `backend/app/db/models.py` change, generate a new migration:
```bash
alembic revision --autogenerate -m "description of changes"
```
*Note: This requires a live running database configured via `DATABASE_URL` or `PG_DSN`.*

---

## 3. Database Backups & Restore

### Database Backup
Run the following command to dump the PostgreSQL database structure and data:
```powershell
# Windows PowerShell
pg_dump "$env:DATABASE_URL" -Fc -f tridentwear-backup.dump

# Linux / macOS
pg_dump "$DATABASE_URL" -Fc -f tridentwear-backup.dump
```
> ⚠️ Never store backups containing sensitive user/payment data inside the Git repository.

### Database Restore
To restore from a backup:
```bash
pg_restore -d "$DATABASE_URL" --clean --no-owner tridentwear-backup.dump
```

---

## 4. Administrative User Management

### Promoting a User to Admin
To promote a user to an administrative role, connect to the database via `psql` or use the Admin panel to update their role to `"admin"`:
```sql
UPDATE users SET role = 'admin' WHERE email = 'target_email@example.com';
```

### Deactivating/Blocking a User
To block a user (which immediately revokes access even with valid sessions/JWTs):
```sql
UPDATE users SET is_active = false WHERE id = <user_id>;
```

---

## 5. Secret Rotation

In the event of a security compromise or as part of periodic policy updates, environment secrets can be safely rotated:

1. **Rotate JWT & Session Secrets:**
   * Generate new 64-character random hex strings:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   * Replace `TRIDENT_JWT_SECRET` and `TRIDENT_SESSION_SECRET` in environment configurations.
   * *Impact:* All currently signed-in users will be instantly logged out and must sign in again.
2. **Rotate Razorpay Keys:**
   * Generate new API keys in the Razorpay Dashboard.
   * Update `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`.
   * *Impact:* Active checkout sessions will need to re-initialize payment requests.

---

## 6. Incident Response & Troubleshooting

### Database is Unavailable
* **Symptom:** API routes return `500 Internal Server Error`, logs show `SQLAlchemyError` or connection timeouts.
* **Action:**
  1. Verify the PostgreSQL service is active.
  2. Verify credentials in `DATABASE_URL`.
  3. Ensure network security rules or PG firewalls allow connections from the web service host.

### SMTP Mail Failure
* **Symptom:** Order confirmations or welcome emails are not arriving.
* **Action:**
  1. The application fails gracefully and does not block order completion if SMTP is unconfigured.
  2. Check logs for SMTP connection/login errors.
  3. Verify port `587` is open on the hosting provider (some hosts block outbound port 25/587).

### Razorpay Webhook Signatures Fail
* **Symptom:** Webhook logs show `400 Bad Request` or signature verification errors.
* **Action:**
  1. Verify `RAZORPAY_WEBHOOK_SECRET` exactly matches the secret defined in the Razorpay Webhook dashboard configuration.
  2. Ensure the payload is not modified before verification (the raw request body must be used).
