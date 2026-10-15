"""Browser smoke test for the three-pane demo (needs Playwright and a running server).

    LLM_MODE=deterministic python -m app.main          # in one terminal
    python scripts/smoke_three_pane.py [http://localhost:8000/]

Signs in as the demo rider Sarah Tan (R-4521), types a DISP-001-style route story, confirms the trip it
finds, and checks the rider sees the hand-off and the agent room shows the ruling. Then signs in as the
support agent in a separate browser session and checks the case is in the queue with its summary.
Exits non-zero on failure or on any browser console error.
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
STORY = "The driver took a long detour on the way to Changi Airport T3 and never told me."

errors: list[str] = []


def sign_in(browser, rider_id=None):
    page = browser.new_context(viewport={"width": 1440, "height": 900}).new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    page.wait_for_selector("#accountSelect option", state="attached")
    if rider_id:
        page.select_option("#accountSelect", rider_id)
    else:
        page.click("label.lg-opt:has(input[value=support])")
    page.click("#signInBtn")
    page.wait_for_selector("#whoami:not(:empty)")
    return page


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    rider = sign_in(browser, "R-4521")
    rider.select_option("#modeSelect", "deterministic")
    rider.fill("#riderInput", STORY)
    rider.click("#riderSend")
    rider.wait_for_selector(".tc-actions .btn.primary", timeout=15000)       # "Is this the one?"
    room_idle = rider.locator("#chat .msg").count() == 0                     # nothing runs before the trip is confirmed
    rider.click(".tc-actions .btn.primary")
    rider.wait_for_selector(".rm.handoff", state="attached", timeout=30000)
    rider.wait_for_selector("#chat .ruling", timeout=30000)
    support = sign_in(browser)
    support.wait_for_selector(".q-item", timeout=15000)
    support.locator(".q-item").last.click()
    support.wait_for_selector("#summary .sm-card", timeout=15000)
    checks = {
        "room idle before confirm": room_idle,
        "rider": rider.locator("#riderChat .rm").count() >= 4,
        "room": rider.locator("#chat .msg").count() >= 5,
        "support": "Partially upheld" in support.inner_text("#summary"),
    }
    browser.close()

print(checks, "console errors:", errors or "none")
sys.exit(0 if all(checks.values()) and not errors else 1)
