import logging
import os
import re
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()  # must be before local imports — scraper.py reads HEADLESS at import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from database import (
    init_db, create_job, get_job, find_active_job,
    get_all_running, set_status, remove_job,
    mark_completed, set_found_notified, STATUS_RUNNING,
)
from scraper import check_appointments, build_url
from email_sender import (
    send_appointment_found, send_new_job_notification, send_stuck_job_alert,
    send_job_completed, send_monitoring_started,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

POLL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "10"))
scheduler = AsyncIOScheduler(timezone="Europe/Berlin")
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

# A single scrape failure (timeout, temporary block, browser hiccup) must
# NOT permanently kill a user's monitoring — only alert the admin after
# several in a row, but keep retrying forever. In-memory is fine: worst
# case after a restart is a few extra retries, never a false "gave up".
MAX_CONSECUTIVE_ERRORS = int(os.getenv("MAX_CONSECUTIVE_ERRORS", "6"))  # ~1h at 10-min interval
_consecutive_errors: dict[str, int] = {}

# Hard ceiling on a single check_appointments() call. Without this, a call
# that hangs (rather than raising) blocks this job's _poll() forever — and
# since APScheduler's default max_instances=1, every future scheduled tick
# for this same job id is silently skipped until the process is restarted.
# This guarantees _poll() always finishes.
SCRAPE_HARD_TIMEOUT = 180  # seconds

# The site's start page (shown for an unknown code) must be seen this many
# checks in a row before a job is ended as "invalid_code". Ending a user's
# monitoring by mistake is worse than waiting one more interval. 1 = end on
# the first sighting. In-memory like _consecutive_errors.
INVALID_CODE_CONFIRMATIONS = int(os.getenv("INVALID_CODE_CONFIRMATIONS", "2"))
_invalid_streak: dict[str, int] = {}

# Makes "look for a duplicate, then create" in /start one atomic step.
_start_lock = asyncio.Lock()

# Stored in jobs.result when a job reaches its final state.
COMPLETION_RESULTS = {
    "booked":       "Termin gebucht",
    "expired":      "Vermittlungscode abgelaufen",
    "invalid_code": "Vermittlungscode nicht erkannt",
}


# ── Scheduler helpers ────────────────────────────────────────────────────────

