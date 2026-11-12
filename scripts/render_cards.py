#!/usr/bin/env python3
"""Render the animated SVG cards used by the profile README.

  python scripts/render_cards.py            fetch fresh contributions, then render every card
  OFFLINE=1 python scripts/render_cards.py  render from data/contributions.json without fetching
  STATIC=1 python scripts/render_cards.py   render every card at its final frame (for screenshots)

Layout lives in README.md; every visual and every animation lives inside the SVGs.
An SVG shown through <img> runs its own <style> (CSS keyframes) and SMIL, but cannot
load web fonts, so the fonts are subset and embedded as base64 WOFF.
"""
import base64
import datetime as dt
import html
import io
import json
import os
import re
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
CARDS, FONTS, DATA = ROOT / "cards", ROOT / "fonts", ROOT / "data" / "contributions.json"
LOGIN = "MohammedSaif29"
STATIC = os.environ.get("STATIC") == "1"
TODAY = dt.date.fromisoformat(os.environ["TODAY"]) if "TODAY" in os.environ else dt.date.today()

# Portfolio palette (mohammed-saif-portfolio.vercel.app)
INK, INK2, INK3 = "#0D0D10", "#131317", "#1B1B21"
TEXT, SOFT, DIM = "#F5F5F7", "#BDBDC7", "#90909C"
LIVE, BLUE, VIOLET, PINK, ORANGE = "#5BE3A0", "#3D7BFF", "#8F5CFF", "#E84FD0", "#FF8A3D"
SPRING, OUT = "cubic-bezier(.34,1.42,.64,1)", "cubic-bezier(.2,.8,.2,1)"


# ---------------------------------------------------------------- data

def fetch_contributions():
    days = {}
    for year in sorted({TODAY.year - 1, TODAY.year}):
        url = f"https://github.com/users/{LOGIN}/contributions?from={year}-01-01&to={year}-12-31"
        req = urllib.request.Request(url, headers={"User-Agent": "profile-cards-renderer"})
        page = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
        tips = dict(re.findall(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)</tool-tip>', page))
        for tag in re.findall(r"<td\b[^>]*\bdata-date=[^>]*>", page):
            date = re.search(r'data-date="([^"]+)"', tag).group(1)
            cid = re.search(r'\bid="([^"]+)"', tag)
            m = re.match(r"\s*(\d+|No) contribution", tips.get(cid.group(1), "") if cid else "")
            if m:
                days[date] = 0 if m.group(1) == "No" else int(m.group(1))
    if not days:
        raise RuntimeError("no contribution days parsed; the calendar markup may have changed")
    return days


def load_contributions():
    old = json.loads(DATA.read_text()) if DATA.exists() else {}
    if os.environ.get("OFFLINE") == "1":
        return old
    try:
        fresh = fetch_contributions()
    except Exception as exc:  # keep the last good data rather than failing the daily run
        print(f"fetch failed, using saved data: {exc}")
        return old
    merged = {**old, **fresh}
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(dict(sorted(merged.items())), indent=0) + "\n")
    return merged


def stats(days):
    start = TODAY - dt.timedelta(days=364)
    window = [(start + dt.timedelta(days=i)) for i in range(365)]
    counts = [days.get(d.isoformat(), 0) for d in window]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    busiest = max(range(365), key=lambda i: (counts[i], i))
    months = []
    y, m = TODAY.year, TODAY.month
    for _ in range(12):
        months.append((y, m))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    months.reverse()
    per_month = [(dt.date(y, m, 1), sum(v for k, v in days.items() if k.startswith(f"{y}-{m:02d}-"))) for y, m in months]
    return {
        "total": sum(counts),
        "active": sum(1 for c in counts if c),
        "longest": longest,
        "busiest": (counts[busiest], window[busiest]),
        "months": per_month,
    }


# ---------------------------------------------------------------- svg helpers

FONT_SPECS = {
    "serif": ("instrument-regular.ttf", "IS", "normal", 400),
    "serif-i": ("instrument-italic.ttf", "IS", "italic", 400),
    "sans": ("bricolage-400.ttf", "BG", "normal", 400),
    "sans-b": ("bricolage-600.ttf", "BG", "normal", 600),
}
GLYPHS = "".join(chr(c) for c in range(32, 127)) + "·—–→↗•…’“”"
_face_cache = {}


