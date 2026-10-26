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
    "dark": dict(bg="#0b1622", border="#1f3347", sea="#12304a", sea2="#0e2539",
                 fin="#d0d7de", box="#39d353", label_text="#0b1622",
                 text="#7d8fa3", accent="#39d353", fov="#39d353", led="#ff5c5c"),
    "light": dict(bg="#eef6fc", border="#c9dcea", sea="#c3dcee", sea2="#d6e8f5",
                  fin="#1f2a36", box="#1a7f37", label_text="#ffffff",
                  text="#4f6273", accent="#1a7f37", fov="#1a7f37", led="#d1242f"),
}


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
.sea{{fill:{c['sea']};animation:swell 5s ease-in-out infinite}}
@keyframes swell{{0%,100%{{fill:{c['sea']}}}50%{{fill:{c['sea2']}}}}}
.hud{{fill:{c['text']};font-size:9px;letter-spacing:.5px}}
.acc{{fill:{c['accent']}}}
.lbl{{fill:{c['label_text']};font-size:7px;font-weight:700}}
</style>""")
    a(f'<rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="8" fill="{c["bg"]}" stroke="{c["border"]}"/>')

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
