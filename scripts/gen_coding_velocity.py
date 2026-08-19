#!/usr/bin/env python3
"""Regenerate the coding-velocity SVGs and README stats from local commit
history.

Aggregates commit counts and line churn per calendar year across every git
repo cloned under WORK_ROOT, authored by any of the patterns in
AUTHOR_PATTERN_FILE. Output is aggregate numbers only -- no repo names, no
employer name, no author-identifying strings -- since this feeds a public
GitHub profile README. The author-match pattern itself lives outside this
repo (see AUTHOR_PATTERN_FILE) precisely so it never enters git history here.
"""
import os
import re
import subprocess
from collections import defaultdict
from datetime import date, timedelta

WORK_ROOT = os.path.expanduser("~/code/work")
AUTHOR_PATTERN_FILE = os.path.expanduser("~/.config/apandeya-stats/authors.txt")
STATS_DIR = os.path.join(os.path.dirname(__file__), "..", "stats")
OUT_SVG_DARK = os.path.join(STATS_DIR, "coding-velocity-dark.svg")
OUT_SVG_LIGHT = os.path.join(STATS_DIR, "coding-velocity-light.svg")
README_PATH = os.path.join(os.path.dirname(__file__), "..", "README.md")
STATS_START = "<!-- STATS:START -->"
STATS_END = "<!-- STATS:END -->"
CHART_START = "<!-- CHART:START -->"
CHART_END = "<!-- CHART:END -->"

NOISE_RE = re.compile(
    r"(package-lock\.json|yarn\.lock|pnpm-lock\.yaml|poetry\.lock|Cargo\.lock|Gemfile\.lock"
    r"|\.min\.js$|/dist/|/vendor/|/node_modules/|\.svg$|\.snap$|/generated/)",
    re.IGNORECASE,
)

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "title": "#e6edf3",
        "sub": "#8b949e",
        "grid": "#30363d",
        "val": "#c9d1d9",
        "yr": "#8b949e",
        "bar_pre": "#3987e5",
        "bar_ai": "#d95926",
        "trend": "#e6edf3",
        "trend_dot": "#f0f0f0",
    },
    "light": {
        "bg": "#ffffff",
        "title": "#1f2328",
        "sub": "#656d76",
        "grid": "#d0d7de",
        "val": "#57606a",
        "yr": "#656d76",
        "bar_pre": "#2a78d6",
        "bar_ai": "#eb6834",
        "trend": "#1f2328",
        "trend_dot": "#1f2328",
    },
}


def load_author_pattern():
    if not os.path.exists(AUTHOR_PATTERN_FILE):
        raise SystemExit(
            f"Missing {AUTHOR_PATTERN_FILE}.\n"
            "This file holds the git-author regex used to match your commits and is "
            "deliberately kept outside this (public) repo. Create it with one line, e.g.:\n"
            "  mkdir -p ~/.config/apandeya-stats\n"
            "  echo 'you@example.com|another@example.com' > ~/.config/apandeya-stats/authors.txt"
        )
    with open(AUTHOR_PATTERN_FILE) as f:
        pattern = f.read().strip()
    if not pattern:
        raise SystemExit(f"{AUTHOR_PATTERN_FILE} is empty.")
    return pattern


def local_repos():
    return [
        os.path.join(WORK_ROOT, n)
        for n in os.listdir(WORK_ROOT)
        if os.path.isdir(os.path.join(WORK_ROOT, n, ".git"))
    ]


