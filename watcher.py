"""Vatikan-Ticket-Watcher: prüft 'Vatican Museums - Admission Ticket' für 2 Personen
am 30.09.–03.10.2026 und schickt eine Push-Nachricht via ntfy."""
import datetime
import os
import re

import requests
from playwright.sync_api import sync_playwright

# URL der Ergebnisseite (Besucher 2, Vatican Museums, Singles) – als GitHub-Variable TICKET_URL setzen
URL = os.environ["TICKET_URL"]
TOPIC = os.environ["NTFY_TOPIC"]
TEST = os.getenv("TEST") == "1"

DATES = ["30 Sep", "1 Oct", "2 Oct", "3 Oct"]  # 4 Oct ist geschlossen
LAST_DAY = datetime.date(2026, 10, 3)
TITLE = re.compile(r"Vatican Museums\s*-\s*Admission Ticket", re.I)
NOT_AVAILABLE = ["not available", "currently unavailable", "sold out"]
OUT = "debug"


def notify(msg, title="Vatikan: Tickets frei!", priority="urgent"):
    requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=msg.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Click": URL, "Tags": "ticket"},
        timeout=15,
    )


def card_text(page):
    """Text der Karte 'Vatican Museums - Admission Ticket' (kleinster Container mit Status)."""
    heading = page.get_by_text(TITLE).first
    heading.wait_for(timeout=20000)
    for level in range(1, 10):
        text = heading.locator(f"xpath=ancestor::*[{level}]").inner_text()
        if "visitors" in text.lower():  # 'No. Of visitors 1 - 6' = Kartenende erreicht
            return text
    return heading.locator("xpath=ancestor::*[6]").inner_text()


def main():
    if datetime.date.today() > LAST_DAY:
        print("Zeitraum vorbei – nichts zu tun.")
        return
    if TEST:
        notify("Testnachricht: Der Watcher läuft.", title="Vatikan-Watcher Test", priority="default")

    os.makedirs(OUT, exist_ok=True)
    free = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
            ),
        )
        page.goto(URL, wait_until="networkidle", timeout=60000)

        if "captcha" in page.inner_text("body").lower():
            page.screenshot(path=f"{OUT}/blocked.png", full_page=True)
            print("CAPTCHA – Watcher wird geblockt.")
            if TEST:
                notify("Achtung: Seite blockt den Watcher.", title="Watcher blockiert", priority="high")
            browser.close()
            return

        for label in DATES:
            try:
                page.get_by_text(label, exact=True).first.click()
                page.wait_for_load_state("networkidle", timeout=30000)
                page.wait_for_timeout(1500)
                text = card_text(page).lower()
                page.screenshot(path=f"{OUT}/{label.replace(' ', '_')}.png")
                available = not any(k in text for k in NOT_AVAILABLE)
                print(f"{label}: {'FREI' if available else 'ausgebucht'}")
                if available:
                    free.append(label)
            except Exception as e:
                print(f"{label}: Fehler – {e}")
                page.screenshot(path=f"{OUT}/error_{label.replace(' ', '_')}.png", full_page=True)

        browser.close()

    if free:
        msg = "Admission Ticket (2 Pers.) verfügbar: " + ", ".join(free)
        if "30 Sep" in free:
            msg += "\n30.09.: Uhrzeit prüfen (nur nachmittags/abends sinnvoll)."
        notify(msg + "\nJetzt buchen!")


if __name__ == "__main__":
    main()
