#!/usr/bin/env python
"""Update Traceability Log in action-validation-architecture epic doc from GitHub issues.

Requires: gh CLI installed and authenticated.

Usage:
  python scripts/update_action_validation_traceability.py --write

Without --write it prints the prospective table.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path

REPO = "crashtestbrandt/Adventorator"
DEFAULT_EPIC = Path("docs/implementation/epics/action-validation-architecture.md")
TRACE_HEADER = "## Traceability Log"

STORY_KEY_PATTERN = re.compile(r"STORY-AVA-(001[A-J])")
TASK_KEY_PATTERN = re.compile(r"TASK-AVA-[A-Z]+-\d+")

def gh_issues_search(query: str) -> list[dict]:
    out = subprocess.check_output([
        "gh","search","issues",query,
        "--repo",REPO,
        "--json","number,title,state"], text=True)
    return json.loads(out)

def collect_story_and_tasks() -> list[tuple[str,int,list[int]]]:
    story_issues = gh_issues_search("STORY-AVA-001")
    # Map story key -> (issue_number, task_numbers)
    story_map: dict[str, tuple[int, list[int]]] = {}
    for issue in story_issues:
        m = STORY_KEY_PATTERN.search(issue["title"])
        if not m:
            continue
        key = m.group(1)
        story_map[key] = (issue["number"], [])
    task_issues = gh_issues_search("TASK-AVA")
    for t in task_issues:
        title = t["title"]
        # Heuristic: tasks include STORY link in body not fetched here; rely on numeric grouping from comment ranges unnecessary.
        # We'll group tasks by nearest preceding Story letter based on numeric ranges embedded in IDs (e.g., -01..-04 belong to 001A etc.)
        task_id_match = TASK_KEY_PATTERN.search(title)
        if not task_id_match:
            continue
        task_id = task_id_match.group(0)
        # Derive story letter from static mapping dictionary for first pass
        letter_map = {
            'SCHEMA':'001A','CONVERT':'001A','FLAGS':'001A','TEST-04':'001A',
            'LOG-05':'001B','METRIC-06':'001B','TEST-07':'001B',
            'PLAN-08':'001C','CMD-09':'001C','CACHE-10':'001C',
            'ORCH-11':'001D','PREVIEW-12':'001D','REJECT-13':'001D',
            'EXEC-14':'001E','IDEMP-15':'001E','INTEG-16':'001E',
            'PRED-17':'001F','PLUG-18':'001F','UNIT-19':'001F',
            'LOG-20':'001G','LINK-21':'001G','E2E-22':'001G',
            'MCP-23':'001H','EXEC-24':'001H','TEST-25':'001H',
            'TIER-26':'001I','GUARD-27':'001I','TEST-28':'001I',
            'TIMEOUT-29':'001J','METRIC-30':'001J','RUNBOOK-31':'001J',
        }
        key_fragment = task_id.replace('TASK-AVA-','')
        story_key = None
        for frag, story in letter_map.items():
            if frag in key_fragment:
                story_key = story
                break
        if story_key and story_key in story_map:
            story_map[story_key][1].append(t['number'])
    result = []
    for story_key, (issue_num, tasks) in sorted(story_map.items(), key=lambda x: x[0]):
        tasks.sort()
        result.append((story_key, issue_num, tasks))
    return result

# Simple cached API fetch using gh CLI
def gh_issue(number: int) -> dict:
    out = subprocess.check_output(["gh", "issue", "view", str(number), "--json", "number,title,state"], text=True)
    return json.loads(out)

def build_table() -> str:
    rows = []
    epic = gh_issue(124)
    rows.append(f"| Epic Issue | [#124](https://github.com/{REPO}/issues/124) | {epic['title'].replace('[Epic] ','')}. |")
    for story_key, story_issue, task_numbers in collect_story_and_tasks():
        story_issue_url = f"https://github.com/{REPO}/issues/{story_issue}"
        story_title = gh_issue(story_issue)['title'].replace('[Story] ','')
        if task_numbers:
            if len(task_numbers) >= 2 and max(task_numbers) - min(task_numbers) + 1 == len(task_numbers):
                tasks_segment = f"#{min(task_numbers)}-#{max(task_numbers)}"
            else:
                tasks_segment = ", ".join(f"#{n}" for n in task_numbers)
        else:
            tasks_segment = "(no tasks)"
        rows.append(f"| Story {story_key} | [#{story_issue}]({story_issue_url}) | {story_title}. Tasks: {tasks_segment} |")
    header = "| Artifact | Link | Notes |\n| --- | --- | --- |"
    return header + "\n" + "\n".join(rows)

def update_file(epic_doc: Path, table: str) -> None:
    text = epic_doc.read_text()
    pattern = re.compile(r"## Traceability Log\n\n\| Artifact.*?(?:\n\n|\Z)", re.DOTALL)
    replacement = f"{TRACE_HEADER}\n\n{table}\n\n"
    new_text = pattern.sub(replacement, text)
    epic_doc.write_text(new_text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--epic", help="Path to a single epic markdown file", default=str(DEFAULT_EPIC))
    ap.add_argument("--all", action="store_true", help="Update all epic docs under docs/implementation/epics/")
    ap.add_argument("--write", action="store_true", help="Write changes instead of printing table")
    ap.add_argument("--verify", action="store_true", help="Exit non-zero if file(s) out of sync")
    args = ap.parse_args()
    epic_paths: list[Path]
    if args.all:
        epic_paths = sorted(Path("docs/implementation/epics").glob("*.md"))
    else:
        epic_paths = [Path(args.epic)]
    exit_code = 0
    for epic_doc in epic_paths:
        table = build_table()  # currently only AVA-aware; future: parse epic_doc name for filtering
        if args.verify:
            current = epic_doc.read_text()
            if table in current:
                print(f"[OK] {epic_doc}")
            else:
                print(f"[FAIL] {epic_doc} out of sync")
                exit_code = 1
        elif args.write:
            update_file(epic_doc, table)
            print(f"Updated {epic_doc}")
        else:
            print(f"=== {epic_doc} ===\n{table}\n")
    if args.verify and exit_code:
        raise SystemExit(exit_code)

if __name__ == "__main__":
    main()
