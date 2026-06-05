import os
import logging
import resend

logger = logging.getLogger(__name__)

resend.api_key = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "Termin-Wächter <noreply@yourdomain.com>")


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

    try:
        resend.Emails.send({
            "from":    FROM_EMAIL,
            "to":      [to_email],
            "subject": "✓ Freier Psychiater-Termin gefunden! / Free appointment found",
            "html":    html,
        })
        logger.info("Email sent to %s", to_email)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to_email, exc)
