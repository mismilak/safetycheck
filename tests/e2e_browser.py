"""Browser smoke test (Playwright): login, every page, alarm dialog, PWA, mobile overflow, CSP, external requests.

Start the server first:  SC_DETECTOR=demo SC_ADMIN_PASSWORD=Admin1234 SC_PORT=8123 python run.py
Run:  python tests/e2e_browser.py [base_url] [screenshot_dir]      (env CHROMIUM_PATH to use a specific browser)
"""
import asyncio, json, os, sys
from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8123"
OUT = sys.argv[2] if len(sys.argv) > 2 else "e2e-shots"

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH"), args=["--no-sandbox"])
        errs, reqs = [], []
        # --- phase 1: CSP active, no eval-based helpers ---
        c0 = await b.new_context(viewport={"width": 1440, "height": 900}, locale="fa-IR")
        p0 = await c0.new_page(); csp = []
        p0.on("console", lambda m: csp.append(m.text) if m.type in ("error", "warning") else None)
        await p0.goto(BASE); await p0.wait_for_selector("#lf")
        await p0.fill("#u", "admin"); await p0.fill("#p", "Admin1234"); await p0.click("#go")
        await p0.wait_for_selector(".shell")
        for r in ["", "alarms", "stats", "reports", "cameras", "users", "settings", "profile"]:
            await p0.goto(f"{BASE}/#/{r}"); await p0.wait_for_timeout(1200)
        await p0.wait_for_selector("#page *")
        print("CSP-active console problems:", csp)
        await c0.close()
        # --- phase 2: measurements ---
        ctx = await b.new_context(viewport={"width": 1440, "height": 900}, locale="fa-IR", timezone_id="Asia/Tehran", bypass_csp=True)
        page = await ctx.new_page()
        page.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        page.on("request", lambda r: reqs.append(r.url))
        await page.goto(BASE)
        await page.wait_for_selector("#lf")
        await page.screenshot(path=f"{OUT}/01-login.png")
        # wrong login
        await page.fill("#u", "admin"); await page.fill("#p", "bad"); await page.click("#go")
        await page.wait_for_selector("#err:not(:empty)")
        print("login error text:", await page.inner_text("#err"))
        await page.fill("#p", "Admin1234"); await page.click("#go")
        await page.wait_for_selector(".shell")
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"{OUT}/02-live.png")
        print("title:", await page.title())
        print("font loaded:", await page.evaluate("document.fonts.check('16px Vazirmatn')"))
        print("font family body:", await page.evaluate("getComputedStyle(document.body).fontFamily"))
        # external requests?
        ext = [u for u in reqs if not u.startswith(BASE) and not u.startswith("data:") and not u.startswith("blob:")]
        print("external requests:", ext)
        for route, name in [("alarms", "03-alarms"), ("stats", "04-stats"), ("reports", "05-reports"), ("cameras", "06-cameras"), ("users", "07-users"), ("settings", "08-settings"), ("profile", "09-profile")]:
            await page.goto(f"{BASE}/#/{route}")
            await page.wait_for_timeout(1800)
            await page.screenshot(path=f"{OUT}/{name}.png", full_page=False)
        # open alarm modal
        await page.goto(f"{BASE}/#/alarms"); await page.wait_for_selector("tr[data-id]", timeout=15000)
        await page.click("tr[data-id]"); await page.wait_for_selector(".modal img.evidence"); await page.wait_for_timeout(800)
        await page.screenshot(path=f"{OUT}/10-alarm-modal.png")
        loaded = await page.evaluate("document.querySelector('.modal img.evidence').naturalWidth")
        print("evidence image width:", loaded)
        await page.keyboard.press("Escape")
        # PWA checks
        man = await page.evaluate("fetch('/manifest.webmanifest').then(r=>r.json()).then(j=>j.name)")
        sw = await page.evaluate("navigator.serviceWorker.getRegistration().then(r=>!!r)")
        await page.wait_for_timeout(1500)
        sw = await page.evaluate("navigator.serviceWorker.getRegistration().then(r=>!!r && !!(r.active||r.installing||r.waiting))")
        print("manifest:", man, "| sw registered:", sw)
        # mobile
        m = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, locale="fa-IR", is_mobile=True, has_touch=True, bypass_csp=True)
        mp = await m.new_page()
        mp.on("pageerror", lambda e: errs.append(f"mobile pageerror: {e}"))
        await mp.goto(BASE); await mp.wait_for_selector("#lf")
        await mp.screenshot(path=f"{OUT}/20-m-login.png")
        await mp.fill("#u", "admin"); await mp.fill("#p", "Admin1234"); await mp.click("#go")
        await mp.wait_for_selector(".bottom-nav"); await mp.wait_for_timeout(3500)
        await mp.screenshot(path=f"{OUT}/21-m-live.png")
        ov = await mp.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        print("mobile horizontal overflow px (live):", ov)
        for route, name in [("alarms", "22-m-alarms"), ("stats", "23-m-stats"), ("cameras", "24-m-cameras"), ("settings", "25-m-settings")]:
            await mp.goto(f"{BASE}/#/{route}"); await mp.wait_for_timeout(1800)
            await mp.screenshot(path=f"{OUT}/{name}.png")
            print(route, "overflow:", await mp.evaluate("document.documentElement.scrollWidth - window.innerWidth"))
        print("ERRORS:", json.dumps(errs, ensure_ascii=False, indent=1))
        await b.close()
asyncio.run(main())
