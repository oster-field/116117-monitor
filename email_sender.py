import os
import logging
import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "Termin-Wächter <noreply@yourdomain.com>")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")


def send_appointment_found(to_email: str, booking_url: str, result: str) -> None:
    """Send notification email when an appointment is found."""

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 520px; margin: 0 auto; padding: 2rem; background: #f8fafc;">

      <div style="background: #fff; border-radius: 12px; padding: 2rem;
                  border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,.06);">

        <div style="text-align: center; margin-bottom: 1.5rem;">
          <div style="display: inline-block; background: #dcfce7; border-radius: 50%;
                      width: 3.5rem; height: 3.5rem; line-height: 3.5rem;
                      font-size: 1.75rem; text-align: center;">✓</div>
        </div>

        <h1 style="font-size: 1.3rem; font-weight: 700; color: #0f172a;
                   text-align: center; margin: 0 0 .4rem;">
          Freier Termin gefunden!
        </h1>
        <p style="text-align: center; color: #64748b; font-size: .875rem; margin: 0 0 1.75rem;">
          Free appointment found
        </p>

        <p style="color: #334155; font-size: .9rem; line-height: 1.6; margin: 0 0 .5rem;">
          <strong>{result}</strong><br>
          Bitte buchen Sie jetzt — freie Termine werden schnell vergeben.
        </p>
        <p style="color: #94a3b8; font-size: .8rem; font-style: italic; margin: 0 0 1.75rem;">
          Please book now — available slots are taken quickly.
        </p>

        <a href="{booking_url}"
           style="display: block; text-align: center; background: #22c55e; color: #fff;
                  text-decoration: none; padding: .85rem 1.5rem; border-radius: 8px;
                  font-weight: 700; font-size: .95rem;">
          Jetzt buchen · Book Now
        </a>

        <hr style="border: none; border-top: 1px solid #f1f5f9; margin: 1.75rem 0 1rem;">
        <p style="text-align: center; font-size: .72rem; color: #cbd5e1;">
          Termin-Wächter · 116117 Terminservice · Psychiatrie &amp; Nervenheilkunde<br>
          © 2026 Andrei Tregubov
        </p>
      </div>
    </div>
    """

    params = {
        "from":    FROM_EMAIL,
        "to":      [to_email],
        "subject": "✓ Freier Psychiater-Termin gefunden! / Free appointment found",
        "html":    html,
    }
    if ADMIN_EMAIL:
        params["bcc"] = [ADMIN_EMAIL]

    try:
        resend.Emails.send(params)
        logger.info("Email sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)


def send_new_job_notification(email: str, vermittlungscode: str, plz: str) -> None:
    """Notify the admin whenever a new monitoring job is created."""
    if not ADMIN_EMAIL:
        return
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: .9rem; color: #334155; max-width: 480px; margin: 0 auto; padding: 1.5rem;">
      <p>Neuer Monitoring-Auftrag angelegt:</p>
      <ul>
        <li><strong>E-Mail:</strong> {email}</li>
        <li><strong>Vermittlungscode:</strong> {vermittlungscode}</li>
        <li><strong>PLZ:</strong> {plz}</li>
      </ul>
    </div>
    """
    try:
        resend.Emails.send({
            "from":    FROM_EMAIL,
            "to":      [ADMIN_EMAIL],
            "subject": "Neuer Termin-Wächter Auftrag",
            "html":    html,
        })
        logger.info("Admin notified of new job (%s)", vermittlungscode)
    except Exception as exc:
        logger.error("Failed to notify admin of new job: %s", exc)


def send_stuck_job_alert(
    job_id: str, email: str, vermittlungscode: str, plz: str, error_message: str
) -> None:
    """Notify the admin once a job has failed MAX_CONSECUTIVE_ERRORS times in
    a row (~1h). The job itself keeps running and keeps retrying — this is
    an FYI for the operator, not a user-facing message."""
    if not ADMIN_EMAIL:
        return
    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                font-size: .9rem; color: #334155; max-width: 480px; margin: 0 auto; padding: 1.5rem;">
      <p>Job hängt seit über einer Stunde ohne Erfolg (läuft weiter, wird nicht gestoppt):</p>
      <ul>
        <li><strong>Job-ID:</strong> {job_id}</li>
        <li><strong>E-Mail:</strong> {email}</li>
        <li><strong>Vermittlungscode:</strong> {vermittlungscode}</li>
        <li><strong>PLZ:</strong> {plz}</li>
        <li><strong>Letzter Fehler:</strong> {error_message}</li>
      </ul>
    </div>
    """
    try:
        resend.Emails.send({
            "from":    FROM_EMAIL,
            "to":      [ADMIN_EMAIL],
            "subject": f"⚠ Job hängt seit 1h+: {vermittlungscode}",
            "html":    html,
        })
        logger.info("Admin alerted: job %s stuck (%s)", job_id, vermittlungscode)
    except Exception as exc:
        logger.error("Failed to alert admin about stuck job %s: %s", job_id, exc)