def font_face(key):
    if key not in _face_cache:
        file, family, style, weight = FONT_SPECS[key]
        opts = subset.Options()
        opts.flavor = "woff"
        opts.layout_features = ["kern", "liga"]
        opts.hinting = False
        opts.name_IDs = []
        font = TTFont(FONTS / file)
        sub = subset.Subsetter(opts)
        sub.populate(text=GLYPHS)
        sub.subset(font)
        buf = io.BytesIO()
        font.flavor = "woff"
        font.save(buf)
        b64 = base64.b64encode(buf.getvalue()).decode()
        _face_cache[key] = (f"@font-face{{font-family:{family};font-style:{style};font-weight:{weight};"
                            f"src:url(data:font/woff;base64,{b64}) format('woff')}}")
    return _face_cache[key]


BASE_CSS = f"""
.is{{font-family:IS,Georgia,serif}} .it{{font-family:IS,Georgia,serif;font-style:italic}}
.bg{{font-family:BG,-apple-system,'Segoe UI',sans-serif}} .b{{font-weight:600}}
.cap{{font-family:BG,-apple-system,'Segoe UI',sans-serif;font-weight:600;font-size:12px;letter-spacing:2.4px}}
.rise{{animation:rise .9s {OUT} both}}
.fade{{animation:fade .8s {OUT} both}}
.pulse{{animation:pulse 2.4s ease-out infinite;transform-box:fill-box;transform-origin:center}}
.nudge{{animation:nudge 2.8s ease-in-out infinite}}
@keyframes rise{{from{{opacity:0;transform:translateY(26px)}}}}
@keyframes fade{{from{{opacity:0}}}}
@keyframes pulse{{0%{{opacity:.9;transform:scale(1)}}80%,100%{{opacity:0;transform:scale(3.2)}}}}
@keyframes nudge{{0%,60%,100%{{transform:none}}75%{{transform:translate(4px,-4px)}}}}
"""


def esc(s):
    return html.escape(str(s), quote=True)


def delay(s):
    return f'style="animation-delay:{s:.3f}s"'


def svg(w, h, body, title, fonts, css="", defs=""):
    style = "".join(font_face(f) for f in fonts) + BASE_CSS + css
    if STATIC:
        style += "*{animation:none!important}"
        body = re.sub(r"<(animate|animateTransform|set)\b[^>]*/>", "", body)
    else:
        style += "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    dots = ('<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
            '<circle cx="11" cy="11" r="1" fill="#fff" fill-opacity=".055"/></pattern>'
            f'<clipPath id="card"><rect width="{w}" height="{h}" rx="20"/></clipPath>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(title)}"><title>{esc(title)}</title>'
            f"<style>{style}</style><defs>{dots}{defs}</defs>{body}</svg>")


