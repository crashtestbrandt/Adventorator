#!/usr/bin/env python3
"""
Builds docs/implementation_plan.md from GitHub issues titled "Phase N".

Usage:
  REPO_SLUG=owner/repo GITHUB_TOKEN=... scripts/build_implementation_plan.py

Defaults:
  REPO_SLUG defaults to "crashtestbrandt/Adventorator".
  GITHUB_TOKEN optional (higher rate limits, access to private repos).
"""
from __future__ import annotations

import os
import re
import sys
import textwrap
from typing import Any, Dict, List

import json
import urllib.request


PHASE_TITLE_RE = re.compile(r"^Phase\s*(\d+)\b", re.IGNORECASE)


def gh_request(url: str, token: str | None) -> Any:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "Adventorator-Plan-Builder")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def fetch_all_issues(repo: str, token: str | None) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    page = 1
    per_page = 100
    while True:
        url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page={per_page}&page={page}"
        batch = gh_request(url, token)
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return issues


def filter_phase_issues(issues: List[Dict[str, Any]]):
    phases = []
    for it in issues:
        title = it.get("title", "")
        m = PHASE_TITLE_RE.match(title)
        if not m:
            continue
        # Skip PRs (the /issues API returns PRs too)
        if "pull_request" in it:
            continue
        num = int(m.group(1))
        phases.append((num, it))
    phases.sort(key=lambda x: x[0])
    return phases


def extract_status(it: Dict[str, Any]) -> str:
    state = it.get("state", "open")
    if state == "closed":
        return "closed"
    return "open"


def build_section(num: int, it: Dict[str, Any]) -> str:
    title = it.get("title", "")
    number = it.get("number")
    html_url = it.get("html_url", "")
    body = it.get("body") or ""
    status = extract_status(it)
    header = f"## {title} ([#{number}]({html_url})) — status: {status}\n\n"
    return header + body.strip() + "\n\n---\n\n"


def main() -> int:
    # Normalize env vars: treat empty strings as None
    repo = os.environ.get("REPO_SLUG") or "crashtestbrandt/Adventorator"
    token = os.environ.get("GITHUB_TOKEN") or None
    try:
        issues = fetch_all_issues(repo, token)
    except Exception as e:
        print(f"Error fetching issues from {repo}: {e}", file=sys.stderr)
        return 2

    phases = filter_phase_issues(issues)
    if not phases:
        print("No Phase issues found.", file=sys.stderr)
        return 1

    doc = [
        "# Implementation Plan — Phase Descriptions\n",
        "\n",
        "This document aggregates the “Phase N” issues from GitHub with their full descriptions for easy reference. Each section links back to the original issue.\n",
        "\n",
    ]

    for num, it in phases:
        doc.append(build_section(num, it))

    doc.append(
        textwrap.dedent(
            """
            Notes
            - This file is generated from GitHub issues to keep the implementation plan close to source. Update the issues to refresh content.
            """
        ).lstrip()
    )

    out_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "docs",
        "implementation",
        "implementation_plan.md")
    out_path = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(doc))

    print(f"Wrote {out_path} with {len(phases)} Phase sections.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
