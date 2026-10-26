"""Shark patrol: turns the GitHub contribution graph into a drone survey.

The grid is ocean. Every day with contributions is a shark. A drone flies a
lawnmower search pattern over it and puts a YOLO-style detection box on each
shark it passes. Output: shark/shark-patrol-dark.svg and shark-patrol-light.svg.

Run: python shark_patrol.py            (uses GITHUB_TOKEN + repo owner)
     python shark_patrol.py --data f.json   (local test, list of {date, level})
"""

import datetime as dt
import hashlib
import json
import os
import re
import sys
import urllib.request

USER = os.environ.get("GITHUB_REPOSITORY_OWNER") or "Gowrishankar-1"
OUT_DIR = "shark"
DUR = 18  # seconds per loop

CELL, GAP = 13, 3
STEP = CELL + GAP
PAD_X, HUD_TOP, HUD_BOTTOM = 16, 36, 34

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

THEMES = {
    "dark": dict(bg="#060503", sea="#ffb000", sea_a=(.05, .10), fin="#fff1c2", box="#ffb000",
                 label_text="#060503", text="#b8a37a", accent="#ffb000", fov="#ff5a1f", led="#ff5a1f",
                 glass="#ffffff", glass_a=(.045, .015), edge="#ffd88a",
                 blobs=("#ffb000", "#ff5a1f", "#7a4a00"), blob_a=.12),
    "light": dict(bg="#fbf6ec", sea="#8a5a12", sea_a=(.07, .14), fin="#2b1d06", box="#a86400",
                  label_text="#ffffff", text="#6e5a36", accent="#a86400", fov="#c2410c", led="#c2410c",
                  glass="#ffffff", glass_a=(.7, .4), edge="#ffffff",
                  blobs=("#ffd38a", "#ffb37a", "#f0d9a8"), blob_a=.55),
}


def glass_bg(c, w, h):
    """Soft colour blobs drifting behind frosted panels (cheap: gradients, no blur filter)."""
    out = [f'<clipPath id="card"><rect width="{w}" height="{h}" rx="12"/></clipPath>',
           '<linearGradient id="glassFill" x1="0" y1="0" x2="0" y2="1">'
           f'<stop offset="0" stop-color="{c["glass"]}" stop-opacity="{c["glass_a"][0]}"/>'
           f'<stop offset="1" stop-color="{c["glass"]}" stop-opacity="{c["glass_a"][1]}"/></linearGradient>',
           '<linearGradient id="glassEdge" x1="0" y1="0" x2="1" y2="1">'
           f'<stop offset="0" stop-color="{c["edge"]}" stop-opacity=".55"/>'
           f'<stop offset=".45" stop-color="{c["edge"]}" stop-opacity=".08"/>'
           f'<stop offset="1" stop-color="{c["edge"]}" stop-opacity=".25"/></linearGradient>']
    for i, col in enumerate(c["blobs"]):
        out.append(f'<radialGradient id="blob{i}"><stop offset="0" stop-color="{col}" stop-opacity="{c["blob_a"]}"/>'
                   f'<stop offset="1" stop-color="{col}" stop-opacity="0"/></radialGradient>')
    out.append(f'<rect width="{w}" height="{h}" rx="12" fill="{c["bg"]}"/>')
    out.append('<g clip-path="url(#card)">')
    spots = [(.82, .1, .55, "-60 40"), (.12, .95, .5, "70 -30"), (.5, .45, .38, "-40 -25")]
    for i, (fx, fy, fr, drift) in enumerate(spots[:len(c["blobs"])]):
        r = fr * w
        out.append(f'<circle cx="{fx * w:.0f}" cy="{fy * h:.0f}" r="{r:.0f}" fill="url(#blob{i})">'
                   f'<animateTransform attributeName="transform" type="translate" values="0 0;{drift};0 0" '
                   f'dur="{16 + i * 5}s" repeatCount="indefinite" calcMode="spline" '
                   f'keySplines=".45 0 .55 1;.45 0 .55 1" keyTimes="0;.5;1"/></circle>')
    out.append('</g>')
    out.append(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="12" fill="none" stroke="url(#glassEdge)"/>')
    return out


def glass_rect(x, y, w, h, rx=10):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="url(#glassFill)" stroke="url(#glassEdge)"/>'
            f'<path d="M{x + rx},{y + .8} H{x + w - rx}" stroke="#ffffff" stroke-opacity=".35" stroke-width=".8"/>')