def frame(w, h, glows=()):
    """Card background: ink, dot grid, soft colour glows, hairline border."""
    defs, parts = [], [f'<rect width="{w}" height="{h}" fill="{INK}"/>', f'<rect width="{w}" height="{h}" fill="url(#dots)"/>']
    for i, (cx, cy, r, color, op) in enumerate(glows):
        defs.append(f'<radialGradient id="g{i}"><stop offset="0" stop-color="{color}" stop-opacity="{op}"/>'
                    f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#g{i})"/>')
    bg = f'<g clip-path="url(#card)">{"".join(parts)}</g>'
    border = f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="19.5" fill="none" stroke="#fff" stroke-opacity=".1"/>'
    return "".join(defs), bg, border


def count_up(value, x, y, cls, start, frames=18, step=0.05, suffix=""):
    """CSS cannot change text, so stack one <text> per frame and flash each in turn."""
    target = int(value)
    seen, vals = set(), []
    for i in range(frames):
        t = i / frames
        v = int(round(target * (1 - (1 - t) ** 3)))
        if v < target and v not in seen:
            seen.add(v)
            vals.append(v)
    out = []
    for i, v in enumerate(vals):
        out.append(f'<text x="{x}" y="{y}" class="{cls} cf" style="animation-delay:{start + i * step:.3f}s">{v}{suffix}</text>')
    done = start + len(vals) * step
    out.append(f'<text x="{x}" y="{y}" class="{cls} cfin" style="animation-duration:{done:.3f}s">{target}{suffix}</text>')
    return "".join(out)


COUNT_CSS = f"""
.cf{{opacity:0;animation:flash .05s step-end}}
.cfin{{animation:hold linear}}
@keyframes flash{{0%,100%{{opacity:1}}}}
@keyframes hold{{0%,100%{{opacity:0}}}}
"""


# ---------------------------------------------------------------- cards

def hero():
    w, h = 1200, 470
    gdefs, bg, border = frame(w, h, [(1120, 20, 470, VIOLET, .30), (1180, 300, 300, PINK, .14), (40, 470, 380, BLUE, .18)])
    defs = gdefs + f"""
<linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="0" y1="120" x2="620" y2="340" gradientTransform="translate(-900 0)">
  <stop offset="0" stop-color="{TEXT}"/><stop offset=".40" stop-color="{TEXT}"/>
  <stop offset=".5" stop-color="#9DB8FF"/><stop offset=".60" stop-color="{TEXT}"/><stop offset="1" stop-color="{TEXT}"/>
  <animateTransform attributeName="gradientTransform" type="translate" values="-900 0;900 0;900 0" keyTimes="0;.32;1" dur="7s" begin="2.2s" repeatCount="indefinite"/>
</linearGradient>
<linearGradient id="flare" gradientUnits="userSpaceOnUse" x1="664" y1="0" x2="1130" y2="0">
  <stop offset="0" stop-color="{BLUE}"/><stop offset=".42" stop-color="{VIOLET}"/><stop offset=".74" stop-color="{PINK}"/><stop offset="1" stop-color="{ORANGE}"/>
</linearGradient>
<linearGradient id="flareS" x1="0" x2="1"><stop offset="0" stop-color="{BLUE}"/><stop offset="1" stop-color="{PINK}"/></linearGradient>"""
    words = ["Mac apps.", "AI tools.", "full-stack platforms."]
    word_svg = "".join(
        f'<text x="664" y="252" class="it word w{i}" font-size="54" fill="url(#flare)" style="animation-delay:{1.3 + i * 3:.1f}s">{esc(wd)}</text>'
        for i, wd in enumerate(words))
    para = ["From a Dynamic Island for the MacBook notch",
            "to voice interview coaching, I like shipping",
            "software people can actually try."]
    para_svg = "".join(f'<text x="666" y="{306 + i * 27}" class="bg rise" font-size="18" fill="{SOFT}" {delay(1.1 + i * .08)}>{esc(t)}</text>' for i, t in enumerate(para))
    body = f"""{bg}
<g class="rise" {delay(.1)}><rect x="64" y="84" width="28" height="2" rx="1" fill="url(#flareS)"/>
<text x="104" y="90" class="cap" fill="{DIM}">B.TECH CSE · DATA ENGINEERING FOR AI</text></g>
<text x="56" y="214" class="is rise" font-size="134" fill="url(#shine)" {delay(.25)}>Mohammed</text>
<text x="56" y="344" class="is rise" font-size="134" fill="url(#shine)" {delay(.42)}>Saif</text>
<text x="66" y="404" class="bg rise" font-size="15" fill="{DIM}" {delay(.6)}>KL University · Class of 2028 · CGPA 8.63</text>
<text x="664" y="190" class="is rise" font-size="54" fill="{TEXT}" {delay(.8)}>Builds</text>
{word_svg}
{para_svg}
<g class="rise" {delay(1.45)}>
  <rect x="664" y="384" width="206" height="38" rx="19" fill="#fff" fill-opacity=".04" stroke="#fff" stroke-opacity=".12"/>
  <circle cx="687" cy="403" r="4.5" fill="{LIVE}" class="pulse"/><circle cx="687" cy="403" r="4.5" fill="{LIVE}"/>
  <text x="702" y="408.5" class="bg b" font-size="15" fill="{TEXT}">Open to internships</text>
</g>
{border}"""
    css = f"""
.word{{animation:cycle 9s {OUT} infinite backwards}} .w1,.w2{{opacity:0}}
@keyframes cycle{{0%{{opacity:0;transform:translateY(22px)}}5%,30%{{opacity:1;transform:none}}35%,100%{{opacity:0;transform:translateY(-16px)}}}}
"""
    return svg(w, h, body, "Mohammed Saif. Builds Mac apps, AI tools and full-stack platforms. Open to internships.",
               ["serif", "serif-i", "sans", "sans-b"], css, defs)


def graph(s, days):
    w, h = 1200, 300
    gdefs, bg, border = frame(w, h, [(1200, 0, 380, BLUE, .16)])
    step, cell = 20, 16
    last_sunday = TODAY - dt.timedelta(days=(TODAY.weekday() + 1) % 7)
    first = last_sunday - dt.timedelta(weeks=52)
    x0, y0 = 72, 118
    levels = ["#1B1E2A", "#1E3170", "#2C55C8", BLUE, "#A9C2FF"]

    def level(c):
        return 0 if c == 0 else 1 if c <= 2 else 2 if c <= 5 else 3 if c <= 9 else 4

    cells, labels, last_label_col = [], [], -9
    for col in range(53):
        week = first + dt.timedelta(weeks=col)
        if week.day <= 7 and col - last_label_col >= 3:
            labels.append(f'<text x="{x0 + col * step}" y="104" class="bg fade" font-size="12" fill="{DIM}" {delay(.2)}>{week.strftime("%b")}</text>')
            last_label_col = col
        for row in range(7):
            d = week + dt.timedelta(days=row)
            if d > TODAY:
                continue
            c = days.get(d.isoformat(), 0)
            tip = f"{c} contribution{'s' if c != 1 else ''} on {d:%b} {d.day}"
            cells.append(f'<rect x="{x0 + col * step}" y="{y0 + row * step}" width="{cell}" height="{cell}" rx="4" '
                         f'fill="{levels[level(c)]}" class="pop c{col}"><title>{tip}</title></rect>')
    legend = "".join(f'<rect x="{1010 + i * 20}" y="268" width="14" height="14" rx="3.5" fill="{c}"/>' for i, c in enumerate(levels))
    body = f"""{bg}
<text x="64" y="72" class="is rise" font-size="40" fill="{TEXT}">Contributions</text>
<text x="1136" y="70" class="bg b rise" font-size="15" fill="{SOFT}" text-anchor="end" {delay(.1)}>{s['total']} in the last year</text>
{''.join(labels)}{''.join(cells)}
<g class="fade" {delay(1.6)}><text x="64" y="280" class="bg" font-size="13" fill="{DIM}">github.com/{LOGIN}</text>
<text x="1000" y="280" class="bg" font-size="12" fill="{DIM}" text-anchor="end">Less</text>{legend}
<text x="1112" y="280" class="bg" font-size="12" fill="{DIM}">More</text></g>
{border}"""
    css = (f".pop{{animation:pop .55s {SPRING} both;transform-box:fill-box;transform-origin:center}}"
           f"@keyframes pop{{from{{opacity:0;transform:scale(.2)}}}}"
           + "".join(f".c{i}{{animation-delay:{.25 + i * .024:.3f}s}}" for i in range(53)))
    return svg(w, h, body, f"{s['total']} GitHub contributions in the last year", ["serif", "sans", "sans-b"], css, gdefs)


def activity(s):
    w, h = 1200, 380
    gdefs, bg, border = frame(w, h, [(0, 0, 360, VIOLET, .14)])
    defs = gdefs + (f'<linearGradient id="best" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{BLUE}"/>'
                    f'<stop offset="1" stop-color="{VIOLET}"/></linearGradient>')
    months = s["months"]
    peak = max(v for _, v in months) or 1
    best = max(range(12), key=lambda i: (months[i][1], i))
    left, right, base, tall = 64, 740, 312, 176
    slot = (right - left) / 12
    bars = []
    for i, (d, v) in enumerate(months):
        bw = 30
        x = left + i * slot + (slot - bw) / 2
        bh = max(4, v / peak * tall)
        fill = "url(#best)" if i == best and v else ("#2A2F45" if v else INK3)
        bars.append(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="6" fill="{fill}" class="grow" '
                    f'{delay(.3 + i * .06)}><title>{v} in {d:%B %Y}</title></rect>')
        bars.append(f'<text x="{x + bw / 2:.1f}" y="{base + 26}" class="bg fade" font-size="12" fill="{SOFT if i == best else DIM}" '
                    f'text-anchor="middle" {delay(.3 + i * .06)}>{d:%b}</text>')
        if i == best and v:
            bars.append(f'<text x="{x + bw / 2:.1f}" y="{base - bh - 12:.1f}" class="is popv" font-size="30" fill="{TEXT}" '
                        f'text-anchor="middle">{v}</text>')
    count, day = s["busiest"]
    tiles = [
        ("CONTRIBUTIONS", s["total"], "in the last 12 months", BLUE),
        ("ACTIVE DAYS", s["active"], "days with commits", VIOLET),
        ("LONGEST STREAK", s["longest"], "days in a row", PINK),
        ("BUSIEST DAY", count, f"on {day:%b} {day.day}, {day.year}", ORANGE),
    ]
    st = []
    for i, (label, val, sub, col) in enumerate(tiles):
        x, y = 820 + (i % 2) * 168, 130 + (i // 2) * 116
        st.append(f'<g class="rise" {delay(.9 + i * .1)}><rect x="{x}" y="{y - 9}" width="8" height="8" rx="2" fill="{col}"/>'
                  f'<text x="{x + 16}" y="{y}" class="cap" font-size="11" fill="{DIM}" style="font-size:11px;letter-spacing:2px">{label}</text>'
                  f'<text x="{x - 2}" y="{y + 50}" class="is" font-size="50" fill="{TEXT}">{val}</text>'
                  f'<text x="{x}" y="{y + 74}" class="bg" font-size="13" fill="{DIM}">{esc(sub)}</text></g>')
    body = f"""{bg}
<text x="64" y="72" class="is rise" font-size="40" fill="{TEXT}">Monthly activity</text>
<g class="rise" {delay(.1)}><circle cx="1018" cy="65" r="4" fill="{LIVE}" class="pulse"/><circle cx="1018" cy="65" r="4" fill="{LIVE}"/>
<text x="1136" y="70" class="bg b" font-size="15" fill="{SOFT}" text-anchor="end">Updated daily</text></g>
<line x1="{left}" x2="{right}" y1="{base + .5}" y2="{base + .5}" stroke="#fff" stroke-opacity=".1"/>
{''.join(bars)}
<line x1="782" x2="782" y1="112" y2="{base + 26}" stroke="#fff" stroke-opacity=".08" class="fade" {delay(.8)}/>
{''.join(st)}
{border}"""
    css = (f".grow{{animation:grow .8s {SPRING} both;transform-box:fill-box;transform-origin:bottom}}"
           f"@keyframes grow{{from{{transform:scaleY(0)}}}}"
           f".popv{{animation:popv .6s {SPRING} both;animation-delay:{.3 + 12 * .06 + .5:.2f}s;transform-box:fill-box;transform-origin:bottom}}"
           f"@keyframes popv{{from{{opacity:0;transform:translateY(10px) scale(.6)}}}}")
    return svg(w, h, body, f"Contributions per month. {s['total']} in the last year, best month {months[best][0]:%B} with {months[best][1]}.",
               ["serif", "sans", "sans-b"], css, defs)


def tile(num, label, value, suffix, caption, footer, footer_dim, color, start):
    w, h = 400, 320
    gdefs, bg, border = frame(w, h, [(400, 0, 300, color, .34)])
    defs = gdefs + ('<linearGradient id="sweep" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                    '<stop offset=".5" stop-color="#fff" stop-opacity=".07"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>')
    cap = "".join(f'<text x="36" y="{214 + i * 25}" class="bg" font-size="17" fill="{SOFT}">{esc(t)}</text>' for i, t in enumerate(caption))
    body = f"""<g class="swing" style="animation-delay:{start:.2f}s">{bg}
<g clip-path="url(#card)"><circle cx="400" cy="0" r="46" fill="none" stroke="{color}" stroke-width="1.5" class="ring" style="animation-delay:{start + 1.2:.2f}s"/>
<rect x="0" y="-40" width="150" height="400" fill="url(#sweep)" class="sweep" style="animation-delay:{start + 2:.2f}s"/></g>
<text x="36" y="58" class="cap" fill="{color}">{num} — {esc(label)}</text>
{count_up(value, 30, 178, 'is big', start + .55, suffix=suffix)}
{cap}
<line x1="36" x2="364" y1="268.5" y2="268.5" stroke="#fff" stroke-opacity=".1"/>
<text x="36" y="297" class="bg b" font-size="14" fill="{TEXT}">{esc(footer)}<tspan class="bg" font-weight="400" fill="{DIM}">{esc(footer_dim)}</tspan></text>
<text x="364" y="298" class="bg b nudge" font-size="18" fill="{color}" text-anchor="end">↗</text>
{border}</g>"""
    css = COUNT_CSS + f"""
.big{{font-size:124px;fill:{TEXT}}}
.swing{{animation:swing 1.1s {SPRING} both;transform-box:view-box;transform-origin:50% 100%}}
@keyframes swing{{from{{opacity:0;transform:translateY(70px) rotate(-6deg)}}55%{{opacity:1}}}}
.ring{{animation:ring 3.6s ease-out infinite both;transform-box:fill-box;transform-origin:center;opacity:0}}
@keyframes ring{{0%{{opacity:.7;transform:scale(1)}}70%,100%{{opacity:0;transform:scale(5)}}}}
.sweep{{transform:translateX(-200px) skewX(-18deg);animation:sweep 6s ease-in-out infinite both}}
@keyframes sweep{{0%{{transform:translateX(-200px) skewX(-18deg)}}28%,100%{{transform:translateX(560px) skewX(-18deg)}}}}
"""
    return svg(w, h, body, f"{label}: {value}{suffix} {' '.join(caption)}", ["serif", "sans", "sans-b"], css, defs)


def wrap(text, width, lines):
    out, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width and cur:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(".,;:") + "…"
    return out


def repo_card(name, kind, desc, chips, color, start):
    w, h = 600, 224
    gdefs, bg, border = frame(w, h, [(600, 224, 260, color, .22)])
    lines = "".join(f'<text x="36" y="{134 + i * 23}" class="bg" font-size="15.5" fill="{SOFT}">{esc(t)}</text>'
                    for i, t in enumerate(wrap(desc, 66, 2)))
    x, chip_svg = 36, []
    for i, c in enumerate(chips):
        cw = len(c) * 7.4 + 26
        chip_svg.append(f'<g class="rise" {delay(start + .45 + i * .07)}><rect x="{x}" y="176" width="{cw:.0f}" height="26" rx="13" fill="#fff" fill-opacity=".05" stroke="#fff" stroke-opacity=".1"/>'
                        f'<text x="{x + cw / 2:.1f}" y="193.5" class="bg b" font-size="12" fill="{SOFT}" text-anchor="middle">{esc(c)}</text></g>')
        x += cw + 8
    body = f"""<g class="rise" {delay(start)}>{bg}
<circle cx="41" cy="45" r="5" fill="{color}"/><text x="56" y="50" class="cap" font-size="11" style="font-size:11px" fill="{DIM}">{esc(kind)}</text>
<text x="564" y="52" class="bg b nudge" font-size="20" fill="{color}" text-anchor="end">↗</text>
<text x="34" y="100" class="is" font-size="38" fill="{TEXT}">{esc(name)}</text>
{lines}{border}</g>{''.join(chip_svg)}"""
    return svg(w, h, body, f"{name}: {desc}", ["serif", "sans", "sans-b"], "", gdefs)


# ---------------------------------------------------------------- main

def main():
    days = load_contributions()
    s = stats(days)
    CARDS.mkdir(exist_ok=True)
    cards = {
        "hero.svg": hero(),
        "graph.svg": graph(s, days),
        "activity.svg": activity(s),
        "tile-mac.svg": tile("01", "MAC APPS", 8, "", ["widgets, search and AI", "living in the MacBook notch"], "NotchPal", " · Swift, SwiftUI", BLUE, .1),
        "tile-ai.svg": tile("02", "AI TOOLS", 83, "", ["tests behind an AI", "mock-interview coach"], "AI Interview Coach", " · FastAPI", VIOLET, .25),
        "tile-web.svg": tile("03", "FULL-STACK", 4, "", ["platforms built end to end,", "from database to UI"], "EduVault, AidConnect", " + 2", PINK, .4),
        "repo-notchpal.svg": repo_card("NotchPal", "SWIFT · MACOS APP",
            "A Dynamic Island for every Mac: search and Apple Intelligence in the notch, Live Activities, Siri, music and games.",
            ["Swift", "SwiftUI", "Apple Intelligence", "AppKit"], BLUE, .1),
        "repo-interview.svg": repo_card("AI Interview Coach", "PYTHON · AI",
            "Voice mock interviews with Whisper transcription, LLM scoring, speech-delivery analysis and ATS resume checks.",
            ["FastAPI", "React", "Whisper", "pytest"], VIOLET, .2),
        "repo-eduvault.svg": repo_card("EduVault", "JAVA · FULL-STACK",
            "Resource-sharing platform with role-based dashboards, JWT and Google OAuth, approvals and recommendations.",
            ["Spring Boot", "React", "OAuth2", "MySQL"], PINK, .3),
        "repo-aidconnect.svg": repo_card("AidConnect", "NODE.JS · FULL-STACK",
            "Donation platform linking people in need with donors, with admin-verified requests and donation tracking.",
            ["Node.js", "Express", "SQLite", "JWT"], ORANGE, .4),
    }
    for name, content in cards.items():
        (CARDS / name).write_text(content)
        print(f"{name:22} {len(content) / 1024:6.1f} KB")
    print(f"total {s['total']} · active {s['active']} · streak {s['longest']} · busiest {s['busiest'][0]} on {s['busiest'][1]}")


if __name__ == "__main__":
    main()
