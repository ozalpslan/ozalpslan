#!/usr/bin/env python3
"""Build self-contained profile artwork. Runtime dependencies: Python stdlib only."""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
from datetime import date, datetime, time, timedelta, timezone
from html import escape
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CYAN, MAGENTA, YELLOW = "#00B2EF", "#ED0090", "#F8EE02"
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
THEMES = {
    "light": dict(bg="#FFFFFF", bar="#F6F8FA", border="#D1D9E0", text="#1F2328", muted="#59636E", line="#007EAD"),
    "dark": dict(bg="#0D1117", bar="#161B22", border="#30363D", text="#E6EDF3", muted="#919BA6", line=CYAN),
}
ET.register_namespace("", "http://www.w3.org/2000/svg")


def svg(title: str, description: str, content: str, height: int, width=840) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title description">\n'
        f'<title id="title">{escape(title)}</title>\n'
        f'<desc id="description">{escape(description)}</desc>\n'
        f'<g font-family="{FONT}">{content}</g>\n</svg>\n'
    )


def label(x, y, value, color, size=12, anchor="start", **attrs):
    extra = " ".join(f'{key.replace("_", "-")}="{escape(str(val))}"' for key, val in attrs.items())
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" text-anchor="{anchor}" {extra}>{escape(str(value))}</text>'


def header(theme: str, animated=True, width=840) -> str:
    colors = THEMES[theme]
    mark = ET.parse(ASSETS / "glasshouse-mark.svg").getroot()
    pieces = []
    for original in mark:
        if original.tag.rsplit("}", 1)[-1] != "g":
            continue
        group = copy.deepcopy(original)
        name = group.attrib.pop("id")
        group.set("class", f"mark-{name}")
        if name == "letters":
            group.set("fill", colors["text"])
        pieces.append(ET.tostring(group, encoding="unicode"))
    animation = ""
    if animated:
        frames = []
        for name, sequence in (("outer", [YELLOW, CYAN, MAGENTA]), ("middle", [CYAN, MAGENTA, YELLOW]), ("inner", [MAGENTA, YELLOW, CYAN])):
            a, b, c = sequence
            stops = (("0%,26.666%", a), ("33.333%,60%", b), ("66.666%,93.333%", c), ("100%", a))
            frames.append("@keyframes " + name + "{" + "".join(f"{stop}{{fill:{color}}}" for stop, color in stops) + "}")
            frames.append(f".mark-{name}{{animation:{name} 12s ease-in-out infinite}}")
        animation = "<style>" + "\n".join(frames) + "\n@media(prefers-reduced-motion:reduce){.mark-outer,.mark-middle,.mark-inner{animation:none}}</style>"
    content = f'''{animation}
<defs>
  <radialGradient id="cyan-glow"><stop stop-color="{CYAN}" stop-opacity=".08"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></radialGradient>
  <radialGradient id="pink-glow"><stop stop-color="{MAGENTA}" stop-opacity=".06"/><stop offset="1" stop-color="{MAGENTA}" stop-opacity="0"/></radialGradient>
  <clipPath id="frame"><rect x=".5" y=".5" width="{width-1}" height="319" rx="12"/></clipPath>
</defs>
<rect x=".5" y=".5" width="{width-1}" height="319" rx="12" fill="{colors['bg']}" stroke="{colors['border']}"/>
<g clip-path="url(#frame)">
  <rect x="1" y="1" width="{width-2}" height="42" fill="{colors['bar']}"/>
  <ellipse cx="{width/2-50}" cy="170" rx="225" ry="135" fill="url(#cyan-glow)"/>
  <ellipse cx="{width/2+95}" cy="165" rx="175" ry="130" fill="url(#pink-glow)"/>
</g>
<path d="M1 43H{width-1}" stroke="{colors['border']}"/>
<circle cx="23" cy="22" r="4" fill="{CYAN}"/>
<circle cx="39" cy="22" r="4" fill="{MAGENTA}"/>
<circle cx="55" cy="22" r="4" fill="{YELLOW}"/>
{label(width/2, 26, 'alper@devops: ~', colors['muted'], 12, 'middle')}
{label(width-36, 26, 'bash', colors['muted'], 11, 'end')}
<g transform="translate({width/2-115} 64) scale(.49)">{''.join(pieces)}</g>
{label(width/2, 285, 'LINUX  /  KUBERNETES  /  GITOPS', colors['muted'], 12, 'middle', letter_spacing='1.5')}
'''
    return svg("GlassHouse · DevOps", "The original GH silhouette stays fixed. Its three colored arcs exchange colors every four seconds in a twelve-second loop. Reduced motion shows the original colors.", content, 320, width)


def dates_ending(end: date):
    return [end - timedelta(days=30 - index) for index in range(31)]


def normalize_days(entries, end: date):
    """Reject incomplete data instead of mistaking a failed response for zero activity."""
    expected = dates_ending(end)
    mapped = {}
    for entry in entries:
        day = date.fromisoformat(entry["date"])
        count = entry["contributionCount"]
        if type(count) is not int or count < 0:
            raise ValueError("Contribution counts must be nonnegative integers")
        if day in mapped:
            raise ValueError(f"Duplicate contribution date: {day}")
        mapped[day] = count
    if any(day not in mapped for day in expected):
        raise ValueError("GitHub returned an incomplete 31-day contribution window")
    return [{"date": day.isoformat(), "contributionCount": mapped[day]} for day in expected]


