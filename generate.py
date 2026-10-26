"""Builds the mission-control profile card (dark_mode.svg and light_mode.svg).

Sequence on every page load (plays once, then holds):
  0.0s  boot log types out like firmware on a serial console
  2.3s  a LiDAR sweep reveals the portrait as a point cloud
  4.3s  a detection box locks onto the face
  2.5s+ telemetry panel and ROS 2 node graph come online, then stay live

If a viewer can't run SVG animation, it shows the finished card (no stuck boot screen).
Edit profile_config.json for the text. ascii_art_dark.txt / ascii_art_light.txt hold the portrait.
"""
import hashlib
import json
import math
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 880, 478
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,'DejaVu Sans Mono',monospace"
RAMP = " .:-=+*#%@"

# Layout
TOP_BAR = 34
PANEL_Y, PANEL_H = 42, 374
LP_X, LP_W = 16, 324          # LiDAR panel
RP_X = LP_X + LP_W + 10       # telemetry panel
RP_W = W - 16 - RP_X
FOOT_Y = PANEL_Y + PANEL_H + 8

# Timeline (seconds)
BOOT_START, BOOT_DT = 0.15, 0.24
BOOT_FADE = (2.0, 2.4)
SCAN = (2.3, 4.3)
LOCK = 4.3
TELE_START, TELE_DT = 2.5, 0.22
FOOT_IN = 3.8

