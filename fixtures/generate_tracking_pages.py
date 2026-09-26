"""Sample carrier tracking pages, for testing the page reader without a parcel.

These are NOT copies of any carrier's website. They are plainly-labelled sample
pages written for this repository, laid out the way the four carriers lay out
the same four facts, so the multimodal reader in ``tracking_reader.py`` can be
exercised on an image rather than on text. Every one carries a visible line
saying what it is. Nothing here is scraped and no carrier's markup is reused.

    python fixtures/generate_tracking_pages.py

Writes the HTML and, if Playwright is installed, a PNG of each.
"""

from __future__ import annotations

import pathlib

OUT = pathlib.Path(__file__).resolve().parent / "tracking_pages"

SHELL = """<!doctype html><html><head><meta charset="utf-8"><style>
body {{ font-family: {font}; background: {bg}; margin: 0; padding: 28px; color: #1c1c1c; }}
.card {{ background: #fff; max-width: 620px; margin: 0 auto; padding: 26px 30px 20px;
        border: 1px solid #dcdcdc; border-radius: {radius}; }}
.brand {{ font-weight: 700; font-size: 20px; color: {brand}; letter-spacing: -0.01em; }}
.num {{ font-family: ui-monospace, Menlo, monospace; font-size: 15px; color: #444; margin: 10px 0 20px; }}
.status {{ font-size: 24px; font-weight: 700; margin: 0 0 6px; color: {statuscolor}; }}
.when {{ font-size: 15px; color: #333; margin: 0 0 18px; }}
.detail {{ font-size: 14px; color: #555; border-top: 1px solid #eee; padding-top: 12px; }}
.detail div {{ margin-bottom: 5px; }}
.sample {{ max-width: 620px; margin: 14px auto 0; font-size: 11px; color: #777; text-align: center; }}
</style></head><body>
<div class="card">
  <div class="brand">{brand_name}</div>
  <div class="num">{number_label}: {number}</div>
  <div class="status">{status}</div>
  <div class="when">{when}</div>
  <div class="detail">{detail}</div>
</div>
<p class="sample">Sample page written for the Doorstep Receipt test suite. Not a real carrier page.</p>
</body></html>"""

PAGES = {
    "ups-delivered": dict(
        font="'Helvetica Neue', Arial, sans-serif", bg="#f2f2f2", radius="4px",
        brand="#351c15", brand_name="UPS Tracking", statuscolor="#0a7c2f",
        number_label="Tracking Number", number="1Z999AA10123456784",
        status="Delivered",
        when="Friday, September 20, 2026 at 2:11 P.M.",
        detail="<div>Left At: Front Door</div><div>Delivered To: CLEVELAND, OH, US</div>"
               "<div>Reference Number: ORD-55120</div>",
    ),
    "usps-delivered": dict(
        font="'Source Sans Pro', Arial, sans-serif", bg="#ffffff", radius="0",
        brand="#004b87", brand_name="USPS Tracking&reg;", statuscolor="#1a7f37",
        number_label="Tracking Number", number="9400 1118 9922 3197 4284 90",
        status="Delivered, Front Door/Porch",
        when="September 20, 2026 at 9:03 am",
        detail="<div>CLEVELAND, OH 44101</div><div>Your item was delivered to the front door or porch.</div>",
    ),
    "royalmail-attempted": dict(
        font="'Helvetica Neue', Arial, sans-serif", bg="#f4f4f4", radius="8px",
        brand="#cc092f", brand_name="Royal Mail Track &amp; Trace", statuscolor="#b3401f",
        number_label="Your reference", number="RM123456789GB",
        status="We attempted to deliver your item",
        when="20 September 2026 at 14:11",
        detail="<div>Delivery office: Sheffield DO</div><div>A card was left at the address.</div>",
    ),
    "amazon-safeplace": dict(
        font="'Amazon Ember', Arial, sans-serif", bg="#eaeded", radius="8px",
        brand="#232f3e", brand_name="Amazon Logistics", statuscolor="#067d62",
        number_label="Tracking ID", number="TBA305012345678",
        status="Delivered to safe place",
        when="Sunday 20 September 2026, 14:11",
        detail="<div>Left in: Porch</div><div>Order # 203-5512099-1180213</div>",
    ),
}


def write_html() -> list[pathlib.Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, values in PAGES.items():
        path = OUT / f"{name}.html"
        path.write_text(SHELL.format(**values), encoding="utf-8")
        paths.append(path)
    return paths


def write_png(paths: list[pathlib.Path]) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright not installed, HTML written but no PNGs.")
        return
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 720, "height": 460}, device_scale_factor=2)
        for path in paths:
            page.goto(path.as_uri())
            page.screenshot(path=str(path.with_suffix(".png")))
            print("wrote", path.with_suffix(".png").name)
        browser.close()


if __name__ == "__main__":
    write_png(write_html())
