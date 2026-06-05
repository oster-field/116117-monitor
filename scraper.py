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


async def check_appointments(vc: str, plz: str) -> dict:
    """
    Returns one of:
      {"status": "found",     "count": N, "url": "..."}
      {"status": "not_found", "count": 0}
      {"status": "error",     "message": "..."}
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
            await page.wait_for_timeout(6_000)   # let JS render

            text = await page.inner_text("body")
            await browser.close()

        # — Parse result —
        if "Access Denied" in text or "Forbidden" in text:
            return {
                "status": "error",
                "message": "Zugriff verweigert (Access Denied). Server blockiert die Anfrage."
            }

        m = re.search(r"(\d+)\s+TERMINE\s+IM\s+UMKREIS", text, re.IGNORECASE)
        if not m:
            logger.warning("Cannot parse page. Snippet: %.300s", text)
            return {
                "status": "error",
                "message": "Seitenstruktur nicht erkannt. Bitte Vermittlungscode und PLZ prüfen."
            }

        count = int(m.group(1))
        if count == 0:
            logger.info("0 appointments found")
            return {"status": "not_found", "count": 0}

        logger.info("%d appointment(s) found!", count)
        return {"status": "found", "count": count, "url": url}

    except PWTimeout:
        return {"status": "error", "message": "Zeitüberschreitung beim Laden der Seite (>60 s)."}
    except Exception as exc:
        logger.exception("Scraper error")
        return {"status": "error", "message": str(exc)}
