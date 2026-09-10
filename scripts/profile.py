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
from datetime import date, datetime, timedelta, timezone
from html import escape
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
CYAN, MAGENTA, YELLOW = "#00B2EF", "#ED0090", "#F8EE02"
FONT = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
THEMES = {
    "light": dict(border="#D1D9E0", text="#1F2328", muted="#59636E", line="#007EAD"),
    "dark": dict(border="#30363D", text="#E6EDF3", muted="#919BA6", line=CYAN),
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
            stops = (("0%,18.333%", a), ("33.333%,51.666%", b), ("66.666%,85%", c), ("100%", a))
            frames.append("@keyframes " + name + "{" + "".join(f"{stop}{{fill:{color}}}" for stop, color in stops) + "}")
            frames.append(f".mark-{name}{{animation:{name} 3s ease-in-out infinite}}")
        animation = "<style>" + "\n".join(frames) + "\n@media(prefers-reduced-motion:reduce){.mark-outer,.mark-middle,.mark-inner{animation:none}}</style>"
    compact = width < 600
    scale = .24 if compact else .40
    logo_x = width - (117 if compact else 196)
    content = f'{animation}<g transform="translate({logo_x} 8) scale({scale})">{"".join(pieces)}</g>'
    content += '<g font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif">'
    content += label(0, 42, "Alper Özarslan", colors["text"], 32 if compact else 34, font_weight="650")
    if compact:
        lines = [
            (78, "Linux & DevOps Platform Intern", 18, "text"),
            (105, "GlassHouse · Istanbul, Türkiye", 14, "muted"),
            (151, "I work with Linux and Kubernetes.", 17, "text"),
            (179, "This is where I keep my labs,", 17, "muted"),
            (204, "scripts, and notes.", 17, "muted"),
        ]
    else:
        lines = [
            (79, "Linux & DevOps Platform Intern", 20, "text"),
            (107, "GlassHouse · Istanbul, Türkiye", 14, "muted"),
            (153, "I work with Linux and Kubernetes.", 17, "text"),
            (180, "This is where I keep my labs, scripts, and notes.", 17, "muted"),
        ]
    content += "".join(label(0, y, text, colors[color], size) for y, text, size, color in lines) + "</g>"
    description = ("Alper Özarslan. Linux & DevOps Platform Intern at GlassHouse, Istanbul, Türkiye. "
                   "I work with Linux and Kubernetes. This is where I keep my labs, scripts, and notes. "
                   "The GH logo sits at the upper right. Its arcs exchange colors every second in a three-second loop; reduced motion keeps them still.")
    return svg("Alper Özarslan · Linux & DevOps", description, content, 232 if compact else 216, width)


def normalize_days(entries):
    """Preserve GitHub's native year window, including partial calendar weeks."""
    mapped = {}
    for entry in entries:
        day = date.fromisoformat(entry["date"])
        count = entry["contributionCount"]
        if type(count) is not int or count < 0:
            raise ValueError("Contribution counts must be nonnegative integers")
        if day in mapped:
            raise ValueError(f"Duplicate contribution date: {day}")
        mapped[day] = count
    if not 365 <= len(mapped) <= 373:
        raise ValueError("GitHub returned an incomplete yearly contribution window")
    expected = [min(mapped) + timedelta(days=i) for i in range(len(mapped))]
    if expected[-1] != max(mapped):
        raise ValueError("GitHub returned an incomplete yearly contribution window")
    return [{"date": day.isoformat(), "contributionCount": mapped[day]} for day in expected]


def weekly_totals(days):
    weeks = {}
    for entry in days:
        day = date.fromisoformat(entry["date"])
        sunday = day - timedelta(days=(day.weekday() + 1) % 7)
        week = weeks.setdefault(sunday, {"date": entry["date"], "end": entry["date"], "contributionCount": 0})
        week["end"] = entry["date"]
        week["contributionCount"] += entry["contributionCount"]
    return list(weeks.values())


def validated_calendar(data):
    if data.get("period") != "last_year":
        raise ValueError("Refresh the cached activity to GitHub's yearly calendar before building")
    days = normalize_days(data["days"])
    total = data["totalContributions"]
    if type(total) is not int or total < 0 or total != sum(day["contributionCount"] for day in days):
        raise ValueError("Calendar total does not match the daily contribution counts")
    return days


def fetch_activity(username: str, token: str, now: datetime):
    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", username):
        raise ValueError("Invalid GitHub username")
    query = """query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
        }
      }
    }"""
    payload = json.dumps({"query": query, "variables": {"login": username}}).encode()
    request = urllib.request.Request("https://api.github.com/graphql", data=payload, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "ozalpslan-profile",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if not isinstance(body, dict) or body.get("errors") or not (body.get("data") or {}).get("user"):
        raise ValueError("GitHub could not return contribution data; existing artwork was preserved")
    calendar = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar["weeks"] for day in week["contributionDays"]]
    data = {"username": username, "updated": now.isoformat(), "source": "GitHub GraphQL contributionCalendar",
            "period": "last_year", "totalContributions": calendar["totalContributions"], "days": days}
    data["days"] = validated_calendar(data)
    return data


def activity(theme: str, data=None, width=840) -> str:
    colors = THEMES[theme]
    content = ""
    if data is None:
        content += label(width/2, 118, "Yearly contributions pending first refresh", colors["muted"], 13, "middle")
        content += label(width/2, 146, "The same year window as the GitHub contribution calendar.", colors["muted"], 10, "middle")
        return svg("GitHub activity awaiting data", "No contribution data has been fetched yet. No sample or zero values are being presented as real activity.", content, 240, width)
    updated = datetime.fromisoformat(data["updated"])
    days = validated_calendar(data)
    weeks = weekly_totals(days)
    counts = [entry["contributionCount"] for entry in weeks]
    total = data["totalContributions"]
    content += label(0, 22, f"{total:,} contributions in the last year", colors["text"], 15)
    content += label(0, 44, "Weekly totals", colors["muted"], 11)
    maximum = max(counts)
    step = max(1, math.ceil(maximum / 3))
    ceiling = step * 3
    x0, x1, y0, y1 = 32, width-16, 63, 173
    for index in range(4):
        value = step * index
        y = y1 - (y1 - y0) * value / ceiling
        content += f'<path d="M{x0} {y:.2f}H{x1}" stroke="{colors["border"]}" stroke-dasharray="2 5"/>'
        content += label(x0 - 12, round(y + 4, 2), value, colors["muted"], 11, "end")
    points = [(x0 + (x1 - x0) * i / (len(weeks)-1), y1 - (y1 - y0) * value / ceiling) for i, value in enumerate(counts)]
    path = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in points)
    content += f'<path d="{path}" fill="none" stroke="{colors["line"]}" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round"/>'
    for (x, y), entry in zip(points, weeks):
        content += f'<circle cx="{x:.2f}" cy="{y:.2f}" r="1.9" fill="{MAGENTA}"><title>{entry["date"]} to {entry["end"]}: {entry["contributionCount"]} contributions</title></circle>'
    intervals = 4 if width < 600 else 6
    for i in sorted({round(n*(len(weeks)-1)/intervals) for n in range(intervals+1)}):
        day = date.fromisoformat(weeks[i]["date"])
        edge = i in (0, len(weeks)-1)
        anchor = "start" if i == 0 else ("end" if i == len(weeks)-1 else "middle")
        content += label(round(points[i][0], 2), 196, day.strftime("%b %y" if edge else "%b"), colors["muted"], 11, anchor)
    period = f"{days[0]['date']} — {days[-1]['date']}"
    content += label(0, 224, period, colors["muted"], 10)
    content += label(width, 224, f"Updated {updated.strftime('%b %d, %H:%M')} UTC", colors["muted"], 10, "end")
    values = "; ".join(f"{entry['date']} to {entry['end']}: {entry['contributionCount']}" for entry in weeks)
    return svg("GitHub contributions · last year", f"{data['username']}. {total} contributions from {period}, using GitHub's native calendar window. Weekly totals: {values}.", content, 240, width)


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
