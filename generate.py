"""Builds the neofetch-style profile card (dark_mode.svg and light_mode.svg).

Edit profile_config.json for your text. ascii_art_dark.txt / ascii_art_light.txt hold the portrait.
The GitHub Action runs this daily with the built-in GITHUB_TOKEN to refresh stats.
"""
import json
import os
import urllib.request
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
WIDTH_CHARS = 60          # width of the right-hand text column
FONT_SIZE = 16
LINE_H = 20
CHAR_W = 9.7              # approx width of one monospace char at 16px
ART_X, TEXT_X, TOP = 25, 470, 32
ART_FONT, ART_LINE = 9, 11  # smaller font = more detail in the portrait

THEMES = {
    "dark": {"bg": "#161b22", "text": "#c9d1d9", "key": "#ffa657",
             "value": "#a5d6ff", "dots": "#616e7f", "art": "#c9d1d9", "accent": "#3fb950"},
    "light": {"bg": "#f6f8fa", "text": "#24292f", "key": "#953800",
              "value": "#0a3069", "dots": "#c2cfde", "art": "#24292f", "accent": "#1a7f37"},
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, first: 100) {
      totalCount
      nodes { stargazerCount }
    }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]) { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar { totalContributions }
    }
  }
}
"""


def fetch_stats(username):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("No GITHUB_TOKEN set, using placeholder stats")
        return {"Repos": "0", "Stars": "0", "Followers": "0",
                "Commits (past year)": "0", "Contributions (past year)": "0"}
    body = json.dumps({"query": QUERY, "variables": {"login": username}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GitHub API error: {data['errors']}")
    u = data["data"]["user"]
    cc = u["contributionsCollection"]
    stars = sum(n["stargazerCount"] for n in u["repositories"]["nodes"])
    return {
        "Repos": f"{u['repositories']['totalCount']} {{Contributed: {u['repositoriesContributedTo']['totalCount']}}}",
        "Stars": f"{stars:,}",
        "Followers": f"{u['followers']['totalCount']:,}",
        "Commits (past year)": f"{cc['totalCommitContributions'] + cc['restrictedContributionsCount']:,}",
        "Contributions (past year)": f"{cc['contributionCalendar']['totalContributions']:,}",
    }


def kv_line(key, value):
    """'. Key: ........ value' padded to WIDTH_CHARS. Returns list of (text, class)."""
    left = f". {key}:"
    gap = WIDTH_CHARS - len(left) - len(value) - 2
    dots = " " + "." * max(gap, 1) + " "
    return [(". ", "text"), (key, "key"), (":", "text"), (dots, "dots"), (value, "value")]


def header_line(text):
    fill = "-" * max(WIDTH_CHARS - len(text) - 3, 1)
    return [("- ", "text"), (text, "text"), (" " + fill, "text")]


def build_lines(cfg, stats):
    lines = [[(cfg["title"], "accent")], [("-" * len(cfg["title"]), "text")]]
    for i, sec in enumerate(cfg["sections"]):
        if i:
            lines.append([])
        if sec.get("header"):
            lines.append(header_line(sec["header"]))
        items = list(stats.items()) if sec.get("stats") else sec["lines"]
        for k, v in items:
            lines.append(kv_line(k, v))
    return lines


def render(theme, art, lines):
    c = THEMES[theme]
    text_h, art_h = len(lines) * LINE_H, len(art) * ART_LINE
    height = TOP + max(text_h, art_h) + 10
    art_y = TOP - 8 + max((text_h - art_h) // 2, 0)  # centre the portrait vertically
    width = int(TEXT_X + WIDTH_CHARS * CHAR_W + 30)
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,\'DejaVu Sans Mono\',monospace" '
        f'width="{width}px" height="{height}px" font-size="{FONT_SIZE}px">',
        "<style>",
        f".text{{fill:{c['text']}}} .key{{fill:{c['key']}}} .value{{fill:{c['value']}}} "
        f".dots{{fill:{c['dots']}}} .art{{fill:{c['art']}}} .accent{{fill:{c['accent']};font-weight:bold}}",
        "text,tspan{white-space:pre}",
        "</style>",
        f'<rect width="{width}px" height="{height}px" fill="{c["bg"]}" rx="15"/>',
        f'<text x="{ART_X}" y="{art_y}" class="art" font-size="{ART_FONT}px">',
    ]
    for i, a in enumerate(art):
        out.append(f'<tspan x="{ART_X}" y="{art_y + i * ART_LINE}">{escape(a)}</tspan>')
    out.append("</text>")
    out.append(f'<text x="{TEXT_X}" y="{TOP}" class="text">')
    for i, parts in enumerate(lines):
        y = TOP + i * LINE_H
        if not parts:
            continue
        segs = "".join(f'<tspan class="{cls}">{escape(t)}</tspan>' for t, cls in parts)
        out.append(f'<tspan x="{TEXT_X}" y="{y}">{segs}</tspan>')
    out.append("</text></svg>")
    return "\n".join(out)


def main():
    with open(os.path.join(HERE, "profile_config.json")) as f:
        cfg = json.load(f)
    lines = build_lines(cfg, fetch_stats(cfg["username"]))
    for theme in THEMES:
        with open(os.path.join(HERE, f"{theme}_mode.svg"), "w") as f:
            with open(os.path.join(HERE, f"ascii_art_{theme}.txt")) as a:
                art = a.read().rstrip("\n").split("\n")
            f.write(render(theme, art, lines))
    print("Wrote dark_mode.svg and light_mode.svg")


if __name__ == "__main__":
    main()
