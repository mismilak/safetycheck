"""Builds app/static vendor assets from npm packages (run once; outputs are committed).

    npm i vazirmatn chart.js lucide-static   # in any temp dir
    python tools/build_assets.py /path/to/node_modules
"""
import shutil
import sys
from pathlib import Path

from fontTools import subset
from PIL import Image, ImageDraw, ImageFilter

NM = Path(sys.argv[1] if len(sys.argv) > 1 else "node_modules")
ST = Path(__file__).resolve().parent.parent / "app" / "static"

ICONS = """video bell-ring chart-column file-spreadsheet camera settings users log-out user shield-check shield-alert
hard-hat shirt check x triangle-alert sun moon volume-2 volume-x download refresh-cw search eye trash-2 plus pencil
wifi wifi-off menu circle-check circle-x clock activity key-round lock image maximize history info save send
flag check-check users-round printer chevron-left chevron-right user-round monitor-play radio scan-eye siren download-cloud
sliders-horizontal bell filter-x calendar""".split()


def font():
    src = NM / "vazirmatn/fonts/webfonts/Vazirmatn[wght].woff2"
    out = ST / "fonts/Vazirmatn-subset.woff2"
    out.parent.mkdir(parents=True, exist_ok=True)
    unicodes = "U+0020-007E,U+00A0,U+00AB,U+00BB,U+0600-06FF,U+200C-200F,U+2010-2027,U+2190-2193,U+00D7,U+2022,U+2026,U+066A-066C"
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    opts.notdef_outline = True
    opts.name_IDs = [1, 2]
    f = subset.load_font(str(src), opts)
    s = subset.Subsetter(opts)
    s.populate(unicodes=subset.parse_unicodes(unicodes))
    s.subset(f)
    subset.save_font(f, str(out), opts)
    print("font", src.stat().st_size, "->", out.stat().st_size)
    shutil.copy(NM / "vazirmatn/OFL.txt", ST / "fonts/OFL.txt")


def chart():
    d = ST / "vendor"
    d.mkdir(parents=True, exist_ok=True)
    src = NM / "chart.js/dist/chart.umd.min.js"
    if not src.exists():
        src = NM / "chart.js/dist/chart.umd.js"
    shutil.copy(src, d / "chart.umd.min.js")
    lic = NM / "chart.js/LICENSE.md"
    if lic.exists():
        shutil.copy(lic, d / "chart.LICENSE.md")
    print("chart", (d / "chart.umd.min.js").stat().st_size)


def sprite():
    base = NM / "lucide-static/icons"
    parts = ['<svg xmlns="http://www.w3.org/2000/svg">']
    for n in ICONS:
        svg = (base / f"{n}.svg").read_text()
        inner = svg[svg.index(">", svg.index("<svg")) + 1: svg.rindex("</svg>")].strip()
        parts.append(f'<symbol id="i-{n}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
                     f'stroke-linecap="round" stroke-linejoin="round">{inner}</symbol>')
    parts.append("</svg>")
    out = ST / "icons/sprite.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts))
    lic = NM / "lucide-static/LICENSE"
    if lic.exists():
        shutil.copy(lic, ST / "icons/LICENSE-lucide.txt")
    print("sprite", len(ICONS), out.stat().st_size)


def app_icon(size: int, maskable: bool = False) -> Image.Image:
    S = 4
    n = size * S
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    bg = Image.new("RGBA", (n, n))
    px = bg.load()
    for y in range(n):  # vertical gradient
        t = y / n
        c = (int(16 + 12 * t), int(24 + 14 * t), int(48 + 26 * t), 255)
        for x in range(n):
            px[x, y] = c
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, n, n), radius=0 if maskable else int(n * 0.22), fill=255)
    img.paste(bg, (0, 0), mask)
    d = ImageDraw.Draw(img)
    k = 0.62 if maskable else 0.72  # maskable keeps content inside the safe zone
    w, h = n * k * 0.78, n * k
    cx, top = n / 2, n * (1 - k) / 2 + n * 0.01
    pts = [(cx - w / 2, top + h * .12), (cx, top), (cx + w / 2, top + h * .12), (cx + w / 2, top + h * .52),
           (cx, top + h), (cx - w / 2, top + h * .52)]
    glow = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(glow).polygon(pts, fill=(255, 138, 31, 150))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(n * 0.03)))
    d.polygon(pts, fill=(255, 138, 31, 255))
    lw = int(n * 0.055)
    chk = [(cx - w * .22, top + h * .47), (cx - w * .05, top + h * .64), (cx + w * .26, top + h * .32)]
    d.line(chk, fill=(16, 24, 48, 255), width=lw, joint="curve")
    for p in (chk[0], chk[-1]):
        d.ellipse((p[0] - lw / 2, p[1] - lw / 2, p[0] + lw / 2, p[1] + lw / 2), fill=(16, 24, 48, 255))
    return img.resize((size, size), Image.LANCZOS)


def icons():
    d = ST / "icons"
    app_icon(192).save(d / "icon-192.png", optimize=True)
    app_icon(512).save(d / "icon-512.png", optimize=True)
    app_icon(512, True).save(d / "icon-maskable-512.png", optimize=True)
    app_icon(180).save(d / "apple-touch-icon.png", optimize=True)
    app_icon(32).save(d / "favicon-32.png", optimize=True)
    print("icons ok")


if __name__ == "__main__":
    font(); chart(); sprite(); icons()
