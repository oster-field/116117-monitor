import os
import logging
import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "Termin-Wächter <noreply@yourdomain.com>")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "")


def send_appointment_found(to_email: str, booking_url: str, result: str) -> bool:
    """Send notification email when an appointment is found. True if sent."""

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
        return True
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
        return False


def send_monitoring_started(to_email: str, vermittlungscode: str, plz: str) -> None:
    """Confirm to a new user that monitoring has started. Sent once per
    genuinely new job — main.py skips this for a duplicate /start request."""

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 520px; margin: 0 auto; padding: 2rem; background: #f8fafc;">

      <div style="background: #fff; border-radius: 12px; padding: 2rem;
                  border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,.06);">

        <div style="text-align: center; margin-bottom: 1.5rem;">
          <div style="display: inline-block; background: #dbeafe; border-radius: 50%;
                      width: 3.5rem; height: 3.5rem; line-height: 3.5rem;
                      font-size: 1.75rem; text-align: center;">▶</div>
        </div>

        <h1 style="font-size: 1.3rem; font-weight: 700; color: #0f172a;
                   text-align: center; margin: 0 0 .4rem;">
          Überwachung gestartet
        </h1>
        <p style="text-align: center; color: #64748b; font-size: .875rem; margin: 0 0 1.75rem;">
          Monitoring started
        </p>

        <p style="color: #334155; font-size: .9rem; line-height: 1.6; margin: 0 0 .5rem;">
          Die Überwachung für Vermittlungscode <strong>{vermittlungscode}</strong> (PLZ {plz}) läuft jetzt.
          Sobald ein Termin verfügbar ist, erhalten Sie eine E-Mail — bitte buchen Sie dann schnell,
          freie Termine werden rasch vergeben. Verpassen Sie einen Termin, läuft die Überwachung
          einfach weiter, bis Sie einen Termin buchen oder Ihr Vermittlungscode abläuft.
          Bitte prüfen Sie bei Benachrichtigungen auch Ihren <strong>Spam-Ordner</strong>.
        </p>
        <p style="color: #94a3b8; font-size: .8rem; font-style: italic; margin: 0 0 1.75rem;">
          Monitoring for referral code {vermittlungscode} (postal code {plz}) is now active.
          You'll get an email as soon as a slot is available — please book quickly, as slots go fast.
          If you miss one, monitoring simply continues until you book an appointment or your referral
          code expires. Please also check your <strong>spam folder</strong> for notifications.
        </p>

        <hr style="border: none; border-top: 1px solid #f1f5f9; margin: 1.75rem 0 1rem;">
        <p style="text-align: center; font-size: .72rem; color: #cbd5e1;">
          Termin-Wächter · 116117 Terminservice · Psychiatrie &amp; Nervenheilkunde<br>
          © 2026 Andrei Tregubov
        </p>
      </div>
    </div>
    """

    # No admin BCC here: send_new_job_notification already tells the admin
    # about every new job in this same code path — a BCC would duplicate it.
    params = {
        "from":    FROM_EMAIL,
        "to":      [to_email],
        "subject": "Überwachung gestartet / Monitoring started",
        "html":    html,
    }

    try:
        resend.Emails.send(params)
        logger.info("Start-confirmation sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send start-confirmation to %s: %s", to_email, exc)


# Texts for the "monitoring ended" email. A booked code has no entry on
# purpose: nothing is sent in that case.
_COMPLETION_TEXTS = {
    "expired": {
        "subject": "Überwachung beendet: Vermittlungscode abgelaufen / Monitoring ended: code expired",
        "title_de": "Vermittlungscode abgelaufen",
        "title_en": "Referral code expired",
        "body_de": (
            "Laut 116117 ist der Vermittlungscode {vc} (PLZ {plz}) abgelaufen. "
            "Damit kann kein Termin mehr gebucht werden. Bitte wenden Sie sich an die "
            "ausstellende Praxis, um bei Bedarf einen neuen Code zu erhalten."
        ),
        "body_en": (
            "According to 116117, the referral code {vc} (postal code {plz}) has expired "
            "and can no longer be used to book an appointment. Please contact the practice "
            "that issued it to get a new code if needed."
        ),
    },
    "invalid_code": {
        "subject": "Überwachung beendet: Vermittlungscode nicht erkannt / Monitoring ended: code not recognised",
        "title_de": "Vermittlungscode nicht erkannt",
        "title_en": "Referral code not recognised",
        "body_de": (
            "116117 hat den Vermittlungscode {vc} (PLZ {plz}) nicht erkannt. "
            "Bitte prüfen Sie Code und PLZ und starten Sie die Überwachung bei Bedarf neu."
        ),
        "body_en": (
            "116117 did not recognise the referral code {vc} (postal code {plz}). "
            "Please check the code and postal code and start a new monitoring if needed."
        ),
    },
}


def send_job_completed(
    to_email: str, vermittlungscode: str, plz: str, reason: str
) -> bool:
    """Tell the user that monitoring has ended and why; the admin gets a BCC.

    reason: "expired" or "invalid_code". Returns True if the email was sent.
    """
    texts = _COMPLETION_TEXTS.get(reason)
    if texts is None:
        logger.error("No completion email text for reason %r", reason)
        return False

    body_de = texts["body_de"].format(vc=vermittlungscode, plz=plz)
    body_en = texts["body_en"].format(vc=vermittlungscode, plz=plz)

    html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 520px; margin: 0 auto; padding: 2rem; background: #f8fafc;">

      <div style="background: #fff; border-radius: 12px; padding: 2rem;
                  border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,.06);">

        <div style="text-align: center; margin-bottom: 1.5rem;">
          <div style="display: inline-block; background: #fef3c7; border-radius: 50%;
                      width: 3.5rem; height: 3.5rem; line-height: 3.5rem;
                      font-size: 1.75rem; text-align: center;">!</div>
        </div>

        <h1 style="font-size: 1.3rem; font-weight: 700; color: #0f172a;
                   text-align: center; margin: 0 0 .4rem;">
          Überwachung beendet: {texts["title_de"]}
        </h1>
        <p style="text-align: center; color: #64748b; font-size: .875rem; margin: 0 0 1.75rem;">
          Monitoring ended: {texts["title_en"]}
        </p>

        <p style="color: #334155; font-size: .9rem; line-height: 1.6; margin: 0 0 .5rem;">
          {body_de}
        </p>
        <p style="color: #94a3b8; font-size: .8rem; font-style: italic; margin: 0 0 1.75rem;">
          {body_en}
        </p>

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
        "subject": texts["subject"],
        "html":    html,
    }
    if ADMIN_EMAIL:
        params["bcc"] = [ADMIN_EMAIL]

    try:
        resend.Emails.send(params)
        logger.info("Completion email (%s) sent to %s", reason, to_email)
        return True
    except Exception as exc:
        logger.error("Failed to send completion email to %s: %s", to_email, exc)
        return False


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