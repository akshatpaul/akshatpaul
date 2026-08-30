#!/usr/bin/env python3
"""Fetch this year's GitHub contribution calendar, break it down by month,
project a year-end total, and render a bar chart + a stats.md snippet.

Data source: GitHub GraphQL API `user.contributionsCollection.contributionCalendar`.
That calendar counts contributions (commits, PRs, issues, reviews); for a
developer-heavy account it tracks commit activity closely, and it is the only
endpoint that exposes a per-day breakdown. We refer to it as "commits" in the
rendered output for readability.

Environment variables:
  GH_TOKEN / GITHUB_TOKEN   - token with read access to public profile data
                             (the Actions built-in GITHUB_TOKEN works)
  GH_USERNAME               - GitHub login to report on. Falls back to
                             GITHUB_REPOSITORY_OWNER (set in Actions), then to
                             the hard-coded DEFAULT_USERNAME below.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MaxNLocator  # noqa: E402

DEFAULT_USERNAME = "akshatpaul"
GRAPHQL_URL = "https://api.github.com/graphql"
CHART_PATH = "monthly_commits.png"
STATS_PATH = "stats.md"

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def get_token() -> str:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("error: set GH_TOKEN or GITHUB_TOKEN in the environment")
    return token


def get_username() -> str:
    return (
        os.environ.get("GH_USERNAME")
        or os.environ.get("GITHUB_REPOSITORY_OWNER")
        or DEFAULT_USERNAME
    )


def fetch_calendar(token: str, login: str, year: int) -> list[dict]:
    """Return a flat list of {date: 'YYYY-MM-DD', count: int} for the year."""
    frm = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
    to = dt.datetime.now(dt.timezone.utc)
    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": login,
                "from": frm.isoformat(),
                "to": to.isoformat(),
            },
        }
    ).encode()

    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": f"{login}-monthly-commits",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as exc:
        sys.exit(f"error: GitHub API returned {exc.code}: {exc.read().decode()[:400]}")
    except urllib.error.URLError as exc:
        sys.exit(f"error: could not reach GitHub API: {exc}")

    if body.get("errors"):
        sys.exit(f"error: GraphQL errors: {json.dumps(body['errors'])}")

    user = (body.get("data") or {}).get("user")
    if not user:
        sys.exit(f"error: no such user '{login}' or no access")

    days: list[dict] = []
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    for week in weeks:
        for day in week["contributionDays"]:
            days.append({"date": day["date"], "count": day["contributionCount"]})
    return days


def build_report(days: list[dict], year: int) -> dict:
    today = dt.date.today()
    is_current_year = today.year == year

    monthly = [0] * 12
    total_so_far = 0
    for entry in days:
        d = dt.date.fromisoformat(entry["date"])
        if d.year != year:
            continue
        if is_current_year and d > today:
            continue
        monthly[d.month - 1] += entry["count"]
        total_so_far += entry["count"]

    year_start = dt.date(year, 1, 1)
    year_end = dt.date(year, 12, 31)
    days_in_year = (year_end - year_start).days + 1

    if is_current_year:
        days_elapsed = (today - year_start).days + 1
        current_month = today.month
    else:
        days_elapsed = days_in_year
        current_month = None

    daily_avg = total_so_far / days_elapsed if days_elapsed else 0.0
    projected = round(daily_avg * days_in_year)

    return {
        "year": year,
        "monthly": monthly,
        "total_so_far": total_so_far,
        "days_elapsed": days_elapsed,
        "days_in_year": days_in_year,
        "daily_avg": daily_avg,
        "projected": projected,
        "current_month": current_month,
    }


def render_chart(report: dict) -> None:
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    values = report["monthly"]
    current_month = report["current_month"]

    base_color = "#4C72B0"
    current_color = "#DD8452"
    future_color = "#D9D9D9"

    colors = []
    for i in range(12):
        month_num = i + 1
        if current_month and month_num == current_month:
            colors.append(current_color)
        elif current_month and month_num > current_month:
            colors.append(future_color)
        else:
            colors.append(base_color)

    fig, ax = plt.subplots(figsize=(10, 4.5), dpi=150)
    bars = ax.bar(months, values, color=colors, width=0.68)

    for rect, val in zip(bars, values):
        if val == 0:
            continue
        ax.text(
            rect.get_x() + rect.get_width() / 2,
            rect.get_height(),
            str(val),
            ha="center",
            va="bottom",
            fontsize=9,
            color="#333333",
        )

    title = (
        f"{get_username()} · {report['year']} monthly commits  "
        f"(so far: {report['total_so_far']:,}  ·  "
        f"projected year-end: {report['projected']:,})"
    )
    ax.set_title(title, fontsize=12, fontweight="bold", pad=14)
    ax.set_ylabel("Contributions")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    ax.grid(axis="y", color="#E5E5E5", linewidth=0.8)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    if current_month:
        legend_handles = [
            plt.Rectangle((0, 0), 1, 1, color=base_color),
            plt.Rectangle((0, 0), 1, 1, color=current_color),
        ]
        ax.legend(
            legend_handles,
            ["Completed months", f"{months[current_month - 1]} (partial)"],
            frameon=False,
            fontsize=9,
            loc="upper left",
        )

    fig.tight_layout()
    fig.savefig(CHART_PATH, facecolor="white", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {CHART_PATH}")


def write_stats(report: dict) -> None:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"- **Commits so far ({report['year']}):** {report['total_so_far']:,} "
        f"over {report['days_elapsed']} days",
        f"- **Daily average:** {report['daily_avg']:.2f} commits/day",
        f"- **Projected {report['year']} year-end total:** "
        f"{report['projected']:,} commits",
        "",
        f"_Last updated: {now}_",
        "",
    ]
    with open(STATS_PATH, "w") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {STATS_PATH}")


def main() -> None:
    year = int(os.environ.get("STATS_YEAR", dt.date.today().year))
    token = get_token()
    login = get_username()
    print(f"fetching {login} contribution calendar for {year} ...")
    days = fetch_calendar(token, login, year)
    report = build_report(days, year)
    render_chart(report)
    write_stats(report)
    print(
        f"done: {report['total_so_far']} so far, "
        f"{report['daily_avg']:.2f}/day, projected {report['projected']}"
    )


if __name__ == "__main__":
    main()
