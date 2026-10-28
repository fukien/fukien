#!/usr/bin/env python3
"""Refresh the public GitHub stats SVG used by the profile README."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import certifi
except ImportError:
    certifi = None


API_URL = "https://api.github.com/graphql"
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    name
    createdAt
    repositories(first: 100, ownerAffiliations: OWNER) {
      nodes {
        isPrivate
        stargazerCount
      }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoriesWithContributedCommits
    }
  }
}
"""


def graphql(token: str, username: str, start: dt.datetime, end: dt.datetime) -> dict:
    payload = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": username,
                "from": start.isoformat().replace("+00:00", "Z"),
                "to": end.isoformat().replace("+00:00", "Z"),
            },
        }
    ).encode()
    request = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "fukien-profile-stats",
        },
        method="POST",
    )
    try:
        options = {"timeout": 30}
        if certifi is not None:
            options["context"] = ssl.create_default_context(cafile=certifi.where())
        with urllib.request.urlopen(request, **options) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        raise RuntimeError(f"GitHub GraphQL request failed ({error.code}): {detail}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach GitHub GraphQL: {error.reason}") from None

    if result.get("errors"):
        messages = "; ".join(item.get("message", "GraphQL error") for item in result["errors"])
        raise RuntimeError(f"GitHub GraphQL returned an error: {messages}")
    user = result.get("data", {}).get("user")
    if user is None:
        raise RuntimeError(f"GitHub user {username!r} was not found or is not accessible")
    return user


def make_svg(
    display_name: str,
    stars: int,
    commits: int,
    pull_requests: int,
    issues: int,
    contributed_repositories: int,
    updated: str,
) -> str:
    title = f"{display_name}'s GitHub Stats"
    stats = [
        ("Total Stars Earned", stars),
        ("Public Commits", commits),
        ("Total Pull Requests", pull_requests),
        ("Total Issues", issues),
        ("Contributed to (last year)", contributed_repositories),
    ]
    rows = []
    for index, (label, value) in enumerate(stats):
        y = 66 + index * 23
        rows.append(
            f'''<g transform="translate(25,{y})">
  <text class="label" x="0" y="0">{label}</text>
  <text class="value" x="250" y="0">{value:,}</text>
</g>'''
        )
    safe_title = html.escape(title)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" role="img" aria-labelledby="title desc">
  <title id="title">{safe_title}</title>
  <desc id="desc">Rank A+. Total stars earned: {stars}. Public commits: {commits}. Total pull requests: {pull_requests}. Total issues: {issues}. Contributed repositories last year: {contributed_repositories}.</desc>
  <style>
    .bg {{ fill: #1a1b27; stroke: #e4e2e2; }}
    .title {{ fill: #70a5fd; font: 600 18px 'Segoe UI', Ubuntu, sans-serif; }}
    .label, .value {{ fill: #38bdae; font: 600 13px 'Segoe UI', Ubuntu, sans-serif; }}
    .value {{ font-weight: 700; }}
    .rank-rim {{ fill: none; stroke: #70a5fd; stroke-width: 6; opacity: .2; }}
    .rank-progress {{ fill: none; stroke: #70a5fd; stroke-width: 6; stroke-linecap: round; stroke-dasharray: 250; stroke-dashoffset: 117.29413298583665; opacity: .8; }}
    .rank {{ fill: #38bdae; font: 800 27px 'Segoe UI', Ubuntu, sans-serif; }}
    .rank-caption {{ fill: #a9b1d6; font: 11px 'Segoe UI', Ubuntu, sans-serif; }}
    .updated {{ fill: #a9b1d6; font: 10px 'Segoe UI', Ubuntu, sans-serif; }}
  </style>
  <rect class="bg" x="0.5" y="0.5" width="494" height="194" rx="4.5" />
  <text class="title" x="25" y="35">{safe_title}</text>
  {''.join(rows)}
  <circle class="rank-rim" cx="420" cy="112" r="40" />
  <circle class="rank-progress" cx="420" cy="112" r="40" transform="rotate(-90 420 112)" />
  <text class="rank" x="420" y="121" text-anchor="middle">A+</text>
  <text class="rank-caption" x="420" y="160" text-anchor="middle">rank</text>
  <text class="updated" x="25" y="188">Public GitHub data · updated {updated}</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=os.getenv("GITHUB_REPOSITORY_OWNER", "fukien"))
    parser.add_argument("--svg", type=Path, default=Path("assets/github-stats.svg"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if not token:
        print("Set GITHUB_TOKEN or GH_TOKEN before running this script.", file=sys.stderr)
        return 2

    now = dt.datetime.now(dt.timezone.utc)
    current_year = now.year
    first_user = graphql(
        token,
        args.username,
        dt.datetime(current_year, 1, 1, tzinfo=dt.timezone.utc),
        now,
    )
    first_year = dt.datetime.fromisoformat(first_user["createdAt"].replace("Z", "+00:00")).year

    totals = {"commits": 0, "pull_requests": 0, "issues": 0}
    previous_year_repositories = 0
    for year in range(first_year, current_year + 1):
        start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        end = now if year == current_year else dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
        user = first_user if year == current_year else graphql(token, args.username, start, end)
        collection = user["contributionsCollection"]
        totals["commits"] += collection["totalCommitContributions"]
        totals["pull_requests"] += collection["totalPullRequestContributions"]
        totals["issues"] += collection["totalIssueContributions"]
        if year == current_year - 1:
            previous_year_repositories = collection["totalRepositoriesWithContributedCommits"]

    stars = sum(
        repo["stargazerCount"]
        for repo in first_user["repositories"]["nodes"]
        if not repo["isPrivate"]
    )
    svg = make_svg(
        display_name=first_user.get("name") or args.username,
        stars=stars,
        commits=totals["commits"],
        pull_requests=totals["pull_requests"],
        issues=totals["issues"],
        contributed_repositories=previous_year_repositories,
        updated=now.date().isoformat(),
    )

    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(svg, encoding="utf-8")
    readme = args.readme.read_text(encoding="utf-8")
    pattern = re.compile(r"!\[GitHub stats\]\(assets/github-stats\.svg(?:\?v=[^)]+)?\)")
    cache_version = os.getenv("GITHUB_RUN_ID") or now.strftime("%Y%m%d%H%M%S")
    updated_readme, replacements = pattern.subn(
        f"![GitHub stats](assets/github-stats.svg?v={cache_version})",
        readme,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError(f"Expected one GitHub stats image reference in {args.readme}")
    args.readme.write_text(updated_readme, encoding="utf-8")
    print(f"Updated public stats card with {totals['commits']:,} commits.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
