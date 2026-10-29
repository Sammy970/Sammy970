"""Generates the profile's stats and top-languages cards as SVG files.

Runs in GitHub Actions with the repository's GITHUB_TOKEN (see .github/workflows/profile-stats.yml),
so the README doesn't depend on a third-party stats server.

Usage: GITHUB_TOKEN=... python3 stats.py <github-login> <output-dir>
"""
import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from html import escape

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

# Theme
BG = "#0d1117"
BORDER = "#30363d"
TITLE = "#a371f7"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT = "#a371f7"
FONT = "font-family=\"'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif\""


def graphql(token, variables):
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def fetch(token, login):
    user, cursor, repos = None, None, []
    while True:
        page = graphql(token, {"login": login, "cursor": cursor})
        user = user or page
        repos += page["repositories"]["nodes"]
        info = page["repositories"]["pageInfo"]
        if not info["hasNextPage"]:
            break
        cursor = info["endCursor"]
    user["repoNodes"] = repos
    return user


def streaks(calendar):
    days = sorted(
        (d for week in calendar["weeks"] for d in week["contributionDays"]),
        key=lambda d: d["date"],
    )
    counts = {d["date"]: d["contributionCount"] for d in days}
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)
    # Current streak: a day with no contributions *today* doesn't break it yet.
    current, day = 0, date.today()
    if counts.get(day.isoformat(), 0) == 0:
        day -= timedelta(days=1)
    while counts.get(day.isoformat(), 0) > 0:
        current += 1
        day -= timedelta(days=1)
    return current, longest


def fmt(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def stats_card(user):
    calendar = user["contributionsCollection"]["contributionCalendar"]
    current, longest = streaks(calendar)
    stars = sum(r["stargazerCount"] for r in user["repoNodes"])
    name = escape((user["name"] or user["login"]).split(" ")[0])
    rows = [
        ("Total stars", stars),
        ("Commits (last year)", user["contributionsCollection"]["totalCommitContributions"]),
        ("Pull requests", user["pullRequests"]["totalCount"]),
        ("Issues", user["issues"]["totalCount"]),
        ("Public repos", user["repositories"]["totalCount"]),
        ("Followers", user["followers"]["totalCount"]),
    ]
    lines = []
    for i, (label, value) in enumerate(rows):
        y = 74 + i * 25
        lines.append(
            f'<circle cx="32" cy="{y - 5}" r="4" fill="{ACCENT}"/>'
            f'<text x="46" y="{y}" fill="{TEXT}" font-size="14" {FONT}>{label}</text>'
            f'<text x="250" y="{y}" fill="{TEXT}" font-size="14" font-weight="700" text-anchor="end" {FONT}>{fmt(value)}</text>'
        )
    right = [
        (fmt(calendar["totalContributions"]), "contributions this year", 92),
        (str(current), "day current streak", 148),
        (str(longest), "day longest streak", 204),
    ]
    blocks = "".join(
        f'<text x="400" y="{y}" fill="{TITLE}" font-size="26" font-weight="700" text-anchor="middle" {FONT}>{big}</text>'
        f'<text x="400" y="{y + 18}" fill="{MUTED}" font-size="12" text-anchor="middle" {FONT}>{small}</text>'
        for big, small, y in right
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="240" viewBox="0 0 495 240">'
        f'<rect x="0.5" y="0.5" width="494" height="239" rx="10" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="25" y="36" fill="{TITLE}" font-size="18" font-weight="700" {FONT}>{name}\'s GitHub stats</text>'
        f'<line x1="305" y1="58" x2="305" y2="214" stroke="{BORDER}"/>'
        f'{"".join(lines)}{blocks}</svg>'
    )


def languages_card(user, limit=8):
    totals, colors = {}, {}
    for repo in user["repoNodes"]:
        for edge in repo["languages"]["edges"]:
            lang = edge["node"]["name"]
            totals[lang] = totals.get(lang, 0) + edge["size"]
            colors[lang] = edge["node"]["color"] or MUTED
    top = sorted(totals.items(), key=lambda kv: -kv[1])[:limit]
    total = sum(size for _, size in top) or 1

    bar, x = [], 25.0
    for lang, size in top:
        width = 445 * size / total
        bar.append(f'<rect x="{x:.2f}" y="56" width="{width:.2f}" height="10" fill="{colors[lang]}"/>')
        x += width
    legend = []
    for i, (lang, size) in enumerate(top):
        col, row = i % 2, i // 2
        lx, ly = 25 + col * 225, 98 + row * 26
        legend.append(
            f'<circle cx="{lx + 5}" cy="{ly - 5}" r="5" fill="{colors[lang]}"/>'
            f'<text x="{lx + 18}" y="{ly}" fill="{TEXT}" font-size="13" {FONT}>{escape(lang)}</text>'
            f'<text x="{lx + 205}" y="{ly}" fill="{MUTED}" font-size="13" text-anchor="end" {FONT}>{100 * size / total:.1f}%</text>'
        )
    # At least as tall as the stats card, so the two line up side by side.
    height = max(240, 98 + ((len(top) + 1) // 2) * 26)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="495" height="{height}" viewBox="0 0 495 {height}">'
        f'<rect x="0.5" y="0.5" width="494" height="{height - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="25" y="36" fill="{TITLE}" font-size="18" font-weight="700" {FONT}>Most used languages</text>'
        f'<clipPath id="bar"><rect x="25" y="56" width="445" height="10" rx="5"/></clipPath>'
        f'<g clip-path="url(#bar)">{"".join(bar)}</g>'
        f'{"".join(legend)}</svg>'
    )


def main():
    login, out = sys.argv[1], sys.argv[2]
    token = os.environ["GITHUB_TOKEN"]
    user = fetch(token, login)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "stats.svg"), "w") as f:
        f.write(stats_card(user))
    with open(os.path.join(out, "languages.svg"), "w") as f:
        f.write(languages_card(user))
    print(f"wrote stats.svg and languages.svg for {login} ({len(user['repoNodes'])} repos)")


if __name__ == "__main__":
    main()
