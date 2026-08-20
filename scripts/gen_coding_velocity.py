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
        "delta": "#8b949e",
        "trend": "#8b949e",
        "trend_dot": "#d95926",
    },
    "light": {
        "bg": "#ffffff",
        "title": "#1f2328",
        "sub": "#656d76",
        "grid": "#d0d7de",
        "val": "#1f2328",
        "delta": "#656d76",
        "trend": "#8c959f",
        "trend_dot": "#eb6834",
    },
}

METRICS = [
    {"key": "loc_per_day", "label": "LOC / active day", "fmt": lambda v: f"{round(v):,}"},
    {"key": "median", "label": "Median commit size", "fmt": lambda v: f"{v:g}"},
    {"key": "cpd", "label": "Commits / active day", "fmt": lambda v: f"{v:.1f}"},
    {"key": "repos_touched", "label": "Repos touched", "fmt": lambda v: f"{v:g}"},
]


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
            "cpd": commits / days,
            "partial": str(today.year) == year,
        })
    return rows


SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 130" width="760" height="130" font-family="Helvetica, Arial, sans-serif">
  <style>
    .bg {{ fill: {bg}; }}
    .label {{ fill: {sub}; font-size: 10.5px; letter-spacing: 0.02em; }}
    .value {{ fill: {val}; font-size: 17px; font-weight: 700; font-family: "SF Mono", Consolas, monospace; }}
    .delta {{ fill: {delta}; font-size: 10px; font-family: "SF Mono", Consolas, monospace; }}
    .div {{ stroke: {grid}; stroke-width: 1; }}
    .spark {{ fill: none; stroke: {trend}; stroke-width: 1.6; }}
    .spark-dot {{ fill: {trend_dot}; }}
    .point {{ fill: {delta}; font-size: 8.5px; font-family: "SF Mono", Consolas, monospace; }}
  </style>
  <rect class="bg" width="760" height="130" rx="10"/>
{panels}
</svg>
"""


def render_svg(rows, theme_name):
    theme = THEMES[theme_name]
    width, height = 760, 130
    outer_pad, gap = 20, 14
    n_panels = len(METRICS)
    panel_w = (width - 2 * outer_pad - gap * (n_panels - 1)) / n_panels

    spark_top, spark_bottom = 68, 106
    n = len(rows)

    parts = []
    for i, metric in enumerate(METRICS):
        x0 = outer_pad + i * (panel_w + gap)
        values = [r[metric["key"]] for r in rows]
        last, prev = values[-1], values[-2] if len(values) > 1 else None
        delta_txt = ""
        if prev:
            pct = (last - prev) / prev * 100
            arrow = "▲" if pct >= 0 else "▼"
            delta_txt = f"{arrow} {abs(pct):.0f}%"

        parts.append(f'<text x="{x0:.1f}" y="20" class="label">{metric["label"]}</text>')
        parts.append(f'<text x="{x0:.1f}" y="42" class="value">{metric["fmt"](last)}</text>')
        if delta_txt:
            parts.append(f'<text x="{x0:.1f}" y="57" class="delta">{delta_txt} vs prior yr</text>')

        vmin, vmax = min(values), max(values)
        span = (vmax - vmin) or 1
        pts = []
        for j, v in enumerate(values):
            px = x0 + (j / (n - 1) * panel_w if n > 1 else panel_w / 2)
            py = spark_bottom - ((v - vmin) / span) * (spark_bottom - spark_top)
            pts.append((px, py))
        path_d = "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in pts)
        parts.append(f'<path d="{path_d}" class="spark"/>')
        parts.append(f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.8" class="spark-dot"/>')

        mid = (spark_top + spark_bottom) / 2
        start_px, start_py = pts[0]
        start_dy = -8 if start_py > mid else 11
        parts.append(
            f'<text x="{start_px:.1f}" y="{start_py + start_dy:.1f}" text-anchor="start" '
            f'class="point">{metric["fmt"](values[0])}</text>'
        )

        if i > 0:
            div_x = x0 - gap / 2
            parts.append(f'<line x1="{div_x:.1f}" x2="{div_x:.1f}" y1="14" y2="{spark_bottom}" class="div"/>')

    year_span = f"{rows[0]['year']}–{rows[-1]['year']}" if rows else ""
    caption = year_span + (" (latest partial)" if any(r["partial"] for r in rows) else "")
    parts.append(f'<text x="{outer_pad}" y="122" class="delta">{caption}</text>')

    return SVG_TEMPLATE.format(panels="\n".join(parts), **theme)


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
