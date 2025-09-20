#!/usr/bin/env python3
"""
Analyze which issues should be linked to EPIC-AVA-000 (dry-run mode).

This script analyzes all issues and shows what changes would be made
without actually updating anything.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

import json
import urllib.request


def gh_request(url: str, token: str | None = None) -> Any:
    """Make a GitHub API request."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "Adventorator-Issue-Analyzer")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    
    with urllib.request.urlopen(req) as resp:
        data = resp.read()
    return json.loads(data.decode("utf-8"))


def fetch_all_issues(repo: str, token: str | None = None) -> List[Dict[str, Any]]:
    """Fetch all issues from the repository."""
    issues: List[Dict[str, Any]] = []
    page = 1
    per_page = 100
    
    while True:
        url = f"https://api.github.com/repos/{repo}/issues?state=all&per_page={per_page}&page={page}"
        print(f"Fetching issues page {page}...")
        batch = gh_request(url, token)
        if not batch:
            break
        issues.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    
    print(f"Fetched {len(issues)} total issues")
    return issues


def analyze_issues(repo: str, token: str | None = None) -> None:
    """Analyze issues and show what would be linked."""
    cutoff_date = "2025-09-20T00:00:00Z"  # Today
    epic_issue_num = 166  # EPIC-AVA-000
    
    # Fetch all issues
    issues = fetch_all_issues(repo, token)
    
    cutoff_dt = datetime.fromisoformat(cutoff_date.replace('Z', '+00:00'))
    
    older_issues = []
    newer_issues = []
    epic_issue = None
    
    for issue in issues:
        # Skip pull requests
        if "pull_request" in issue:
            continue
            
        issue_num = issue.get("number")
        created_at = issue.get("created_at", "")
        title = issue.get("title", "")
        state = issue.get("state", "")
        
        if issue_num == epic_issue_num:
            epic_issue = issue
            continue
            
        if created_at:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if created_dt < cutoff_dt:
                older_issues.append(issue)
            else:
                newer_issues.append(issue)
    
    print(f"\n{'='*60}")
    print("ANALYSIS RESULTS")
    print(f"{'='*60}")
    
    if epic_issue:
        print(f"Epic Issue: #{epic_issue['number']} - {epic_issue['title']}")
        print(f"Created: {epic_issue['created_at']}")
    else:
        print("Epic issue not found!")
        return
    
    print(f"\nCutoff Date: {cutoff_date}")
    print(f"Issues created before cutoff: {len(older_issues)}")
    print(f"Issues created on/after cutoff: {len(newer_issues)}")
    
    print(f"\n{'='*60}")
    print("ISSUES TO BE LINKED TO EPIC (older than today)")
    print(f"{'='*60}")
    
    # Group by type for better visualization
    issue_groups = {
        "Epic": [],
        "Story": [],
        "Task": [], 
        "Other": []
    }
    
    for issue in older_issues:
        title = issue.get("title", "")
        issue_num = issue.get("number")
        state = issue.get("state", "open")
        created_at = issue.get("created_at", "")
        
        # Determine issue type from title
        if title.startswith("[Epic]"):
            issue_groups["Epic"].append((issue_num, title, state, created_at))
        elif title.startswith("[Story]"):
            issue_groups["Story"].append((issue_num, title, state, created_at))
        elif title.startswith("[Task]"):
            issue_groups["Task"].append((issue_num, title, state, created_at))
        else:
            issue_groups["Other"].append((issue_num, title, state, created_at))
    
    total_count = 0
    for group_name, group_issues in issue_groups.items():
        if group_issues:
            print(f"\n{group_name} Issues ({len(group_issues)}):")
            print("-" * 40)
            for issue_num, title, state, created_at in sorted(group_issues, key=lambda x: x[0]):
                status_emoji = "✅" if state == "closed" else "🔄"
                # Show just the date part for readability
                date_part = created_at.split('T')[0]
                print(f"  {status_emoji} #{issue_num:3d} [{date_part}] {title}")
            total_count += len(group_issues)
    
    print(f"\n{'='*60}")
    print("ISSUES NOT TO BE LINKED (created today or later)")
    print(f"{'='*60}")
    
    if newer_issues:
        for issue in sorted(newer_issues, key=lambda x: x.get("number", 0)):
            issue_num = issue.get("number")
            title = issue.get("title", "")
            state = issue.get("state", "open")
            created_at = issue.get("created_at", "")
            status_emoji = "✅" if state == "closed" else "🔄"
            date_part = created_at.split('T')[0]
            print(f"  {status_emoji} #{issue_num:3d} [{date_part}] {title}")
    else:
        print("  (None)")
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total issues to link to epic: {total_count}")
    print(f"Epic issue: #{epic_issue_num}")
    print(f"Repository: {repo}")
    
    if total_count > 0:
        print(f"\nNext steps:")
        print(f"1. Run the link_issues_to_epic.py script with GITHUB_TOKEN")
        print(f"2. This will update issue #{epic_issue_num} body with links to all {total_count} child issues")
        print(f"3. Each child issue will get 'Epic Link: #{epic_issue_num}' added to its body")


def main() -> int:
    # Configuration
    repo = os.environ.get("REPO_SLUG") or "crashtestbrandt/Adventorator"
    token = os.environ.get("GITHUB_TOKEN")  # Optional for read-only analysis
    
    try:
        analyze_issues(repo, token)
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())