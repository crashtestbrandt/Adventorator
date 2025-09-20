#!/usr/bin/env python3
"""
Link all issues older than today to the epic issue EPIC-AVA-000.

This script:
1. Fetches all issues from the repository
2. Filters issues created before today (2025-09-20)
3. Updates the epic issue (#166) body to include links to all older issues
4. Updates each older issue to reference the epic in their body

Usage:
  REPO_SLUG=owner/repo GITHUB_TOKEN=... python scripts/link_issues_to_epic.py
  
Environment Variables:
  REPO_SLUG: Repository slug (default: "crashtestbrandt/Adventorator")
  GITHUB_TOKEN: GitHub token for API access (required for updates)
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List

import json
import urllib.request
import urllib.parse


def gh_request(url: str, token: str, method: str = "GET", data: bytes | None = None) -> Any:
    """Make a GitHub API request with proper authentication."""
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "Adventorator-Issue-Linker")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
        return json.loads(data.decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.reason}", file=sys.stderr)
        if hasattr(e, 'read'):
            error_data = e.read().decode('utf-8')
            print(f"Error details: {error_data}", file=sys.stderr)
        raise


def fetch_all_issues(repo: str, token: str) -> List[Dict[str, Any]]:
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


def filter_older_issues(issues: List[Dict[str, Any]], cutoff_date: str) -> List[Dict[str, Any]]:
    """Filter issues created before the cutoff date."""
    older_issues = []
    epic_issue_num = 166  # EPIC-AVA-000
    
    cutoff_dt = datetime.fromisoformat(cutoff_date.replace('Z', '+00:00'))
    
    for issue in issues:
        # Skip the epic issue itself
        if issue.get("number") == epic_issue_num:
            continue
            
        # Skip pull requests
        if "pull_request" in issue:
            continue
            
        created_at = issue.get("created_at", "")
        if created_at:
            created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            if created_dt < cutoff_dt:
                older_issues.append(issue)
    
    print(f"Found {len(older_issues)} issues older than {cutoff_date}")
    return older_issues


def update_epic_issue_body(repo: str, token: str, epic_issue_num: int, child_issues: List[Dict[str, Any]]) -> None:
    """Update the epic issue body to include links to all child issues."""
    # First, get the current epic issue
    url = f"https://api.github.com/repos/{repo}/issues/{epic_issue_num}"
    epic_issue = gh_request(url, token)
    
    current_body = epic_issue.get("body", "")
    
    # Build the new body with links to child issues
    new_body_lines = [
        "Epic container to hold all early / initial project issues",
        "",
        "## Child Issues",
        ""
    ]
    
    # Group issues by type for better organization
    issue_groups = {
        "Epic": [],
        "Story": [],
        "Task": [], 
        "Other": []
    }
    
    for issue in child_issues:
        title = issue.get("title", "")
        issue_num = issue.get("number")
        html_url = issue.get("html_url", "")
        state = issue.get("state", "open")
        
        # Determine issue type from title
        if title.startswith("[Epic]"):
            issue_groups["Epic"].append((issue_num, title, html_url, state))
        elif title.startswith("[Story]"):
            issue_groups["Story"].append((issue_num, title, html_url, state))
        elif title.startswith("[Task]"):
            issue_groups["Task"].append((issue_num, title, html_url, state))
        else:
            issue_groups["Other"].append((issue_num, title, html_url, state))
    
    # Add each group to the body
    for group_name, group_issues in issue_groups.items():
        if group_issues:
            new_body_lines.append(f"### {group_name}")
            for issue_num, title, html_url, state in sorted(group_issues, key=lambda x: x[0]):
                status_emoji = "✅" if state == "closed" else "🔄"
                new_body_lines.append(f"- {status_emoji} [#{issue_num}]({html_url}) {title}")
            new_body_lines.append("")
    
    new_body_lines.append(f"**Total Child Issues:** {len(child_issues)}")
    
    new_body = "\n".join(new_body_lines)
    
    # Update the epic issue
    update_data = {
        "body": new_body
    }
    
    update_url = f"https://api.github.com/repos/{repo}/issues/{epic_issue_num}"
    print(f"Updating epic issue #{epic_issue_num}...")
    
    response = gh_request(
        update_url,
        token,
        method="PATCH",
        data=json.dumps(update_data).encode("utf-8")
    )
    print(f"Epic issue updated successfully")


def update_child_issue_body(repo: str, token: str, issue: Dict[str, Any], epic_issue_num: int) -> None:
    """Update a child issue to reference the epic."""
    issue_num = issue.get("number")
    current_body = issue.get("body", "") or ""
    
    # Check if epic link already exists
    epic_link_text = f"Epic Link: #{epic_issue_num}"
    if epic_link_text in current_body:
        print(f"Issue #{issue_num} already references epic, skipping")
        return
    
    # Add epic link at the beginning of the body
    if current_body.strip():
        new_body = f"{epic_link_text}\n\n{current_body}"
    else:
        new_body = epic_link_text
    
    # Update the issue
    update_data = {
        "body": new_body
    }
    
    update_url = f"https://api.github.com/repos/{repo}/issues/{issue_num}"
    print(f"Updating issue #{issue_num} to reference epic...")
    
    try:
        response = gh_request(
            update_url,
            token,
            method="PATCH",
            data=json.dumps(update_data).encode("utf-8")
        )
        print(f"Issue #{issue_num} updated successfully")
    except Exception as e:
        print(f"Failed to update issue #{issue_num}: {e}", file=sys.stderr)


def main() -> int:
    # Configuration
    repo = os.environ.get("REPO_SLUG") or "crashtestbrandt/Adventorator"
    token = os.environ.get("GITHUB_TOKEN")
    
    if not token:
        print("Error: GITHUB_TOKEN environment variable is required", file=sys.stderr)
        return 1
    
    cutoff_date = "2025-09-20T00:00:00Z"  # Today
    epic_issue_num = 166  # EPIC-AVA-000
    
    try:
        # Fetch all issues
        issues = fetch_all_issues(repo, token)
        
        # Filter to issues older than today
        older_issues = filter_older_issues(issues, cutoff_date)
        
        if not older_issues:
            print("No issues found older than today")
            return 0
        
        print(f"Found {len(older_issues)} issues to link to epic #{epic_issue_num}")
        
        # Update the epic issue to list all child issues
        update_epic_issue_body(repo, token, epic_issue_num, older_issues)
        
        # Update each child issue to reference the epic
        print("\nUpdating child issues...")
        for i, issue in enumerate(older_issues, 1):
            print(f"Processing issue {i}/{len(older_issues)}: #{issue.get('number')}")
            update_child_issue_body(repo, token, issue, epic_issue_num)
        
        print(f"\nSuccessfully linked {len(older_issues)} issues to epic #{epic_issue_num}")
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())