def collect(author_pattern, repos):
    year_stats = defaultdict(lambda: {"commits": 0, "loc": 0, "days": set(), "sizes": [], "repos": set()})

    for repo in repos:
        repo_name = os.path.basename(repo)
        out = subprocess.run(
            ["git", "log", "--all", "--author=" + author_pattern, "-E",
             "--date=format:%Y-%m-%d", "--pretty=format:C|%H|%ad", "--numstat"],
            cwd=repo, capture_output=True, text=True, timeout=60,
        ).stdout
        cur_year = cur_day = None
        cur_size = 0
        started = False

        def flush():
            if started:
                year_stats[cur_year]["sizes"].append(cur_size)

        for line in out.splitlines():
            if line.startswith("C|"):
                flush()
                _, _h, d = line.split("|", 2)
                cur_year, cur_day = d[:4], d
                cur_size = 0
                started = True
                year_stats[cur_year]["commits"] += 1
                year_stats[cur_year]["days"].add(cur_day)
                year_stats[cur_year]["repos"].add(repo_name)
            elif line.strip():
                parts = line.split("\t")
                if len(parts) == 3:
                    add, dele, fname = parts
                    if NOISE_RE.search(fname):
                        continue
                    a = int(add) if add.isdigit() else 0
                    d2 = int(dele) if dele.isdigit() else 0
                    year_stats[cur_year]["loc"] += a + d2
                    cur_size += a + d2
        flush()

    return year_stats


def recent_active_days(author_pattern, repos, window_days=30):
    since = (date.today() - timedelta(days=window_days)).isoformat()
    days = set()
    for repo in repos:
        out = subprocess.run(
            ["git", "log", "--all", "--author=" + author_pattern, "-E",
             f"--since={since}", "--date=format:%Y-%m-%d", "--pretty=format:%ad"],
            cwd=repo, capture_output=True, text=True, timeout=60,
        ).stdout
        days.update(line.strip() for line in out.splitlines() if line.strip())
    return len(days), window_days


def median(lst):
    if not lst:
        return 0
    s = sorted(lst)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def build_rows(year_stats):
    today = date.today()
    rows = []
    for year in sorted(year_stats.keys()):
        s = year_stats[year]
        days = len(s["days"])
        if days == 0:
            continue
        commits = s["commits"]
        loc = s["loc"]
        rows.append({
            "year": year,
            "commits": commits,
            "loc": loc,
            "active_days": days,
            "loc_per_day": loc / days,
            "median": median(s["sizes"]),
            "mean": round(loc / commits, 1) if commits else 0,
            "repos_touched": len(s["repos"]),
            "partial": str(today.year) == year,
        })
    return rows


SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 300" width="760" height="300" font-family="Helvetica, Arial, sans-serif">
  <style>
    .bg {{ fill: {bg}; }}
    .title {{ fill: {title}; font-size: 15px; font-weight: 700; }}
    .sub {{ fill: {sub}; font-size: 11px; }}
    .grid {{ stroke: {grid}; stroke-width: 1; }}
    .val {{ fill: {val}; font-size: 10px; font-family: "SF Mono", Consolas, monospace; }}
    .bar-pre {{ fill: {bar_pre}; }}
    .bar-ai {{ fill: {bar_ai}; }}
    .yr {{ fill: {yr}; font-size: 11px; }}
    .trend {{ fill: none; stroke: {trend}; stroke-width: 1.5; stroke-dasharray: 3 3; opacity: 0.6; }}
    .trend-dot {{ fill: {trend_dot}; }}
  </style>
  <rect class="bg" width="760" height="300" rx="10"/>
  <text x="24" y="30" class="title">Lines changed per active coding day</text>
  <text x="24" y="48" class="sub">personal commit history, aggregated by year{partial_note}</text>
{bars}
</svg>
"""


def render_svg(rows, theme_name):
    theme = THEMES[theme_name]
    pad_l, pad_r, pad_t, pad_b = 50, 24, 70, 40
    width, height = 760, 300
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(rows)
    gap = 16
    bar_w = (plot_w - gap * (n - 1)) / n if n else 0
    max_v = max((r["loc_per_day"] for r in rows), default=1) * 1.15

    parts = []
    for i in range(1, 4):
        y = pad_t + plot_h - plot_h * i / 3
        parts.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y:.1f}" y2="{y:.1f}" class="grid"/>')

    centers = []
    for i, r in enumerate(rows):
        x = pad_l + i * (bar_w + gap)
        h = (r["loc_per_day"] / max_v) * plot_h
        y = pad_t + plot_h - h
        cls = "bar-ai" if r["loc_per_day"] > 1000 else "bar-pre"
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 2):.1f}" rx="4" class="{cls}"/>')
        parts.append(f'<text x="{x + bar_w/2:.1f}" y="{y - 8:.1f}" text-anchor="middle" class="val">{round(r["loc_per_day"]):,}</text>')
        label = r["year"] + ("*" if r["partial"] else "")
        parts.append(f'<text x="{x + bar_w/2:.1f}" y="{height - pad_b + 20:.1f}" text-anchor="middle" class="yr">{label}</text>')
        centers.append((x + bar_w / 2, y))

    if len(centers) > 1:
        path_d = "M " + " L ".join(f"{cx:.1f} {cy:.1f}" for cx, cy in centers)
        parts.insert(0, f'<path d="{path_d}" class="trend"/>')
        for cx, cy in centers:
            parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" class="trend-dot"/>')

    partial_note = " (* = partial year)" if any(r["partial"] for r in rows) else ""
    return SVG_TEMPLATE.format(bars="\n".join(parts), partial_note=partial_note, **theme)


def render_markdown_table(rows):
    lines = [
        "| Year | Commits | LOC changed | Active days | LOC/day | Median LOC/commit | Mean LOC/commit | Repos touched |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        year_label = r["year"] + (" \\*" if r["partial"] else "")
        lines.append(
            f"| {year_label} | {r['commits']:,} | {r['loc']:,} | {r['active_days']} | "
            f"{round(r['loc_per_day']):,} | {r['median']:g} | {r['mean']:g} | {r['repos_touched']} |"
        )
    if any(r["partial"] for r in rows):
        lines.append("")
        lines.append("\\* partial year")
    return "\n".join(lines)


def render_chart_block(streak_days, streak_window):
    return (
        f'<picture>\n'
        f'  <source media="(prefers-color-scheme: dark)" srcset="stats/coding-velocity-dark.svg">\n'
        f'  <source media="(prefers-color-scheme: light)" srcset="stats/coding-velocity-light.svg">\n'
        f'  <img alt="Coding velocity by year" src="stats/coding-velocity-light.svg">\n'
        f'</picture>\n\n'
        f'\U0001F525 Active on {streak_days} of the last {streak_window} days &nbsp;·&nbsp; '
        f'_last updated {date.today().isoformat()}_'
    )


def replace_block(content, start_marker, end_marker, body, fallback_anchor=None):
    block = f"{start_marker}\n{body}\n{end_marker}"
    if start_marker in content and end_marker in content:
        pre = content.split(start_marker)[0]
        post = content.split(end_marker)[1]
        return pre + block + post
    if fallback_anchor and fallback_anchor in content:
        return content.replace(fallback_anchor, block, 1)
    return content.rstrip() + "\n\n" + block + "\n"


def update_readme(chart_md, table_md):
    with open(README_PATH) as f:
        content = f.read()

    old_image_line = "![Coding velocity by year](stats/coding-velocity.svg)"
    content = replace_block(content, CHART_START, CHART_END, chart_md, fallback_anchor=old_image_line)
    content = replace_block(content, STATS_START, STATS_END, table_md)

    with open(README_PATH, "w") as f:
        f.write(content)


def main():
    author_pattern = load_author_pattern()
    repos = local_repos()

    year_stats = collect(author_pattern, repos)
    rows = build_rows(year_stats)
    streak_days, streak_window = recent_active_days(author_pattern, repos)

    os.makedirs(STATS_DIR, exist_ok=True)
    with open(OUT_SVG_DARK, "w") as f:
        f.write(render_svg(rows, "dark"))
    with open(OUT_SVG_LIGHT, "w") as f:
        f.write(render_svg(rows, "light"))

    chart_md = render_chart_block(streak_days, streak_window)
    table_md = render_markdown_table(rows)
    update_readme(chart_md, table_md)

    print(f"Wrote light/dark SVGs and updated README with {len(rows)} years of data, "
          f"{streak_days}/{streak_window}-day streak")


if __name__ == "__main__":
    main()