# ---------------------------------------------------------------- data

def fetch_graphql(token):
    query = """query($login:String!){user(login:$login){contributionsCollection{
      contributionCalendar{totalContributions weeks{contributionDays{
      date contributionCount contributionLevel}}}}}}"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        cal = json.load(r)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [{"date": d["date"], "level": LEVELS.get(d["contributionLevel"], 0),
             "count": d["contributionCount"]}
            for w in cal["weeks"] for d in w["contributionDays"]]
    return days, cal["totalContributions"]


def fetch_html():
    url = f"https://github.com/users/{USER}/contributions"
    with urllib.request.urlopen(url, timeout=30) as r:
        html = r.read().decode()
    days = []
    for tag in re.findall(r"<td[^>]*data-date[^>]*>", html):
        date = re.search(r'data-date="([\d-]+)"', tag)
        level = re.search(r'data-level="(\d)"', tag)
        if date and level:
            days.append({"date": date.group(1), "level": int(level.group(1))})
    m = re.search(r"([\d,]+)\s+contributions?\s+in the last year", html)
    total = int(m.group(1).replace(",", "")) if m else None
    return days, total


def load_days():
    if "--data" in sys.argv:
        days = json.load(open(sys.argv[sys.argv.index("--data") + 1]))
        return days, sum(d.get("count", d["level"]) for d in days)
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        try:
            return fetch_graphql(token)
        except Exception as e:  # fall back to the public page
            print(f"GraphQL failed ({e}), falling back to HTML", file=sys.stderr)
    return fetch_html()


# ---------------------------------------------------------------- layout

def confidence(date, level):
    h = int(hashlib.md5(date.encode()).hexdigest()[:4], 16) / 0xFFFF
    return min(0.99, 0.58 + 0.09 * level + 0.06 * h)


def build(days, total, theme):
    c = THEMES[theme]
    days = sorted(days, key=lambda d: d["date"])
    first = dt.date.fromisoformat(days[0]["date"])
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)  # Sunday
    cells = []
    for d in days:
        day = dt.date.fromisoformat(d["date"])
        cells.append(dict(d, col=(day - start).days // 7, row=(day.weekday() + 1) % 7))
    cols = max(x["col"] for x in cells) + 1

    gx, gy = PAD_X, HUD_TOP
    grid_w, grid_h = cols * STEP - GAP, 7 * STEP - GAP
    W, H = gx * 2 + grid_w, HUD_TOP + grid_h + HUD_BOTTOM

    # Drone route: pass A over rows 0-3 left to right, pass B over rows 3-6 back.
    x0, x1 = gx - 6, gx + grid_w + 6
    ya = gy + (4 * STEP - GAP) / 2
    yb = gy + 3 * STEP + (4 * STEP - GAP) / 2
    tA0, tA1, tB0, tB1, tEnd = 0.03, 0.45, 0.50, 0.92, 0.965

    def detect_time(cell):
        cx = gx + cell["col"] * STEP + CELL / 2
        f = (cx - x0) / (x1 - x0)
        return tA0 + f * (tA1 - tA0) if cell["row"] <= 3 else tB0 + (1 - f) * (tB1 - tB0)

    out = []
    a = out.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'font-family="ui-monospace,SFMono-Regular,Menlo,Consolas,monospace">')
    a(f"""<style>
