import os
import uuid
import logging
import aiosqlite
from datetime import datetime, timezone
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)
DB_PATH = os.getenv("DB_PATH", "monitoring.db")


def _fernet() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set.\n"
            "Generate one with:\n"
            "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode())


def encrypt_email(email: str) -> str:
    return _fernet().encrypt(email.encode()).decode()


def decrypt_email(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    id                TEXT PRIMARY KEY,
    email_enc         TEXT NOT NULL,
    vermittlungscode  TEXT NOT NULL,
    plz               TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'running',
    result            TEXT,
    error_message     TEXT,
    created_at        TEXT NOT NULL,
    last_checked      TEXT,
    completed_reason  TEXT,
    found_notified    INTEGER NOT NULL DEFAULT 0
)
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TABLE)
        await _migrate(db)
        await db.commit()
    logger.info("Database ready at %s", DB_PATH)


async def _migrate(db: aiosqlite.Connection) -> None:
    """Bring a database created by an older version up to date. Idempotent."""
    async with db.execute("PRAGMA table_info(jobs)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "completed_reason" not in columns:
        await db.execute("ALTER TABLE jobs ADD COLUMN completed_reason TEXT")
    if "found_notified" not in columns:
        await db.execute(
            "ALTER TABLE jobs ADD COLUMN found_notified INTEGER NOT NULL DEFAULT 0"
        )

    # Older versions stopped a job as soon as appointments were found
    # (status 'found'). That is no longer a final state, so resume those jobs.
    # found_notified=1 because the user already got the email for them.
    cur = await db.execute(
        "UPDATE jobs SET status=?, found_notified=1 WHERE status='found'",
        (STATUS_RUNNING,),
    )
    if cur.rowcount:
        logger.info("Resumed %d legacy 'found' job(s)", cur.rowcount)


async def create_job(email: str, vc: str, plz: str) -> str:
    job_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO jobs
               (id, email_enc, vermittlungscode, plz, status, created_at)
               VALUES (?,?,?,?,'running',?)""",
            (job_id, encrypt_email(email), vc, plz,
             datetime.now(timezone.utc).isoformat())
        )
        await db.commit()
    return job_id


async def get_job(job_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE id=?", (job_id,)
        ) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["email"] = decrypt_email(d["email_enc"])
    except Exception:
        d["email"] = ""
    return d


async def find_active_job(email: str, vc: str, plz: str) -> dict | None:
    """Oldest job that is not completed and has the same email, code and PLZ.

    Emails are stored with non-deterministic encryption, so SQL can only
    narrow down by code and PLZ; the decrypted email is compared in Python.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE vermittlungscode=? AND plz=? AND status!=? "
            "ORDER BY created_at",
            (vc, plz, STATUS_COMPLETED),
        ) as cur:
            rows = await cur.fetchall()
    wanted = email.strip().lower()
    for row in rows:
        d = dict(row)
        try:
            d["email"] = decrypt_email(d["email_enc"])
        except Exception:
            continue
        if d["email"].strip().lower() == wanted:
            return d
    return None


async def get_all_running() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM jobs WHERE status='running'"
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        try:
            d["email"] = decrypt_email(d["email_enc"])
        except Exception:
            d["email"] = ""
        result.append(d)
    return result


async def set_status(
    job_id: str, status: str,
    result: str | None = None,
    error: str | None = None
) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE jobs
               SET status=?, result=?, error_message=?, last_checked=?
               WHERE id=?""",
            (status, result, error,
             datetime.now(timezone.utc).isoformat(), job_id)
        )
        await db.commit()


async def mark_completed(job_id: str, reason: str, result: str) -> None:
    """Final state. reason: booked | expired | invalid_code."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE jobs
               SET status=?, completed_reason=?, result=?,
                   error_message=NULL, last_checked=?
               WHERE id=?""",
            (STATUS_COMPLETED, reason, result,
             datetime.now(timezone.utc).isoformat(), job_id),
        )
        await db.commit()


async def set_found_notified(job_id: str, notified: bool) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET found_notified=? WHERE id=?",
            (1 if notified else 0, job_id),
        )
        await db.commit()


async def touch_job(job_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE jobs SET last_checked=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), job_id)
        )
        await db.commit()


async def remove_job(job_id: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
        await db.commit()
