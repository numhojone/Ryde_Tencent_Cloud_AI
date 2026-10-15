"""Browser smoke test for the three-pane demo (needs Playwright and a running server).

    LLM_MODE=deterministic python -m app.main          # in one terminal
    python scripts/smoke_three_pane.py [http://localhost:8000/]

Types a DISP-001-style route story in the rider pane and checks that all three panes fill:
the rider sees the hand-off message, the agent room shows the ruling, the support console shows the
case summary. Exits non-zero on failure or on any browser console error.
"""
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/"
STORY = ("The driver took a much longer route from Orchard Central to Changi Airport T3. The fare was $35 when "
         "I usually pay $28, and he never told me about any change.")

errors: list[str] = []
with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(BASE)
    page.select_option("#modeSelect", "deterministic")
    page.fill("#riderInput", STORY)
    page.click("#riderSend")
    page.wait_for_selector(".rm.handoff", timeout=30000)
    page.wait_for_selector("#chat .ruling", timeout=30000)
    page.wait_for_selector("#summary .sm-card", timeout=30000)
    checks = {
        "rider": page.locator("#riderChat .rm").count() >= 3,
        "room": page.locator("#chat .msg").count() >= 5,
        "human": "Partially upheld" in page.inner_text("#summary"),
    }
    browser.close()

print(checks, "console errors:", errors or "none")
sys.exit(0 if all(checks.values()) and not errors else 1)
