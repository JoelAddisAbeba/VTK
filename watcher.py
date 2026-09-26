"""Vatikan-Ticket-Watcher v3: prüft das Einzel-Eintrittsticket (2 Pers., Singles)
für 30.09.–03.10.2026 und schickt eine Push-Nachricht via ntfy."""
import datetime
import os
import re
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright

TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
TEST = os.getenv("TEST") == "1"
ROME = ZoneInfo("Europe/Rome")
DAYS = [datetime.date(2026, 9, 30), datetime.date(2026, 10, 1),
        datetime.date(2026, 10, 2), datetime.date(2026, 10, 3)]
VISITORS = 2
OUT = "debug"

TITLE = re.compile(r"^\s*(Vatican Museums\s*-\s*Admission Ticket|Musei Vaticani\s*-\s*Biglietti d.ingresso)\s*$", re.I)
# Status-Button der Karte: nur "PRENOTA"/"BOOK" zählt als frei
STATUS = re.compile(r"\b(prenota|book|non disponibil\w*|not available|non prenotabil\w*|unavailable)\b", re.I)
AVAILABLE = re.compile(r"\b(prenota|book)\b", re.I)
MONTHS_IT = {9: "settembre", 10: "ottobre"}
MONTHS_EN = {9: "September", 10: "October"}


def day_url(day):
    """URL-Schema der Seite: /home/visit/<Besucher>/<Mitternacht Rom in ms>/1/1"""
    ts = int(datetime.datetime(day.year, day.month, day.day, tzinfo=ROME).timestamp() * 1000)
    return f"https://tickets.museivaticani.va/home/visit/{VISITORS}/{ts}/1/1"


def notify(msg, title="Vatikan: Tickets frei!", priority="urgent", click="https://tickets.museivaticani.va"):
    if not TOPIC:
        print("FEHLER: NTFY_TOPIC ist leer – Secret wird nicht gefunden!")
        return
    r = requests.post(
        f"https://ntfy.sh/{TOPIC}",
        data=msg.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Click": click, "Tags": "ticket"},
        timeout=15,
    )
    print(f"ntfy: Status {r.status_code}")


def card_status(page):
    """Sucht den kleinsten Container um den Titel, der einen Status-Button enthält."""
    heading = page.get_by_text(TITLE).first
    heading.wait_for(timeout=25000)
    for level in range(1, 12):
        text = heading.locator(f"xpath=ancestor::*[{level}]").inner_text()
        m = STATUS.search(text)
        if m:
            return m.group(0)
    raise RuntimeError("Status-Button der Karte nicht gefunden")


def main():
    today = datetime.datetime.now(ROME).date()
    days = [d for d in DAYS if d >= today]
    if not days:
        print("Zeitraum vorbei – nichts zu tun.")
        return
    if TEST:
        notify("Testnachricht: Der Watcher läuft.", title="Vatikan-Watcher Test", priority="default")

    os.makedirs(OUT, exist_ok=True)
    free = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            timezone_id="Europe/Rome",
            viewport={"width": 1400, "height": 1000},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()

        for day in days:
            name = day.strftime("%d.%m.")
            url = day_url(day)
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(2000)
                body = page.inner_text("body")
                if "captcha" in body.lower():
                    print("CAPTCHA – Watcher wird geblockt.")
                    page.screenshot(path=f"{OUT}/blocked.png", full_page=True)
                    break
                # Kontrolle: zeigt die Seite wirklich das richtige Datum?
                shown = re.search(rf"\b0?{day.day} ({MONTHS_IT[day.month]}|{MONTHS_EN[day.month]})", body, re.I)
                if not shown:
                    print(f"{name}: Seite zeigt ein anderes Datum – übersprungen")
                    page.screenshot(path=f"{OUT}/wrongdate_{name}.png", full_page=True)
                    continue
                status = card_status(page)
                available = bool(AVAILABLE.fullmatch(status))
                print(f"{name}: {'FREI' if available else 'ausgebucht'} (Button: {status})")
                page.screenshot(path=f"{OUT}/{name}.png")
                if available:
                    free.append((name, url))
            except Exception as e:
                print(f"{name}: Fehler – {str(e).splitlines()[0]}")
                page.screenshot(path=f"{OUT}/error_{name}.png", full_page=True)

        browser.close()

    if free:
        msg = "Eintrittsticket (2 Pers.) verfügbar: " + ", ".join(n for n, _ in free)
        if any(n == "30.09." for n, _ in free):
            msg += "\n30.09.: Uhrzeit prüfen (nur nachmittags/abends)."
        notify(msg + "\nJetzt buchen!", click=free[0][1])


if __name__ == "__main__":
    main()
