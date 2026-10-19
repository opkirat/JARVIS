from pathlib import Path
from playwright.sync_api import sync_playwright

profile = Path("secrets/crowdmark_browser").resolve()

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(profile),
        channel="chrome",
        headless=False,
    )

    page = context.pages[0] if context.pages else context.new_page()
    page.goto("https://app.crowdmark.com/sign-in")

    input("Sign in if needed, then press Enter to close...")
    context.close()