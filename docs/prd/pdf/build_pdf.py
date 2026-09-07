import sys, asyncio
from playwright.async_api import async_playwright

SRC, OUT = sys.argv[1], sys.argv[2]

FOOT = """<div style="font-family:'DejaVu Sans',sans-serif;font-size:7pt;color:#6b7280;
width:100%;padding:0 14mm;display:flex;justify-content:space-between;">
<span>PRD v1.2 · HORMUZ-RATE — 2026-09-07 · 미통과 (재설계 필요)</span>
<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                                    args=["--no-sandbox","--font-render-hinting=none"])
        pg = await b.new_page()
        await pg.goto(f"file://{SRC}", wait_until="networkidle")
        await pg.pdf(path=OUT, format="A4", print_background=True,
                     display_header_footer=True,
                     header_template="<div></div>", footer_template=FOOT,
                     margin={"top":"14mm","bottom":"16mm","left":"14mm","right":"14mm"})
        await b.close()

asyncio.run(main())
