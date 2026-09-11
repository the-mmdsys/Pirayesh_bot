"""Export the editable SVG wordmark and placeholder for Bale's photo messages."""
import base64
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

assets = Path(__file__).resolve().parent.parent / 'panel/static/panel'
font = base64.b64encode((assets / 'vendor/Vazirmatn.woff2').read_bytes()).decode()
with sync_playwright() as playwright:
    channel = os.getenv('PANEL_BROWSER_CHANNEL')
    browser = playwright.chromium.launch(headless=True, **({'channel': channel} if channel else {}))
    page = browser.new_page(viewport={'width': 1100, 'height': 800}, device_scale_factor=1)
    for name in ('payizan-logo', 'barber-placeholder'):
        svg = (assets / f'{name}.svg').read_text(encoding='utf-8')
        page.set_content(f'<style>body{{margin:0}}@font-face{{font-family:Vazirmatn;src:url(data:font/woff2;base64,{font});font-weight:100 900}}</style>{svg}')
        page.evaluate("document.fonts.ready")
        page.locator('svg').screenshot(path=str(assets / f'{name}.png'))
    browser.close()