THEMES = {
    "dark": dict(bg="#0d0b07", panel="#17120a", border="#3a2e18", text="#fff4dc",
                 muted="#b8a37a", accent="#ffb000", accent2="#ff5a1f", boot_bg="#080603",
                 pts=("#4a3510", "#8a5a12", "#ffb000", "#fff1c2"), grid="#2a2010",
                 glass="#ffffff", glass_a=(.07, .02), edge="#ffd88a",
                 blobs=("#ffb000", "#ff5a1f", "#7a4a00"), blob_a=.28,
                 title=("#ffd36b", "#ff5a1f")),
    "light": dict(bg="#fbf6ec", panel="#ffffff", border="#e6d7b8", text="#241a0a",
                  muted="#6e5a36", accent="#a86400", accent2="#c2410c", boot_bg="#120d05",
                  pts=("#efdcb4", "#d39b3a", "#a86400", "#3d2600"), grid="#efe3cc",
                  glass="#ffffff", glass_a=(.72, .45), edge="#ffffff",
                  blobs=("#ffd38a", "#ffb37a", "#f0d9a8"), blob_a=.6,
                  title=("#a86400", "#c2410c")),
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


def once(attr, t0, t1, v0, v1, extra=""):
    """Animate attr from v0 to v1 between t0 and t1, starting at page load, then hold."""
    t0 = max(t0, 0.001)
    return (f'<animate attributeName="{attr}" begin="0s" dur="{t1:.3f}s" fill="freeze" '
            f'values="{v0};{v0};{v1}" keyTimes="0;{t0 / t1:.4f};1" {extra}/>')


def jitter(i, j, amp):
    h = hashlib.md5(f"{i},{j}".encode()).digest()
    return (h[0] / 255 - 0.5) * amp, (h[1] / 255 - 0.5) * amp


def lidar_panel(c, art):
    out = []
    a = out.append
    rows, cols = len(art), max(len(l) for l in art)
    sx = (LP_W - 16) / cols
    sy = (PANEL_H - 40) / rows
    ox, oy = LP_X + 8 + sx / 2, PANEL_Y + 26
    cx, cy = LP_X + LP_W / 2, PANEL_Y + PANEL_H - 6     # sensor origin
    R = math.hypot(LP_W / 2, PANEL_H) + 10
    C = 2 * math.pi * R

    a(f'<clipPath id="lp"><rect x="{LP_X}" y="{PANEL_Y}" width="{LP_W}" height="{PANEL_H}" rx="10"/></clipPath>')
    a(f'<mask id="scan"><circle cx="{cx}" cy="{cy}" r="{R:.1f}" fill="none" stroke="#fff" '
      f'stroke-width="{2 * R:.1f}" stroke-dasharray="{C:.1f} {C:.1f}" transform="rotate(180 {cx} {cy})">'
      + once("stroke-dasharray", SCAN[0], SCAN[1], f"0 {C:.1f}", f"{C / 2:.1f} {C:.1f}")
      + '</circle></mask>')
    a(f'<radialGradient id="beam" cx="{cx}" cy="{cy}" r="{R:.1f}" gradientUnits="userSpaceOnUse">'
      f'<stop offset="0" stop-color="{c["accent"]}" stop-opacity=".55"/>'
      f'<stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/></radialGradient>')

    a(f'<g clip-path="url(#lp)">')
    # range rings and bearing lines
    for r in (110, 220, 330):
        a(f'<path d="M{cx - r},{cy} A{r},{r} 0 0 1 {cx + r},{cy}" fill="none" stroke="{c["grid"]}" stroke-dasharray="2 4"/>')
    for deg in (30, 60, 90, 120, 150):
        rad = math.radians(deg)
        a(f'<line x1="{cx}" y1="{cy}" x2="{cx - R * math.cos(rad):.1f}" y2="{cy - R * math.sin(rad):.1f}" '
          f'stroke="{c["grid"]}" stroke-dasharray="1 5"/>')

    # point cloud, one dot per ASCII character, sized and coloured by density
    groups = {k: [] for k in range(4)}
    for i, line in enumerate(art):
        for j, ch in enumerate(line):
            d = RAMP.find(ch)
            if d < 2:
                continue
            jx, jy = jitter(i, j, 1.2)
            x, y = ox + j * sx + jx, oy + i * sy + jy
            groups[min((d - 2) * 4 // 8, 3)].append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{0.55 + d * 0.16:.2f}"/>')
    a('<g mask="url(#scan)">')
    for k, pts in groups.items():
        a(f'<g fill="{c["pts"][k]}">{"".join(pts)}</g>')
    a("</g>")

    # rotating beam: sweeps with the reveal, then keeps scanning
    half = math.radians(2.5)
    bx1, by1 = cx - R * math.cos(half), cy - R * math.sin(half)
    bx2, by2 = cx - R * math.cos(-half), cy - R * math.sin(-half)
    a(f'<g opacity="0"><set attributeName="opacity" to="1" begin="{SCAN[0]}s" fill="freeze"/>'
      f'<path d="M{cx},{cy} L{bx1:.1f},{by1:.1f} L{bx2:.1f},{by2:.1f} Z" fill="url(#beam)">'
      f'<animateTransform attributeName="transform" type="rotate" begin="{SCAN[0]}s" dur="4s" '
      f'repeatCount="indefinite" values="0 {cx} {cy};180 {cx} {cy};0 {cx} {cy}" calcMode="spline" '
      f'keySplines=".45 0 .55 1;.45 0 .55 1" keyTimes="0;.5;1"/></path></g>')
    a("</g>")

    # sensor head
    a(f'<path d="M{cx - 9},{cy + 6} A9,9 0 0 1 {cx + 9},{cy + 6} Z" fill="{c["border"]}"/>'
      f'<circle cx="{cx}" cy="{cy}" r="2.2" fill="{c["accent"]}"/>'
      f'<circle cx="{cx}" cy="{cy}" r="4" fill="none" stroke="{c["accent"]}">'
      f'<animate attributeName="r" values="4;16" dur="1.6s" repeatCount="indefinite"/>'
      f'<animate attributeName="opacity" values=".8;0" dur="1.6s" repeatCount="indefinite"/></circle>')

    # detection lock on the face
    fx0, fy0 = ox + 8 * sx, oy + 8.5 * sy
    fx1, fy1 = ox + 47 * sx, oy + 25 * sy
    L = 10
    br = "".join(
        f'<path d="M{x},{y + (L if y == fy0 else -L)} V{y} H{x + (L if x == fx0 else -L)}"/>'
        for x in (fx0, fx1) for y in (fy0, fy1))
    a(f'<g opacity="1">'
      f'<animate attributeName="opacity" begin="0s" dur="{LOCK + .5:.2f}s" fill="freeze" '
      f'values="0;0;1;.2;1;.2;1" keyTimes="0;{LOCK / (LOCK + .5):.4f};{(LOCK + .1) / (LOCK + .5):.4f};'
      f'{(LOCK + .2) / (LOCK + .5):.4f};{(LOCK + .3) / (LOCK + .5):.4f};{(LOCK + .4) / (LOCK + .5):.4f};1"/>'
      f'<g fill="none" stroke="{c["accent"]}" stroke-width="1.6">{br}</g>'
      f'<rect x="{fx0:.1f}" y="{fy0 - 13:.1f}" width="66" height="11" rx="1.5" fill="{c["accent"]}"/>'
      f'<text x="{fx0 + 4:.1f}" y="{fy0 - 4.6:.1f}" font-size="8" font-weight="700" fill="{c["bg"]}">gowri 0.99</text>'
      f'</g>')

    # panel chrome
    a(f'<text x="{LP_X + 10}" y="{PANEL_Y + 15}" class="tag">LIDAR // PILOT SCAN</text>')
    a(f'<text x="{LP_X + LP_W - 10}" y="{PANEL_Y + 15}" class="tag" text-anchor="end">'
      f'{sum(len(p) for p in groups.values())} PTS</text>')
    return out


def telemetry_panel(c, cfg):
    out = []
    a = out.append
    x = RP_X + 16
    kx, vx = x + 4, x + 86
    y = PANEL_Y + 34
    a(f'<text x="{RP_X + 10}" y="{PANEL_Y + 15}" class="tag">TELEMETRY</text>')
    a(f'<text x="{RP_X + RP_W - 10}" y="{PANEL_Y + 15}" class="tag" text-anchor="end">'
      f'<tspan fill="{c["accent"]}">&#9679;</tspan> ONLINE</text>')
    a(f'<g opacity="1">{once("opacity", TELE_START - .15, TELE_START + .25, 0, 1)}'
      f'<text x="{x}" y="{y}" font-size="17" font-weight="700" fill="url(#titleGrad)" filter="url(#glow)">'
      f'{escape(cfg["title"])}</text>'
      f'<text x="{x}" y="{y + 15}" font-size="9.5" fill="{c["muted"]}">{escape(cfg["subtitle"])}</text></g>')
    y += 36
    for gi, g in enumerate(cfg["groups"]):
        t0 = TELE_START + gi * TELE_DT
        a(f'<g opacity="1" transform="translate(0,0)">{once("opacity", t0, t0 + .35, 0, 1)}'
          f'<animateTransform attributeName="transform" type="translate" begin="0s" dur="{t0 + .35:.2f}s" '
          f'fill="freeze" values="10 0;10 0;0 0" keyTimes="0;{t0 / (t0 + .35):.4f};1"/>')
        a(f'<text x="{x}" y="{y}" class="grp">&#9656; {escape(g["name"])}</text>'
          f'<line x1="{x + 22 + len(g["name"]) * 8}" y1="{y - 3}" x2="{RP_X + RP_W - 16}" y2="{y - 3}" '
          f'stroke="{c["border"]}"/>')
        y += 15
        for k, v in g["lines"]:
            a(f'<text x="{kx}" y="{y}" class="key">{escape(k)}</text>'
              f'<text x="{vx}" y="{y}" class="val">{escape(v)}</text>')
            y += 15
        a("</g>")
        y += 5
    return out


def boot_overlay(c, cfg):
    out = []
    a = out.append
    n = len(cfg["boot"])
    a(f'<g opacity="0">{once("opacity", BOOT_FADE[0], BOOT_FADE[1], 1, 0)}')
    a(f'<rect width="{W}" height="{H}" rx="12" fill="{c["boot_bg"]}"/>')
    y0 = 70
    for i, (line, status) in enumerate(cfg["boot"]):
        t = BOOT_START + i * BOOT_DT
        y = y0 + i * 22
        a(f'<clipPath id="bt{i}"><rect x="30" y="{y - 14}" height="20" width="820">'
          + once("width", t, t + .16, 0, 820) + '</rect></clipPath>')
        tag = (f'<tspan fill="#ffb000">[  OK  ]</tspan> ' if status else
               f'<tspan fill="#ff5a1f">&gt;&gt;</tspan> ')
        a(f'<text x="40" y="{y}" font-size="13" fill="#f3e6c8" clip-path="url(#bt{i})">{tag}{escape(line)}</text>')
    yc = y0 + n * 22
    t_end = BOOT_START + n * BOOT_DT
    a(f'<text x="40" y="{H - 92}" font-size="10" fill="#b8a37a" letter-spacing="2">SYSTEM CHECK</text>'
      f'<rect x="40" y="{H - 82}" width="{W - 80}" height="8" rx="2" fill="none" stroke="#3a2e18"/>'
      f'<rect x="42" y="{H - 80}" width="{W - 84}" height="4" fill="url(#titleGrad)">'
      + once("width", .05, t_end, 0, W - 84) + '</rect>'
      f'<text x="{W - 40}" y="{H - 92}" font-size="10" fill="#ffb000" text-anchor="end">{n} MODULES</text>')
    a(f'<text x="40" y="{yc}" font-size="13" fill="#ff5a1f" opacity="0">'
      + once("opacity", BOOT_START + n * BOOT_DT, BOOT_START + n * BOOT_DT + .01, 0, 1)
      + 'launching mission control <tspan fill="#ffb000">&#9612;'
      '<animate attributeName="opacity" values="1;0;1" dur=".5s" repeatCount="indefinite"/></tspan></text>')
    a("</g>")
    return out


def footer(c, cfg):
    out = []
    a = out.append
    y = FOOT_Y + 22
    x0, x1 = 120, W - 30
    a(f'<g opacity="1">{once("opacity", FOOT_IN, FOOT_IN + .4, 0, 1)}')
    a(glass_rect(16, FOOT_Y, W - 32, 44))
    a(f'<line x1="{x0}" y1="{y}" x2="{x1}" y2="{y}" stroke="{c["border"]}" stroke-width="1.5"/>')
    a(f'<path d="M{x1 - 6},{y - 4} L{x1},{y} L{x1 - 6},{y + 4}" fill="none" stroke="{c["border"]}" stroke-width="1.5"/>')
    # message packets travelling along the bus (drawn under the topic boxes)
    for k in range(3):
        b = FOOT_IN + k * 1.07
        a(f'<circle r="2.6" fill="{c["accent"]}" opacity="0"><set attributeName="opacity" to="1" begin="{b:.2f}s" fill="freeze"/>'
          f'<animateMotion path="M{x0},{y} H{x1 - 8}" begin="{b:.2f}s" dur="3.2s" repeatCount="indefinite"/></circle>')
    a(f'<ellipse cx="72" cy="{y}" rx="44" ry="12" fill="{c["bg"]}"/>')
    a(f'<ellipse cx="72" cy="{y}" rx="44" ry="12" fill="{c["accent"]}" fill-opacity=".14" stroke="{c["accent"]}" stroke-width="1.4"/>'
      f'<text x="72" y="{y + 4}" text-anchor="middle" font-size="11" font-weight="700" fill="{c["accent"]}">/gowri</text>')
    topics = cfg["topics"]
    span = (x1 - 40) - (x0 + 30)
    for i, t in enumerate(topics):
        tx = x0 + 30 + span * (i + .5) / len(topics)
        w = len(t) * 6.4 + 14
        a(f'<rect x="{tx - w / 2:.1f}" y="{y - 10}" width="{w:.1f}" height="20" rx="10" fill="{c["bg"]}"/>')
        a(f'<rect x="{tx - w / 2:.1f}" y="{y - 10}" width="{w:.1f}" height="20" rx="10" fill="{c["accent2"]}" fill-opacity=".12" stroke="{c["accent2"]}" stroke-opacity=".7"/>'
          f'<text x="{tx:.1f}" y="{y + 3.5}" text-anchor="middle" font-size="10" fill="{c["accent2"]}">{escape(t)}</text>')
    a("</g>")
    return out


def render(theme, cfg, art):
    c = THEMES[theme]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="{FONT}">']
    a = out.append
    a(f"""<style>
text{{white-space:pre}}
.tag{{fill:{c['muted']};font-size:8.5px;letter-spacing:1.5px}}
.grp{{fill:{c['accent']};font-size:9.5px;font-weight:700;letter-spacing:1.5px}}
.key{{fill:{c['muted']};font-size:11px}}
.val{{fill:{c['text']};font-size:11.5px}}
.hud{{fill:{c['muted']};font-size:9px;letter-spacing:.8px}}
</style>""")
    a('<defs><filter id="glow" x="-20%" y="-50%" width="140%" height="200%">'
      '<feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
      f'<pattern id="scanlines" width="4" height="3" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="{c["text"]}"/></pattern>'
      f'<linearGradient id="sweep" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c["accent"]}" stop-opacity="0"/>'
      f'<stop offset=".5" stop-color="{c["accent"]}" stop-opacity=".05"/><stop offset="1" stop-color="{c["accent"]}" stop-opacity="0"/></linearGradient>'
      f'<linearGradient id="titleGrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{c["title"][0]}"/>'
      f'<stop offset="1" stop-color="{c["title"][1]}"/></linearGradient>'
      '</defs>')
    out += glass_bg(c, W, H)

    # top bar
    bars = "".join(
        f'<rect x="{W - 38 + i * 5}" y="{22 - (i + 1) * 3}" width="3" height="{(i + 1) * 3}" fill="{c["accent"]}">'
        f'<animate attributeName="opacity" values="1;{.25 if i > 1 else 1};1" dur="{1.3 + i * .4:.1f}s" repeatCount="indefinite"/></rect>'
        for i in range(4))
    a(f'<text x="18" y="22" class="hud"><tspan fill="{c["accent"]}">&#9679; REC</tspan>'
      f'<animate attributeName="opacity" values="1;1;.35;1" dur="1.4s" repeatCount="indefinite"/></text>')
    a(f'<text x="64" y="22" class="hud">GCS-01 // MISSION CONTROL</text>')
    a(f'<text x="{W - 46}" y="22" class="hud" text-anchor="end">BASE {escape(cfg["base"])} · {escape(cfg["coords"])} · LINK</text>')
    a(bars)

    # panels
    for px, pw in ((LP_X, LP_W), (RP_X, RP_W)):
        a(glass_rect(px, PANEL_Y, pw, PANEL_H))
        for sxn in (0, 1):
            for syn in (0, 1):
                bx, by = px + sxn * pw, PANEL_Y + syn * PANEL_H
                dx, dy = (8 if sxn == 0 else -8), (8 if syn == 0 else -8)
                a(f'<path d="M{bx},{by + dy} V{by} H{bx + dx}" fill="none" stroke="{c["accent"]}" stroke-width="1.5" opacity=".7"/>')

    out += lidar_panel(c, art)
    out += telemetry_panel(c, cfg)
    out += footer(c, cfg)

    # CRT finish: scanlines plus a slow refresh band
    a(f'<rect width="{W}" height="{H}" rx="12" fill="url(#scanlines)" opacity=".035" pointer-events="none"/>')
    a(f'<rect x="0" y="-120" width="{W}" height="120" fill="url(#sweep)" pointer-events="none">'
      f'<animate attributeName="y" values="-120;{H}" dur="7s" repeatCount="indefinite"/></rect>')

    out += boot_overlay(c, cfg)
    a("</svg>")
    return "\n".join(out)


def main():
    with open(os.path.join(HERE, "profile_config.json")) as f:
        cfg = json.load(f)
    for theme in THEMES:
        with open(os.path.join(HERE, f"ascii_art_{theme}.txt")) as f:
            art = f.read().rstrip("\n").split("\n")
        with open(os.path.join(HERE, f"{theme}_mode.svg"), "w") as f:
            f.write(render(theme, cfg, art))
    print("Wrote dark_mode.svg and light_mode.svg")


if __name__ == "__main__":
    main()
