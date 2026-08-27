import os
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = "/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/docs/assets/screenshots"
BASE_URL = "http://localhost:4200"

def capture_chat():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
        page = context.new_page()

        page.goto(f"{BASE_URL}/projects")
        page.wait_for_timeout(1000)
        page.locator(".project-card").first.click()
        page.wait_for_url("**/projects/*/*", timeout=10000)
        page.locator("a.tab-link:has-text('Chat')").click()
        page.wait_for_url("**/projects/*/chat", timeout=5000)

        # Send a message to show conversation bubble & tools
        page.locator("#chatInput").fill("Synthesize literature consensus on Graph Neural Networks for cascade detection.")
        page.locator("#btnSendMessage").click()
        page.wait_for_timeout(2000)

        # Expand tool traces
        toggle_btn = page.locator(".tool-trace-toggle").first
        if toggle_btn.is_visible():
            toggle_btn.click()
            page.wait_for_timeout(500)

        page.screenshot(path=f"{SCREENSHOTS_DIR}/06_workspace_chat_tab.png", full_page=False)
        print("Captured 06_workspace_chat_tab.png successfully!")
        browser.close()

if __name__ == "__main__":
    capture_chat()
