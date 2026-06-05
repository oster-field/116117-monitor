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
    last_checked      TEXT
)
"""


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_TABLE)
        await db.commit()
    logger.info("Database ready at %s", DB_PATH)


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
