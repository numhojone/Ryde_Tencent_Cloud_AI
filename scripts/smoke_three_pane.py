"""Browser smoke test for the three-pane demo (needs Playwright and a running server).

    LLM_MODE=deterministic python -m app.main          # in one terminal
    python scripts/smoke_three_pane.py [http://localhost:8000/]

Signs in as Priya Nair (R-9001), types the vague route story, checks the picker offers her three route rides, picks
the 23 Sep one (DISP-152, 5.0 km over, so a person decides), and checks all three panes fill: the rider is told a support agent
has the case, the agent room shows the ruling, the console shows the case summary. Then the console asks the
driver and the driver view shows the question under the case's own driver. Exits non-zero on failure or any
browser console error.
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
STORY = "My driver took a much longer route than usual and I paid more than I should have."

errors: list[str] = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector("#accountSelect option", state="attached")
    only_rider = page.locator("input[name=role]").count() == 0
    page.select_option("#accountSelect", "R-9001")
    page.click("#signInBtn")
    page.wait_for_selector("#whoami:not(:empty)")
    page.select_option("#modeSelect", "deterministic")
    page.fill("#riderInput", STORY)
    page.click("#riderSend")
    page.wait_for_selector(".tc-list .tc", timeout=15000)
    picker = page.locator(".tc-list .tc").count()
    room_idle = page.locator("#chat .msg").count() == 0              # nothing runs before the trip is confirmed
    page.locator(".tc-list .tc").filter(has_text="Clementi Mall").locator(".tc-btn").first.click()
    page.wait_for_selector(".rm.handoff", state="attached", timeout=30000)
    page.wait_for_selector("#chat .ruling", timeout=30000)
    page.wait_for_selector("#summary .sm-card", timeout=15000)
    page.fill("#askInput", "why did the drvier go thru Bukit Timah insted of the KPE?")
    page.click("#askBtn"); page.wait_for_selector("#askConfirm:not([hidden])"); page.click("#qcSend")
    page.wait_for_selector(".qa-item.asked_driver", timeout=15000)
    page.click("#tgDriver")
    page.wait_for_selector(".drv-case .drv-text", timeout=15000)
    checks = {
        "login offers riders only": only_rider,
        "picker with three rides": picker == 3,
        "room idle before confirm": room_idle,
        "rider": "Priya Nair (R-9001)" in page.inner_text("#whoami"),
        "room": page.locator("#chat .msg").count() >= 5,
        "console": "DISP-152" in page.inner_text("#summary"),
        "driver view": "Nur Aisyah (D-4410)" in page.inner_text("#driverChat"),
    }
    browser.close()

print(checks, "console errors:", errors or "none")
sys.exit(0 if all(checks.values()) and not errors else 1)
