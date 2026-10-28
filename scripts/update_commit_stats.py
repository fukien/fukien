#!/usr/bin/env python3
"""Update the profile README with GitHub's yearly commit contribution counts."""

from __future__ import annotations

import argparse
import datetime as dt
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
START_MARKER = "<!-- github-commit-stats:start -->"
END_MARKER = "<!-- github-commit-stats:end -->"
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    createdAt
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
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
            "User-Agent": "fukien-profile-commit-stats",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default=os.getenv("GITHUB_REPOSITORY_OWNER", "fukien"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()

    token = (
        os.getenv("PROFILE_STATS_TOKEN")
        or os.getenv("GITHUB_TOKEN")
        or os.getenv("GH_TOKEN")
    )
    if not token:
        print(
            "Set PROFILE_STATS_TOKEN (recommended), GITHUB_TOKEN, or GH_TOKEN. "
            "The token needs the read:user scope for private contribution counts.",
            file=sys.stderr,
        )
        return 2

    now = dt.datetime.now(dt.timezone.utc)
    current_year = now.year
    first_user = graphql(
        token,
        args.username,
        dt.datetime(current_year, 1, 1, tzinfo=dt.timezone.utc),
        now,
    )
    start_year = dt.datetime.fromisoformat(first_user["createdAt"].replace("Z", "+00:00")).year

    by_year: list[tuple[int, int]] = []
    for year in range(start_year, current_year + 1):
        start = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        end = now if year == current_year else dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
        user = first_user if year == current_year else graphql(token, args.username, start, end)
        count = user["contributionsCollection"]["totalCommitContributions"]
        by_year.append((year, count))

    total = sum(count for _, count in by_year)
    rows = "\n".join(f"| {year} | {count:,} |" for year, count in by_year)
    generated = (
        f"{START_MARKER}\n"
        f"**GitHub-recognized commits (all time):** {total:,} "
        f"(updated {now.date().isoformat()})\n\n"
        "<details><summary>Commits by year</summary>\n\n"
        "| Year | Commit contributions |\n|---:|---:|\n"
        f"{rows}\n\n"
        "</details>\n"
        f"{END_MARKER}"
    )

    readme = args.readme.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL
    )
    updated, replacements = pattern.subn(lambda _: generated, readme, count=1)
    if replacements != 1:
        raise RuntimeError(f"Expected exactly one pair of commit-stat markers in {args.readme}")
    args.readme.write_text(updated, encoding="utf-8")
    print(f"Updated {args.readme} with {total:,} GitHub-recognized commits.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
