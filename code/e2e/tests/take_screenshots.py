import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

options = Options()
options.add_argument("--headless=new")
options.add_argument("--window-size=1920,1080")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
options.add_argument("--disable-gpu")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

base_url = "http://localhost:4200"
out_dir = "/home/mr-h/.gemini/antigravity/brain/da385ead-233a-41b7-a148-da96d10abb31/"

try:
    # 1. Projects List
    driver.get(f"{base_url}/projects")
    time.sleep(3)
    driver.save_screenshot(f"{out_dir}ui_projects.png")

    # 2. Search Page
    driver.get(f"{base_url}/search")
    time.sleep(3)
    driver.save_screenshot(f"{out_dir}ui_search.png")
    
    # 3. Logs Page
    driver.get(f"{base_url}/logs")
    time.sleep(3)
    driver.save_screenshot(f"{out_dir}ui_logs.png")
    
    # 4. Settings Page
    driver.get(f"{base_url}/settings")
    time.sleep(3)
    driver.save_screenshot(f"{out_dir}ui_settings.png")

    print("Screenshots taken successfully!")
finally:
    driver.quit()
