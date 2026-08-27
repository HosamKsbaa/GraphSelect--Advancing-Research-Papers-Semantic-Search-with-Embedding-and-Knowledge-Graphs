import os
import time
from playwright.sync_api import sync_playwright

SCREENSHOTS_DIR = "/home/mr-h/Documents/Fam/me/masters/new/MasterProject2/docs/assets/screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

BASE_URL = "http://localhost:4200"

def capture_guide_screenshots():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1.5)
        page = context.new_page()

        # 1. Projects List Page
        print("Capturing Projects List...")
        page.goto(f"{BASE_URL}/projects")
        page.wait_for_timeout(1500)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/01_projects_list.png", full_page=False)

        # 2. Create Project Modal
        print("Capturing Create Project Modal...")
        new_proj_btn = page.locator("button:has-text('New Project'), button:has-text('Create Your First Project')").first
        if new_proj_btn.is_visible():
            new_proj_btn.click()
            page.wait_for_timeout(600)
            page.locator("#projectName").fill("Misinformation Detection with Graph Neural Networks")
            page.locator("#projectTopic").fill("Network Science & Disinformation")
            page.locator("#projectDesc").fill("Investigating diffusion dynamics and Graph-Centric Dual-Loop verification across citation networks.")
            page.wait_for_timeout(600)
            page.screenshot(path=f"{SCREENSHOTS_DIR}/02_create_project_modal.png", full_page=False)
            
            # Submit to create project and navigate to workspace
            page.locator("button[type='submit']:has-text('Create Project')").click()
            page.wait_for_url("**/projects/*/research", timeout=10000)
            page.wait_for_timeout(1000)
        
        # 3. Workspace - Research Tab
        print("Capturing Workspace Research Tab...")
        page.locator("#inputQuestion").fill("How do Graph Neural Networks detect misinformation cascades?")
        page.locator("#btnAddQuestion").click()
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/03_workspace_research_tab.png", full_page=False)

        # 4. Workspace - Analysis Tab
        print("Capturing Workspace Analysis Tab...")
        page.locator("a:has-text('Analysis'), button:has-text('Analysis')").click()
        page.wait_for_url("**/projects/*/analysis", timeout=5000)
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/04_workspace_analysis_tab.png", full_page=False)

        # 5. Workspace - Planning Tab
        print("Capturing Workspace Planning Tab...")
        page.locator("a:has-text('Planning'), button:has-text('Planning')").click()
        page.wait_for_url("**/projects/*/planning", timeout=5000)
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/05_workspace_planning_tab.png", full_page=False)

        # 6. Workspace - Writing Tab
        print("Capturing Workspace Writing Tab...")
        page.locator("a:has-text('Writing'), button:has-text('Writing')").click()
        page.wait_for_url("**/projects/*/writing", timeout=5000)
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/06_workspace_writing_tab.png", full_page=False)

        # 7. Workspace - Export Tab
        print("Capturing Workspace Export Tab...")
        page.locator("a:has-text('Export'), button:has-text('Export')").click()
        page.wait_for_url("**/projects/*/export", timeout=5000)
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/07_workspace_export_tab.png", full_page=False)

        # 8. Literature Search Wizard - Step 1
        print("Capturing Literature Search Wizard Step 1...")
        page.goto(f"{BASE_URL}/search")
        page.wait_for_timeout(1000)
        seed_input = page.locator("input[placeholder*='Enter paper title']")
        if seed_input.is_visible():
            seed_input.fill("Attention Is All You Need")
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/08_search_wizard_step1.png", full_page=False)

        # 9. System Status Page
        print("Capturing System Status Page...")
        page.goto(f"{BASE_URL}/system-status")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/09_system_status_page.png", full_page=False)

        # 10. Logs Page
        print("Capturing Logs Page...")
        page.goto(f"{BASE_URL}/logs")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/10_logs_page.png", full_page=False)

        # 11. Debug Page
        print("Capturing Debug Page...")
        page.goto(f"{BASE_URL}/debug")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/11_debug_page.png", full_page=False)

        # 12. Settings Page
        print("Capturing Settings Page...")
        page.goto(f"{BASE_URL}/settings")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{SCREENSHOTS_DIR}/12_settings_page.png", full_page=False)

        browser.close()
        print("All screenshots successfully captured!")

if __name__ == "__main__":
    capture_guide_screenshots()
