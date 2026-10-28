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
) -> str:
    title = f"{display_name}'s GitHub Stats"
    stats = [
        (
            "Total Stars Earned:",
            stars,
            "M8 0.25a.75.75 0 01.673.418l1.882 3.815 4.21.612a.75.75 0 01.416 1.279l-3.046 2.97.719 4.192a.75.75 0 01-1.088.791L8 12.347l-3.766 1.98a.75.75 0 01-1.088-.79l.72-4.194L.818 6.374a.75.75 0 01.416-1.28l4.21-.611L7.327.668A.75.75 0 018 .25zm0 2.445L6.615 5.5a.75.75 0 01-.564.41l-3.097.45 2.24 2.184a.75.75 0 01.216.664l-.528 3.084 2.769-1.456a.75.75 0 01.698 0l2.77 1.456-.53-3.084a.75.75 0 01.216-.664l2.24-2.183-3.096-.45a.75.75 0 01-.564-.41L8 2.694v.001z",
        ),
        (
            "Total Commits:",
            commits,
            "M1.643 3.143L.427 1.927A.25.25 0 000 2.104V5.75c0 .138.112.25.25.25h3.646a.75.75 0 00.177-.427L2.715 4.215a6.5 6.5 0 11-1.18 4.458.75.75 0 10-1.493.154 8.001 8.001 0 101.6-5.684zM7.75 4a.75.75 0 01.75.75v2.992l2.028.812a.75.75 0 01-.557 1.392l-2.5-1A.75.75 0 017 8.25v-3.5A.75.75 0 017.75 4z",
        ),
        (
            "Total PRs:",
            pull_requests,
            "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z",
        ),
        (
            "Total Issues:",
            issues,
            "M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8zm9 3a1 1 0 11-2 0 1 1 0 012 0zm-.25-6.25a.75.75 0 00-1.5 0v3.5a.75.75 0 001.5 0v-3.5z",
        ),
        (
            "Contributed to (last year):",
            contributed_repositories,
            "M2 2.5A2.5 2.5 0 014.5 0h8.75a.75.75 0 01.75.75v12.5a.75.75 0 01-.75.75h-2.5a.75.75 0 110-1.5h1.75v-2h-8a1 1 0 00-.714 1.7.75.75 0 01-1.072 1.05A2.495 2.495 0 012 11.5v-9zm10.5-1V9h-8c-.356 0-.694.074-1 .208V2.5a1 1 0 011-1h8zM5 12.25v3.25a.25.25 0 00.4.2l1.45-1.087a.25.25 0 01.3 0L8.6 15.7a.25.25 0 00.4-.2v-3.25a.25.25 0 00-.25-.25h-3.5a.25.25 0 00-.25.25z",
        ),
    ]
    rows = []
    for index, (label, value, icon_path) in enumerate(stats):
        y = 55 + index * 25
        rows.append(
            f'''<g transform="translate(25,{y})">
  <svg class="icon" x="0" y="0" width="16" height="16" viewBox="0 0 16 16"><path fill-rule="evenodd" d="{icon_path}" /></svg>
  <text class="stat label" x="25" y="12.5">{html.escape(label)}</text>
  <text class="stat value" x="219.01" y="12.5">{value:,}</text>
</g>'''
        )
    safe_title = html.escape(title)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" role="img" aria-labelledby="title desc">
  <title id="title">{safe_title}</title>
  <desc id="desc">Rank A+. Total stars earned: {stars}. Public commits: {commits}. Total pull requests: {pull_requests}. Total issues: {issues}. Contributed repositories last year: {contributed_repositories}.</desc>
  <style>
    .bg {{ fill: #1a1b27; stroke: #e4e2e2; }}
    .title {{ fill: #70a5fd; font: 600 18px 'Segoe UI', Ubuntu, sans-serif; }}
    .stat {{ font: 600 14px 'Segoe UI', Ubuntu, sans-serif; fill: #38bdae; }}
    .value {{ font-weight: 700; }}
    .icon {{ fill: #bf91f3; display: block; }}
    .rank-rim {{ fill: none; stroke: #70a5fd; stroke-width: 6; opacity: .2; }}
    .rank-progress {{ fill: none; stroke: #70a5fd; stroke-width: 6; stroke-linecap: round; stroke-dasharray: 250; stroke-dashoffset: 117.29413298583665; opacity: .8; }}
    .rank {{ fill: #38bdae; font: 800 24px 'Segoe UI', Ubuntu, sans-serif; }}
  </style>
  <rect class="bg" x="0.5" y="0.5" width="494" height="194" rx="4.5" />
  <text class="title" x="25" y="35">{safe_title}</text>
  {''.join(rows)}
  <circle class="rank-rim" cx="390" cy="110.5" r="40" />
  <circle class="rank-progress" cx="390" cy="110.5" r="40" transform="rotate(-90 390 110.5)" />
  <text class="rank" x="390" y="111" dominant-baseline="central" text-anchor="middle">A+</text>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=os.getenv("GITHUB_REPOSITORY_OWNER", "fukien"))
    parser.add_argument("--svg", type=Path, default=Path("assets/github-stats-v2.svg"))
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
    )

    args.svg.parent.mkdir(parents=True, exist_ok=True)
    args.svg.write_text(svg, encoding="utf-8")
    readme = args.readme.read_text(encoding="utf-8")
    pattern = re.compile(r"!\[GitHub stats\]\(assets/github-stats-v2\.svg(?:\?v=[^)]+)?\)")
    cache_version = os.getenv("GITHUB_RUN_ID") or now.strftime("%Y%m%d%H%M%S")
    updated_readme, replacements = pattern.subn(
        f"![GitHub stats](assets/github-stats-v2.svg?v={cache_version})",
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
