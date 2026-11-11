import os
from pathlib import Path
from typing import Optional, Union
from app.db.database import DatabaseInterface, JsonDatabaseAdapter, PostgresDatabaseAdapter, DualWriteDatabaseAdapter

class UnsafeTestDatabaseError(RuntimeError):
    """Raised when test mode attempts to resolve to an unsafe, non-isolated, or production database."""
    pass

def get_default_db_dir() -> Path:
    """Returns the default development database directory (e.g. repo/db)."""
    return (Path(__file__).resolve().parent.parent.parent.parent / "db").resolve()

def is_test_mode() -> bool:
    """Checks whether test mode is active via environment variables or test runners."""
    if os.getenv("TRIDENT_TEST_MODE", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.getenv("ENVIRONMENT", "").strip().lower() in ("testing", "test"):
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    return False

def is_production_database_url(dsn: str) -> bool:
    """Checks whether a database URL appears to target production or external non-test hosts."""
    if not dsn:
        return False
    lower_dsn = dsn.lower()
    dangerous_keywords = (
        "prod",
        "production",
        "tridentwear.in",
        "amazonaws.com",
        "rds.",
        "neon.tech",
        "supabase.co",
        "cloud.cockroachlabs.com",
        "azure.com",
        "digitaloceanspaces.com",
    )
    for kw in dangerous_keywords:
        if kw in lower_dsn:
            return True
    return False

def get_db_dir() -> Path:
    """
    Resolves the active database directory.
    Priority:
    1. app.db.database.DB_DIR if monkeypatched to something other than DEFAULT_DB_DIR
    2. TRIDENT_DB_DIR environment variable
    3. If is_test_mode() and no isolated dir configured, fail closed.
    4. Otherwise DEFAULT_DB_DIR.
    """
    default_dir = get_default_db_dir()

    # 1. Check module-level DB_DIR for backward-compatibility with monkeypatched tests
    import app.db.database as db_mod
    monkeypatched = getattr(db_mod, "DB_DIR", None)
    if monkeypatched is not None and Path(monkeypatched).resolve() != default_dir:
        return Path(monkeypatched).resolve()

    # 2. Check TRIDENT_DB_DIR environment variable
    custom_dir = os.getenv("TRIDENT_DB_DIR", "").strip()
    if custom_dir:
        resolved = Path(custom_dir).resolve()
        if is_test_mode() and resolved == default_dir:
            raise UnsafeTestDatabaseError(
                f"[SAFETY GUARD] Test mode cannot run against the development database directory: '{resolved}'."
            )
        return resolved

    # 3. If in test mode and no isolated directory was provided: FAIL CLOSED
    if is_test_mode():
        raise UnsafeTestDatabaseError(
            f"[SAFETY GUARD] Test mode is active, but TRIDENT_DB_DIR is not configured and defaults to "
            f"development database '{default_dir}'. Test execution aborted to prevent database contamination."
        )

    return default_dir

def validate_db_safety(db_dir: Optional[Path] = None, dsn: Optional[str] = None):
    """Fails closed if test mode points to the real development DB directory or production DB."""
    if is_test_mode():
        resolved_dir = (db_dir if db_dir is not None else get_db_dir()).resolve()
        default_dir = get_default_db_dir()
        if resolved_dir == default_dir:
            raise UnsafeTestDatabaseError(
                f"[SAFETY GUARD] Test mode is active, but the database directory resolves to "
                f"the development database '{resolved_dir}'. Test execution aborted to prevent contamination."
            )
        active_mode = os.getenv("DB_MODE", "json").lower()
        if active_mode in ("postgres", "dual_write"):
            active_dsn = dsn or resolve_dsn("")
            if is_production_database_url(active_dsn):
                raise UnsafeTestDatabaseError(
                    f"[SAFETY GUARD] Test mode cannot connect to production PostgreSQL database DSN: '{active_dsn}'."
                )

DB_MODE = os.getenv("DB_MODE", "json") # "json", "postgres", "dual_write"
def resolve_dsn(default: str = "postgresql://user:password@localhost/tridentwear") -> str:
    """DATABASE_URL (what Docker/Render/Railway set) wins over PG_DSN.

    Previously only PG_DSN was read, so the staging container (which sets
    DATABASE_URL) silently fell back to the placeholder DSN and could not boot.
    Also normalises URL schemes to the installed psycopg2 driver:
      postgres://            -> postgresql://   (Heroku/Render style; SQLAlchemy 2 rejects it)
      postgresql+psycopg://  -> postgresql://   (psycopg3 driver is not installed)
    """
    dsn = (os.getenv("DATABASE_URL") or os.getenv("PG_DSN") or default).strip()
    for prefix in ("postgres://", "postgresql+psycopg://"):
        if dsn.startswith(prefix):
            dsn = "postgresql://" + dsn[len(prefix):]
    return dsn


PG_DSN = resolve_dsn()

def get_db(db_dir: Optional[Union[str, Path]] = None) -> DatabaseInterface:
    mode = os.getenv("DB_MODE", "json").strip().lower()
    dsn = resolve_dsn()

    if db_dir is not None and is_test_mode():
        validate_db_safety(db_dir=Path(db_dir).resolve(), dsn=dsn)

    json_adapter = JsonDatabaseAdapter(db_dir=db_dir)

    if mode == "json":
        return json_adapter
    elif mode == "postgres":
        if is_test_mode():
            validate_db_safety(dsn=dsn)
        return PostgresDatabaseAdapter(dsn)
    elif mode == "dual_write":
        if is_test_mode():
            validate_db_safety(dsn=dsn)
        pg_adapter = PostgresDatabaseAdapter(dsn)
        return DualWriteDatabaseAdapter(old_db=json_adapter, new_db=pg_adapter)
    else:
        return json_adapter

db = get_db()