def fetch_activity(username: str, token: str, now: datetime):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ValueError("Invalid GitHub username")
    end = now.date()
    start = datetime.combine(end - timedelta(days=30), time.min, tzinfo=timezone.utc)
    query = """query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar { weeks { contributionDays { date contributionCount } } }
        }
      }
    }"""
    payload = json.dumps({"query": query, "variables": {"login": username, "from": start.isoformat(), "to": now.isoformat()}}).encode()
    request = urllib.request.Request("https://api.github.com/graphql", data=payload, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "ozalpslan-profile",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if not isinstance(body, dict) or body.get("errors") or not (body.get("data") or {}).get("user"):
        raise ValueError("GitHub could not return contribution data; existing artwork was preserved")
    weeks = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = normalize_days([day for week in weeks for day in week["contributionDays"]], end)
    return {"username": username, "updated": now.isoformat(), "source": "GitHub GraphQL contributionCalendar", "days": days}


def activity(theme: str, data=None, width=840) -> str:
    colors = THEMES[theme]
    content = f'<rect x=".5" y=".5" width="{width-1}" height="239" rx="12" fill="{colors["bg"]}" stroke="{colors["border"]}"/>'
    content += label(25, 31, "GITHUB ACTIVITY", colors["text"], 12, letter_spacing="1")
    if data is None:
        content += label(width/2, 118, "Activity data pending first refresh", colors["muted"], 14, "middle")
        content += label(width/2, 146, "Real daily GitHub contributions will appear here.", colors["muted"], 11, "middle")
        return svg("GitHub activity awaiting data", "No contribution data has been fetched yet. No sample or zero values are being presented as real activity.", content, 240, width)
    updated = datetime.fromisoformat(data["updated"])
    days = normalize_days(data["days"], updated.date())
    counts = [entry["contributionCount"] for entry in days]
    total = sum(counts)
    content += label(width-25, 31, f"{total:,} contributions / 31 days", colors["muted"], 12, "end")
    maximum = max(counts)
    step = max(1, math.ceil(maximum / 3))
    ceiling = step * 3
    x0, x1, y0, y1 = 54, width-33, 60, 173
    for index in range(4):
        value = step * index
        y = y1 - (y1 - y0) * value / ceiling
        content += f'<path d="M{x0} {y:.2f}H{x1}" stroke="{colors["border"]}" stroke-dasharray="2 5"/>'
        content += label(x0 - 12, round(y + 4, 2), value, colors["muted"], 11, "end")
    points = [(x0 + (x1 - x0) * i / 30, y1 - (y1 - y0) * value / ceiling) for i, value in enumerate(counts)]
    path = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)
    content += f'<path d="{path}" fill="none" stroke="{colors["line"]}" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"/>'
    for (x, y), entry in zip(points, days):
        content += f'<circle cx="{x:.2f}" cy="{y:.2f}" r="2.8" fill="{MAGENTA}"><title>{entry["date"]}: {entry["contributionCount"]} contributions</title></circle>'
    for i in ((0, 10, 20, 30) if width < 600 else (0, 7, 14, 21, 30)):
        day = date.fromisoformat(days[i]["date"])
        content += label(round(points[i][0], 2), 196, day.strftime("%b %d"), colors["muted"], 11, "middle")
    period = f"{days[0]['date']} — {days[-1]['date']}"
    content += label(25, 224, period, colors["muted"], 10)
    content += label(width-25, 224, f"Updated {updated.strftime('%b %d, %H:%M')} UTC", colors["muted"], 10, "end")
    values = "; ".join(f"{entry['date']}: {entry['contributionCount']}" for entry in days)
    return svg("GitHub contributions · last 31 days", f"{data['username']}. {total} contributions from {period}. Daily counts: {values}.", content, 240, width)


def write_outputs(outputs):
    # Render and validate the whole set before replacing any existing artwork.
    for path, value in outputs.items():
        if path.suffix == ".svg":
            ET.fromstring(value)
    for path, value in outputs.items():
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)


def build_headers():
    write_outputs({ASSETS / f"header-{theme}{'-compact' if width == 420 else ''}{'' if motion else '-static'}.svg": header(theme, motion, width)
                   for theme in THEMES for motion in (True, False) for width in (840, 420)})


def activity_outputs(data):
    return {ASSETS / f"activity-{theme}{'-compact' if width == 420 else ''}.svg": activity(theme, data, width)
            for theme in THEMES for width in (840, 420)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "refresh"))
    parser.add_argument("--username", default="ozalpslan")
    args = parser.parse_args()
    try:
        if args.command == "refresh":
            token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
            if not token:
                raise ValueError("Set GH_TOKEN or GITHUB_TOKEN to refresh. Existing artwork was preserved.")
            data = fetch_activity(args.username, token, datetime.now(timezone.utc))
            outputs = activity_outputs(data)
            outputs[ASSETS / "activity.json"] = json.dumps(data, indent=2) + "\n"
            write_outputs(outputs)
        else:
            cache = ASSETS / "activity.json"
            data = json.loads(cache.read_text()) if cache.exists() else None
            outputs = activity_outputs(data)
            build_headers()
            write_outputs(outputs)
    except (ValueError, KeyError, TypeError, OSError, urllib.error.URLError) as error:
        print(f"Profile generation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
