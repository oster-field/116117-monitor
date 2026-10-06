import os
import re
import logging
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger(__name__)

LEISTUNGEN   = "W550,W147,W533,W149,W141"
RADIUS       = 150
HEADLESS     = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false"

# Injected before page load to mask headless signals
STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver',  {get: () => undefined});
Object.defineProperty(navigator, 'plugins',    {get: () => [1, 2, 3, 4, 5]});
Object.defineProperty(navigator, 'languages',  {get: () => ['de-DE', 'de', 'en-US', 'en']});
window.chrome = {
    runtime: {},
    loadTimes: function(){},
    csi: function(){},
    app: {}
};
"""


def build_url(vc: str, plz: str) -> str:
    return (
        f"https://www.116117-termine.de/termin/suchen/"
        f"{vc}/{plz}/{LEISTUNGEN}?suchradius={RADIUS}"
    )


# Longest extra wait for a recognisable page, on top of the fixed render wait.
EXTRA_WAIT_MS = 30_000

# What a page can say. Matched case-insensitively on normalised text.
_COUNT_RE = re.compile(r"(\d+)\s+TERMINE\s+IM\s+UMKREIS", re.IGNORECASE)
_BOOKED_RE = re.compile(
    r"Termin\s+bereits\s+gebucht|wurde\s+bereits\s+ein\s+Termin\s+gebucht",
    re.IGNORECASE,
)
_EXPIRED_RE = re.compile(
    r"Vermittlungscode\s+abgelaufen|kann\s+kein\s+Termin\s+mehr\s+gebucht\s+werden",
    re.IGNORECASE,
)
# For an unknown code the site shows its generic start page (search form).
_START_PAGE_MARKERS = ("suchgebiet (plz)", "vermittlungscode (optional)")

# The same patterns evaluated in the browser, so the extra wait ends as soon
# as one of the final states is on screen.
_FINAL_STATE_PATTERNS = [r.pattern for r in (_COUNT_RE, _BOOKED_RE, _EXPIRED_RE)]
_FINAL_STATE_JS = r"""(patterns) => {
  const t = (document.body ? document.body.innerText : '')
    .replace(/\u00ad/g, '').replace(/\s+/g, ' ');
  return patterns.some(p => new RegExp(p, 'i').test(t));
}"""


def _normalize(text: str) -> str:
    """Drop soft hyphens and collapse all whitespace."""
    return re.sub(r"\s+", " ", text.replace("\u00ad", "")).strip()


def _is_blocked(text: str) -> bool:
    return "Access Denied" in text or "Forbidden" in text


def _detect_final_state(flat: str, url: str) -> dict | None:
    """found / not_found / booked / expired, or None if none of them is shown."""
    m = _COUNT_RE.search(flat)
    if m:
        count = int(m.group(1))
        if count == 0:
            return {"status": "not_found", "count": 0}
        return {"status": "found", "count": count, "url": url}
    if _BOOKED_RE.search(flat):
        return {"status": "booked"}
    if _EXPIRED_RE.search(flat):
        return {"status": "expired"}
    return None


def classify_page_text(text: str, url: str) -> dict:
    """Map the visible page text to a result. Pure function, no I/O.

    Anything not recognised with certainty is an "error", which keeps the
    job running. "invalid_code" means the site showed its start page instead
    of a result page.
    """
    if _is_blocked(text):
        return {
            "status": "error",
            "message": "Zugriff verweigert (Access Denied). Server blockiert die Anfrage."
        }

    flat = _normalize(text)
    final = _detect_final_state(flat, url)
    if final is not None:
        return final

    low = flat.lower()
    if all(marker in low for marker in _START_PAGE_MARKERS):
        return {"status": "invalid_code"}

    return {
        "status": "error",
        "message": "Seitenstruktur nicht erkannt. Bitte Vermittlungscode und PLZ prüfen."
    }


async def check_appointments(vc: str, plz: str) -> dict:
    """
    Returns one of:
      {"status": "found",        "count": N, "url": "..."}
      {"status": "not_found",    "count": 0}
      {"status": "booked"}        code was already used for a booking
      {"status": "expired"}       code has expired
      {"status": "invalid_code"}  site shows its start page (unknown code)
      {"status": "error",        "message": "..."}
    """
    url = build_url(vc, plz)
    logger.info("Checking %s (headless=%s)", url, HEADLESS)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=HEADLESS,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                ],
            )
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    locale="de-DE",
                    timezone_id="Europe/Berlin",
                    viewport={"width": 1920, "height": 1080},
                )
                await context.add_init_script(STEALTH_JS)
                page = await context.new_page()

                await page.goto(url, timeout=60_000)
                await page.wait_for_timeout(6_000)  # let JS render

                text = await page.inner_text("body")

                # Some states render slowly (an already booked code does).
                # Only when nothing recognisable is on screen yet, keep waiting.
                if not _is_blocked(text) and _detect_final_state(_normalize(text), url) is None:
                    try:
                        await page.wait_for_function(
                            _FINAL_STATE_JS,
                            arg=_FINAL_STATE_PATTERNS,
                            timeout=EXTRA_WAIT_MS,
                        )
                    except PWTimeout:
                        pass  # classify whatever is on screen
                    text = await page.inner_text("body")
                final_url = page.url
            finally:
                await browser.close()

        # Parse result
        result = classify_page_text(text, url)
        status = result["status"]
        if status == "found":
            logger.info("%d appointment(s) found!", result["count"])
        elif status == "not_found":
            logger.info("0 appointments found")
        elif status == "booked":
            logger.info("Code already booked")
        elif status == "expired":
            logger.info("Code expired")
        elif status == "invalid_code":
            logger.warning("Start page instead of results (final URL: %s)", final_url)
        elif not _is_blocked(text):
            logger.warning("Cannot parse page. Snippet: %.300s", text)
        return result

    except PWTimeout:
        return {"status": "error", "message": "Zeitüberschreitung beim Laden der Seite (>60 s)."}
    except Exception as exc:
        logger.exception("Scraper error")
        return {"status": "error", "message": str(exc)}
