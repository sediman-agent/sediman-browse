"""
Quick dry-run test: EVIL v2 — Can we navigate the 7-layer maze programmatically?
Layer-aware navigation with dynamic data table (data only exists at layer 6).
"""

import asyncio
import sys
from pathlib import Path

async def test_navigate():
    url = "http://localhost:9999/yahoo_finance_AAPL.html"
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright not installed. Run: uv pip install playwright")
        return False
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))
            
            print(f"Navigating to {url}...")
            await page.goto(url)
            await asyncio.sleep(1)
            
            async def in_layer(layer_id, selector):
                layer = await page.query_selector(f"#layer{layer_id}")
                if not layer:
                    return []
                return await layer.query_selector_all(selector)
            
            # Layer 0: Click hidden nav (opacity:0.005, onclick="showLayer(1)")
            print("Layer 0: Clicking hidden nav button...")
            buttons = await in_layer(0, "button")
            for btn in buttons:
                style = await btn.evaluate("el => el.getAttribute('style') || ''")
                onclick = await btn.evaluate("el => el.getAttribute('onclick') || ''")
                if ("opacity:0.005" in style) and "showLayer(1)" in onclick:
                    await btn.click()
                    print("✅ Clicked hidden nav")
                    break
            else:
                # Fallback: click "Data" nav button
                for btn in buttons:
                    title = await btn.evaluate("el => el.getAttribute('title') || ''")
                    onclick = await btn.evaluate("el => el.getAttribute('onclick') || ''")
                    if "Data Access" in title and "showLayer(1)" in onclick:
                        await btn.click()
                        print("✅ Clicked Data nav")
                        break
                else:
                    print("❌ Hidden nav not found")
                    await browser.close()
                    return False
            
            await asyncio.sleep(1)

            # Layer 1: Accept Terms (click "I Agree — Continue")
            print("Layer 1: Accepting terms...")
            btns = await in_layer(1, "button")
            for btn in btns:
                text = await btn.inner_text()
                if text and "agree" in text.lower() and "continue" in text.lower():
                    await btn.click()
                    print("✅ Accepted terms")
                    break
            
            await asyncio.sleep(1)

            # Layer 2: Check consent + type variant name + click Continue
            print("Layer 2: Checking consent and confirming...")
            
            # Click the consent div (which triggers saveConsentAndContinue handler)
            consent_divs = await in_layer(2, "div")
            for div in consent_divs:
                text = await div.evaluate("el => el.innerText || ''")
                if "data processing" in text.lower() and "consent" in text.lower():
                    await div.click()
                    print("✅ Checked consent (via div onclick)")
                    break
            
            # Type variant name to confirm and trigger input event
            confirm_input = await page.query_selector("#confirm-input")
            if confirm_input:
                await confirm_input.fill("AAPL")
                # Trigger input event explicitly
                await confirm_input.evaluate("el => el.dispatchEvent(new Event('input', {bubbles: true}))")
                await asyncio.sleep(0.3)
                print("✅ Typed confirmation")
            
            # Click Cancel & Continue (should be enabled now)
            await asyncio.sleep(0.5)
            cont_btn = await page.query_selector("#cancel-continue-btn")
            if cont_btn:
                # Force enable and click
                await cont_btn.evaluate("el => el.disabled = false")
                await asyncio.sleep(0.2)
                await cont_btn.click()
                print("✅ Clicked Continue")
            
            await asyncio.sleep(1)

            # Layer 3: Click ghost button (empty text, onclick wired via JS)
            print("Layer 3: Clicking ghost button...")
            ghost_btns = await in_layer(3, "button")
            ghost_found = False
            for btn in ghost_btns:
                text = await btn.inner_text()
                onclick = await btn.evaluate("el => el.getAttribute('onclick') || ''")
                if (not text or text.strip() == "") and onclick == "":
                    btn_id = await btn.evaluate("el => el.id || ''")
                    if "ghost-" in btn_id:
                        # Force click via JS (opacity:0.005 prevents normal click)
                        await btn.evaluate("el => el.click()")
                        ghost_found = True
                        print("✅ Clicked ghost button")
                        break
            if not ghost_found:
                print("❌ Ghost button not found")
                await browser.close()
                return False
            
            await asyncio.sleep(1)

            # Layer 4: Security check — click hidden submit via JS
            print("Layer 4: Bypassing security...")
            btns = await in_layer(4, "button")
            for btn in btns:
                btn_id = await btn.evaluate("el => el.id || ''")
                style = await btn.evaluate("el => el.getAttribute('style') || ''")
                if "security-submit-btn" in btn_id or ("opacity:0.005" in style):
                    await btn.evaluate("el => el.click()")
                    print("✅ Clicked hidden submit")
                    break
            
            await asyncio.sleep(1)

            # Layer 5: Expand "Summary for AAPL" accordion
            print("Layer 5: Expanding accordion...")
            headers = await in_layer(5, "div")
            for h in headers:
                text = await h.inner_text()
                if "Summary for" in text and "AAPL" in text:
                    await h.click()
                    print(f"✅ Expanded: {text[:50]}")
                    break
            
            await asyncio.sleep(0.5)

            # Click "View AAPL Data →" button (may be obscured by accordion layout)
            print("Clicking data access button...")
            btns = await in_layer(5, "button")
            for btn in btns:
                text = await btn.inner_text()
                if "View" in text and "Data" in text and "→" in text:
                    await btn.evaluate("el => el.click()")
                    print("✅ Clicked data access")
                    break
            
            await asyncio.sleep(2)

            # Layer 6: Wait for async data fetch (buildDataTable uses fetch API)
            print("Layer 6: Waiting for data fetch...")
            for i in range(15):  # Wait up to 15 seconds
                ready = await page.evaluate("() => window.__DATA_READY")
                if ready:
                    print(f"  DATA_READY after {i+1}s")
                    break
                await asyncio.sleep(1)
            
            table = await in_layer(6, "table")
            if table:
                print("✅ Data table found!")
                rows = await table[0].query_selector_all("tr")
                print(f"   Table has {len(rows)} rows")
                for row in rows:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 2:
                        label = await cells[0].inner_text()
                        value = await cells[1].inner_text()
                        if label and "n/a" not in value.lower():
                            print(f"   📊 {label}: {value}")
            else:
                print("❌ No data table — it may not have been built yet (dynamic)")
                # Check if DATA_READY flag is set
                ready = await page.evaluate("() => window.__DATA_READY")
                print(f"   DATA_READY: {ready}")
                await browser.close()
                return False
            
            screenshot_path = Path("/tmp/benchmark_dryrun_v2.png")
            await page.screenshot(path=str(screenshot_path))
            print(f"✅ Screenshot saved to {screenshot_path}")
            
            await browser.close()
            return True
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_navigate())
    sys.exit(0 if success else 1)