def _remove_sched(job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass


def _add_sched(job_id: str) -> None:
    scheduler.add_job(
        _poll, "interval",
        minutes=POLL_MINUTES,
        id=job_id,
        args=[job_id],
        next_run_time=datetime.now(timezone.utc),  # run immediately
        replace_existing=True,
    )


def _forget(job_id: str) -> None:
    """Drop the in-memory counters of a job that is no longer polled."""
    _consecutive_errors.pop(job_id, None)
    _invalid_streak.pop(job_id, None)


async def _complete(job: dict, reason: str, notify: bool) -> None:
    """Move a job to its final state and stop polling it.

    The DB is updated before any email goes out, so a failing email can never
    lead to a second completion. notify=True: one email to the user, BCC to
    the admin (see send_job_completed).
    """
    job_id = job["id"]
    await mark_completed(job_id, reason, COMPLETION_RESULTS[reason])
    _remove_sched(job_id)
    _forget(job_id)
    logger.info("Job %s → COMPLETED (%s)", job_id, reason)
    if notify:
        await asyncio.to_thread(
            send_job_completed,
            job["email"], job["vermittlungscode"], job["plz"], reason,
        )


async def _poll(job_id: str) -> None:
    job = await get_job(job_id)
    if not job or job["status"] != STATUS_RUNNING:
        _remove_sched(job_id)
        _forget(job_id)
        return

    try:
        result = await asyncio.wait_for(
            check_appointments(job["vermittlungscode"], job["plz"]),
            timeout=SCRAPE_HARD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        result = {
            "status": "error",
            "message": f"Scraper reagierte nicht innerhalb von {SCRAPE_HARD_TIMEOUT}s "
                       f"(hard timeout) — vermutlich hängender Browser-Prozess.",
        }
        logger.error("Job %s → hard timeout in check_appointments", job_id)

    kind = result["status"]
    if kind != "invalid_code":
        _invalid_streak.pop(job_id, None)

    # A job ends only in one of three cases: the code was used for a booking,
    # it expired, or the site does not know it. Everything else, errors
    # included, keeps it running.
    if kind == "booked":
        # Nothing left to watch and nothing to tell anyone.
        await _complete(job, "booked", notify=False)

    elif kind == "expired":
        await _complete(job, "expired", notify=True)

    elif kind == "invalid_code":
        _consecutive_errors.pop(job_id, None)
        seen = _invalid_streak.get(job_id, 0) + 1
        _invalid_streak[job_id] = seen
        if seen >= INVALID_CODE_CONFIRMATIONS:
            await _complete(job, "invalid_code", notify=True)
        else:
            logger.warning(
                "Job %s → start page instead of results (%d/%d), checking again",
                job_id, seen, INVALID_CODE_CONFIRMATIONS,
            )
            await set_status(
                job_id, STATUS_RUNNING, result=job["result"],
                error="Vermittlungscode wurde nicht erkannt, wird erneut geprüft.",
            )

    elif kind == "found":
        msg = f"{result['count']} Termine gefunden"
        _consecutive_errors.pop(job_id, None)
        # Found is not a final state: the job keeps running until the code is
        # booked or expires. The email goes out once per appearance of
        # appointments (found_notified is reset when the count drops to 0).
        await set_status(job_id, STATUS_RUNNING, result=msg, error=None)
        logger.info("Job %s → FOUND %d appointments, continuing", job_id, result["count"])
        if not job["found_notified"]:
            # Run sync Resend call in a thread, avoids blocking the async event loop
            sent = await asyncio.to_thread(
                send_appointment_found,
                job["email"], result["url"], msg,
            )
            # Not marked on failure, so the next check tries again.
            if sent:
                await set_found_notified(job_id, True)

    elif kind == "not_found":
        _consecutive_errors.pop(job_id, None)
        # set_status (not touch_job): this also clears a stale
        # error_message left over from an earlier failed attempt that has
        # since recovered; touch_job only ever touched last_checked.
        await set_status(job_id, STATUS_RUNNING, error=None)
        if job["found_notified"]:
            await set_found_notified(job_id, False)
        logger.info("Job %s → 0 appointments, continuing", job_id)

    else:
        # "error", or any status this code does not know: keep running.
        message = result.get("message") or f"Unbekanntes Scraper-Ergebnis: {kind!r}"
        fails = _consecutive_errors.get(job_id, 0) + 1
        _consecutive_errors[job_id] = fails
        logger.warning(
            "Job %s → error (%d/%d consecutive): %s",
            job_id, fails, MAX_CONSECUTIVE_ERRORS, message,
        )

        # Never give up on its own — a scrape failure (site hiccup, block,
        # timeout, hung browser) must not silently end a user's monitoring.
        # Keep status "running" and keep retrying forever; only alert the
        # admin once a streak has gone on long enough (~1h) to be worth a
        # human look. The previous result (appointments found) is kept.
        await set_status(job_id, STATUS_RUNNING, result=job["result"], error=message)

        if fails == MAX_CONSECUTIVE_ERRORS:
            logger.error("Job %s → stuck for %d consecutive errors", job_id, fails)
            await asyncio.to_thread(
                send_stuck_job_alert,
                job_id, job["email"], job["vermittlungscode"], job["plz"], message,
            )


# ── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.start()
    for job in await get_all_running():
        _add_sched(job["id"])
        logger.info("Restored job %s", job["id"])
    yield
    scheduler.shutdown(wait=False)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="Termin-Wächter", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request model ────────────────────────────────────────────────────────────

class StartRequest(BaseModel):
    email:            str
    vermittlungscode: str
    plz:              str

    @field_validator("email")
    @classmethod
    def v_email(cls, v: str) -> str:
        v = v.strip().lower()[:254]
        if not re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", v):
            raise ValueError("Ungültige E-Mail-Adresse")
        return v

    @field_validator("vermittlungscode")
    @classmethod
    def v_vc(cls, v: str) -> str:
        v = re.sub(r"[^A-Za-z0-9]", "", v.strip()).upper()
        if not re.match(r"^[A-Z0-9]{12}$", v):
            raise ValueError("Format: XXXX-XXXX-XXXX")
        return f"{v[:4]}-{v[4:8]}-{v[8:]}"

    @field_validator("plz")
    @classmethod
    def v_plz(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^\d{5}$", v):
            raise ValueError("PLZ muss genau 5 Ziffern enthalten")
        return v


# ── Routes ───────────────────────────────────────────────────────────────────

def _job_view(job: dict) -> dict:
    """Public shape of a job, shared by /start (duplicate) and /status."""
    running = job["status"] == STATUS_RUNNING
    return {
        "status":        job["status"],             # running | completed
        "found":         running and bool(job["result"]),  # appointments available now
        "reason":        job["completed_reason"],   # booked | expired | invalid_code | None
        "last_checked":  job["last_checked"],
        "result":        job["result"],
        "error_message": job["error_message"],
        "booking_url":   build_url(job["vermittlungscode"], job["plz"]),
    }


@app.post("/api/monitor/start")
async def start(req: StartRequest):
    async with _start_lock:
        existing = await find_active_job(
            req.email, req.vermittlungscode, req.plz,
        )
        if existing:
            logger.info("Job %s → duplicate start request, not creating a new job", existing["id"])
            return {
                "job_id":          existing["id"],
                "already_running": True,
                **_job_view(existing),
            }
        job_id = await create_job(req.email, req.vermittlungscode, req.plz)
        _add_sched(job_id)
    await asyncio.to_thread(
        send_new_job_notification, req.email, req.vermittlungscode, req.plz,
    )
    await asyncio.to_thread(
        send_monitoring_started, req.email, req.vermittlungscode, req.plz,
    )
    return {
        "job_id":          job_id,
        "already_running": False,
        "booking_url":     build_url(req.vermittlungscode, req.plz),
    }


@app.get("/api/monitor/status/{job_id}")
async def status(job_id: str):
    if not UUID_RE.match(job_id):
        raise HTTPException(400, "Ungültige Job-ID")
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    return _job_view(job)


@app.delete("/api/monitor/{job_id}")
async def stop(job_id: str):
    if not UUID_RE.match(job_id):
        raise HTTPException(400, "Ungültige Job-ID")
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    _remove_sched(job_id)
    _forget(job_id)
    await remove_job(job_id)
    return {"message": "Überwachung gestoppt"}


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ── Legal pages and favicon ──────────────────────────────────────────────────

@app.get("/impressum", include_in_schema=False)
async def impressum_page():
    return FileResponse("static/impressum.html")


@app.get("/datenschutz", include_in_schema=False)
async def datenschutz_page():
    return FileResponse("static/datenschutz.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Fallback for clients that ignore <link rel="icon">; serves img/favicon.png.
    if not os.path.isfile("img/favicon.png"):
        raise HTTPException(404)
    return FileResponse("img/favicon.png", media_type="image/png")


# check_dir=False: the app must still start if img/ has not been created yet.
app.mount("/img", StaticFiles(directory="img", check_dir=False), name="img")
app.mount("/", StaticFiles(directory="static", html=True), name="static")