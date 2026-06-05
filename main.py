import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from database import (
    init_db, create_job, get_job,
    get_all_running, set_status, touch_job, remove_job,
)
from scraper import check_appointments, build_url

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
)
logger = logging.getLogger(__name__)

POLL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "10"))
scheduler = AsyncIOScheduler(timezone="Europe/Berlin")

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


# ──────────────────────────────────────────────
# Scheduler helpers
# ──────────────────────────────────────────────

def _remove_sched(job_id: str) -> None:
    try:
        scheduler.remove_job(job_id)
    except JobLookupError:
        pass


def _add_sched(job_id: str) -> None:
    scheduler.add_job(
        _poll,
        "interval",
        minutes=POLL_MINUTES,
        id=job_id,
        args=[job_id],
        next_run_time=datetime.now(timezone.utc),   # run immediately
        replace_existing=True,
    )


async def _poll(job_id: str) -> None:
    job = await get_job(job_id)
    if not job or job["status"] != "running":
        _remove_sched(job_id)
        return

    result = await check_appointments(job["vermittlungscode"], job["plz"])

    if result["status"] == "found":
        msg = f"{result['count']} Termine gefunden"
        await set_status(job_id, "found", result=msg)
        _remove_sched(job_id)
        logger.info("Job %s → FOUND %d appointments", job_id, result["count"])

    elif result["status"] == "error":
        await set_status(job_id, "error", error=result["message"])
        logger.warning("Job %s → error: %s", job_id, result["message"])

    else:
        await touch_job(job_id)
        logger.info("Job %s → 0 appointments, continuing", job_id)


# ──────────────────────────────────────────────
# Lifespan
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    scheduler.start()
    for job in await get_all_running():
        _add_sched(job["id"])
        logger.info("Restored job %s", job["id"])
    yield
    scheduler.shutdown(wait=False)


# ──────────────────────────────────────────────
# App
# ──────────────────────────────────────────────

app = FastAPI(title="Termin-Wächter", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Request model
# ──────────────────────────────────────────────

class StartRequest(BaseModel):
    email:               str
    vermittlungscode:    str
    plz:                 str
    emailjs_service_id:  str
    emailjs_template_id: str
    emailjs_public_key:  str

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
        if not re.match(r"^[A-Z0-9]{4}[A-Z0-9]{4}[A-Z0-9]{4}$", v):
            raise ValueError("Format: XXXX-XXXX-XXXX")
        return f"{v[:4]}-{v[4:8]}-{v[8:]}"

    @field_validator("plz")
    @classmethod
    def v_plz(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^\d{5}$", v):
            raise ValueError("PLZ muss genau 5 Ziffern enthalten")
        return v

    @field_validator("emailjs_service_id", "emailjs_template_id", "emailjs_public_key")
    @classmethod
    def v_ejs(cls, v: str) -> str:
        v = v.strip()[:64]
        if not re.match(r"^[A-Za-z0-9_\-\.]+$", v):
            raise ValueError("Ungültiger EmailJS-Wert")
        return v


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.post("/api/monitor/start")
async def start(req: StartRequest):
    job_id = await create_job(
        req.email, req.vermittlungscode, req.plz,
        req.emailjs_service_id, req.emailjs_template_id, req.emailjs_public_key,
    )
    _add_sched(job_id)
    return {
        "job_id":      job_id,
        "booking_url": build_url(req.vermittlungscode, req.plz),
    }


@app.get("/api/monitor/status/{job_id}")
async def status(job_id: str):
    if not UUID_RE.match(job_id):
        raise HTTPException(400, "Ungültige Job-ID")
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    return {
        "status":        job["status"],
        "last_checked":  job["last_checked"],
        "result":        job["result"],
        "error_message": job["error_message"],
        "booking_url":   build_url(job["vermittlungscode"], job["plz"]),
    }


@app.delete("/api/monitor/{job_id}")
async def stop(job_id: str):
    if not UUID_RE.match(job_id):
        raise HTTPException(400, "Ungültige Job-ID")
    job = await get_job(job_id)
    if not job:
        raise HTTPException(404, "Job nicht gefunden")
    _remove_sched(job_id)
    await remove_job(job_id)
    return {"message": "Überwachung gestoppt"}


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


app.mount("/", StaticFiles(directory="static", html=True), name="static")