.sea{{fill:{c['sea']};fill-opacity:{c['sea_a'][0]};animation:swell 5s ease-in-out infinite}}
@keyframes swell{{0%,100%{{fill-opacity:{c['sea_a'][0]}}}50%{{fill-opacity:{c['sea_a'][1]}}}}}
.hud{{fill:{c['text']};font-size:9px;letter-spacing:.5px}}
.acc{{fill:{c['accent']}}}
.lbl{{fill:{c['label_text']};font-size:7px;font-weight:700}}
</style>""")
    out += glass_bg(c, W, H)
    a(glass_rect(gx - 8, gy - 8, grid_w + 16, grid_h + 16, 8))

    # HUD
    sharks = [x for x in cells if x["level"] > 0]
    a(f'<text class="hud" x="{gx}" y="22"><tspan class="acc">&#9679; REC</tspan>'
      f'  UAV-01 · SHARK PATROL · ALT 60m · -34.42, 150.89</text>')

    # Ocean
    for x in cells:
        px, py = gx + x["col"] * STEP, gy + x["row"] * STEP
        delay = -((x["col"] * 0.22 + x["row"] * 0.5) % 5)
        a(f'<rect class="sea" x="{px}" y="{py}" width="{CELL}" height="{CELL}" rx="2" '
          f'style="animation-delay:{delay:.2f}s"/>')

    # Sharks (fins), detection boxes, labels
    times, placed = [], []
    for x in sorted(sharks, key=detect_time):
        px, py = gx + x["col"] * STEP, gy + x["row"] * STEP
        t = detect_time(x)
        times.append(t)
        s = 0.62 + 0.1 * x["level"]
        a(f'<g transform="translate({px + CELL/2},{py + CELL - 1.5}) scale({s:.2f})">'
          f'<path d="M-4.5,0 Q-1,-4 1.5,-9.5 Q2,-4 4.5,0 Z" fill="{c["fin"]}" opacity=".35">'
          f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" '
          f'values=".35;.35;1;1;.35;.35" keyTimes="0;{t:.4f};{t+.008:.4f};.95;.985;1"/></path>'
          f'<path d="M-6,.8 Q-3,-.4 0,.8 T6,.8" fill="none" stroke="{c["fin"]}" stroke-width=".8" opacity=".5"/></g>')
        conf = confidence(x["date"], x["level"])
        bx, by = px - 2, py - 2
        a(f'<g opacity="0"><animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" '
          f'values="0;0;1;1;0;0" keyTimes="0;{t:.4f};{t+.006:.4f};.95;.985;1"/>'
          f'<rect x="{bx}" y="{by}" width="{CELL+4}" height="{CELL+4}" rx="1" fill="none" '
          f'stroke="{c["box"]}" stroke-width="1.4"/></g>')
        t_off = min(t + 0.06, 0.99)
        lw = 48
        lx = min(max(bx, gx), gx + grid_w - lw)
        if any(abs(lx - ox) < lw + 2 and abs(by - oy) < 20 and t < ot for ox, oy, ot in placed):
            continue  # skip a label that would sit on top of another visible one
        placed.append((lx, by, t_off))
        a(f'<g opacity="0"><animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" '
          f'values="0;0;1;1;0;0" keyTimes="0;{t:.4f};{t+.006:.4f};{t_off-.02:.4f};{t_off:.4f};1"/>'
          f'<rect x="{lx}" y="{by - 10}" width="{lw}" height="10" rx="1.5" fill="{c["box"]}"/>'
          f'<text class="lbl" x="{lx + 3}" y="{by - 2.6}">shark {conf:.2f}</text></g>')

    # Detection counter (top right)
    events = sorted(set(round(t, 4) for t in times))
    counts = [sum(1 for t in times if round(t, 4) <= e) for e in events]
    cx_txt = W - gx
    def counter(n, vals, keys):
        a(f'<text class="hud" x="{cx_txt}" y="22" text-anchor="end" opacity="{vals.split(";")[0]}">'
          f'DETECTIONS <tspan class="acc">{n:02d}</tspan>'
          f'<animate attributeName="opacity" dur="{DUR}s" repeatCount="indefinite" calcMode="discrete" '
          f'values="{vals}" keyTimes="{keys}"/></text>')
    if events:
        counter(0, "1;0;1", f"0;{events[0]:.4f};{tEnd:.4f}")
        for i, (e, n) in enumerate(zip(events, counts)):
            nxt = events[i + 1] if i + 1 < len(events) else tEnd
            counter(n, "0;1;0", f"0;{e:.4f};{nxt:.4f}")
    else:
        a(f'<text class="hud" x="{cx_txt}" y="22" text-anchor="end">DETECTIONS <tspan class="acc">00</tspan></text>')

    # Drone with camera field of view
    fw, fh = 3 * STEP + 2, 4 * STEP + 2
    route = (f"{x0},{ya};{x0},{ya};{x1},{ya};{x1},{yb};{x0},{yb};{x0},{yb};{x0},{ya}")
    keys = f"0;{tA0};{tA1};{tB0};{tB1};{tEnd};1"
    br = 6  # bracket length
    corners = "".join(
        f'<path d="M{sx*fw/2},{sy*fh/2 - sy*br} V{sy*fh/2} H{sx*fw/2 - sx*br}" />'
        for sx in (-1, 1) for sy in (-1, 1))
    rotors = "".join(
        f'<g transform="translate({rx},{ry})"><circle r="4.2" fill="{c["fin"]}" opacity=".18"/>'
        f'<line x1="-3.8" y1="0" x2="3.8" y2="0" stroke="{c["fin"]}" stroke-width="1">'
        f'<animateTransform attributeName="transform" type="rotate" from="0" to="360" dur=".25s" repeatCount="indefinite"/></line></g>'
        for rx in (-7, 7) for ry in (-7, 7))
    a(f'<g><animateTransform attributeName="transform" type="translate" dur="{DUR}s" '
      f'repeatCount="indefinite" values="{route}" keyTimes="{keys}"/>'
      f'<rect x="{-fw/2}" y="{-fh/2}" width="{fw}" height="{fh}" fill="{c["fov"]}" opacity=".07"/>'
      f'<g fill="none" stroke="{c["fov"]}" stroke-width="1.3" opacity=".9">{corners}</g>'
      f'<line x1="{-fw/2+3}" x2="{fw/2-3}" y1="0" y2="0" stroke="{c["fov"]}" stroke-width=".8" opacity=".55">'
      f'<animate attributeName="y1" values="{-fh/2+3};{fh/2-3};{-fh/2+3}" dur="1.6s" repeatCount="indefinite"/>'
      f'<animate attributeName="y2" values="{-fh/2+3};{fh/2-3};{-fh/2+3}" dur="1.6s" repeatCount="indefinite"/></line>'
      f'<g stroke="{c["fin"]}" stroke-width="1.6" stroke-linecap="round">'
      f'<line x1="-7" y1="-7" x2="7" y2="7"/><line x1="7" y1="-7" x2="-7" y2="7"/></g>'
      f'{rotors}<rect x="-3.5" y="-3.5" width="7" height="7" rx="1.5" fill="{c["fin"]}"/>'
      f'<circle r="1.3" fill="{c["led"]}"><animate attributeName="opacity" values="1;.15;1" dur="1s" repeatCount="indefinite"/></circle>'
      f'</g>')

    # Footer
    fy = gy + grid_h + 22
    total_txt = f"{total} contributions" if total is not None else f"{len(sharks)} active days"
    a(f'<text class="hud" x="{gx}" y="{fy}">model: YOLO · on-board edge inference · conf &#8805; 0.50</text>')
    a(f'<text class="hud" x="{W-gx}" y="{fy}" text-anchor="end">{total_txt} · last 12 months</text>')
    a("</svg>")
    return "\n".join(out)


def main():
    days, total = load_days()
    if not days:
        sys.exit("No contribution data found")
    os.makedirs(OUT_DIR, exist_ok=True)
    for theme in THEMES:
        path = os.path.join(OUT_DIR, f"shark-patrol-{theme}.svg")
        with open(path, "w") as f:
            f.write(build(days, total, theme))
        print("wrote", path)


if __name__ == "__main__":
    main()
