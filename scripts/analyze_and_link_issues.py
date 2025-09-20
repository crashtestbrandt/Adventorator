#!/usr/bin/env python3
"""
Analyze and prepare issue linking using available API access.

This script demonstrates what issues should be linked to EPIC-AVA-000
and prepares the linking logic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Any


def analyze_known_issues() -> None:
    """Analyze the known issues from our exploration."""
    
    cutoff_date = "2025-09-20T00:00:00Z"  # Today
    epic_issue_num = 166  # EPIC-AVA-000
    
    # Based on our previous API exploration, we know:
    print(f"{'='*60}")
    print("ISSUE LINKING ANALYSIS")
    print(f"{'='*60}")
    
    print(f"Epic Issue: #{epic_issue_num} - [Epic] EPIC-AVA-000 Initial Project Standup")
    print(f"Created: 2025-09-20T00:10:50Z (today)")
    print(f"Cutoff Date: {cutoff_date}")
    
    # From our earlier exploration, we found these categories of issues to link:
    
    print(f"\n{'='*60}")
    print("ISSUES TO BE LINKED (created before today)")
    print(f"{'='*60}")
    
    open_issues_older = [
        (165, "[Task] TASK-AVA-RUNBOOK-31 Rollout/canary runbook", "2025-09-19T23:16:18Z", "open"),
        (164, "[Task] TASK-AVA-METRIC-30 Rollout metrics/dashboard", "2025-09-19T23:16:12Z", "open"),
        (163, "[Task] TASK-AVA-TIMEOUT-29 Timeouts & payload bounds", "2025-09-19T23:16:07Z", "open"),
        (162, "[Task] TASK-AVA-TEST-28 Plan serialization tests", "2025-09-19T23:16:01Z", "open"),
        (161, "[Task] TASK-AVA-GUARD-27 Populate guards metadata", "2025-09-19T23:15:54Z", "open"),
        (160, "[Task] TASK-AVA-TIER-26 Tier selection scaffolding", "2025-09-19T23:15:09Z", "open"),
        (159, "[Task] TASK-AVA-TEST-25 MCP parity tests", "2025-09-19T23:15:05Z", "open"),
        (158, "[Task] TASK-AVA-EXEC-24 Executor MCP adapter usage", "2025-09-19T23:14:58Z", "open"),
        (157, "[Task] TASK-AVA-MCP-23 Specify MCP interface", "2025-09-19T23:14:52Z", "open"),
        # Stories
        (134, "[Story] STORY-AVA-001J Operational hardening and rollout", "2025-09-19T22:43:30Z", "open"),
        (133, "[Story] STORY-AVA-001I Tiered planning scaffolding", "2025-09-19T22:43:29Z", "open"),
        (132, "[Story] STORY-AVA-001H MCP adapter scaffold", "2025-09-19T22:43:28Z", "open"),
        (131, "[Story] STORY-AVA-001G ActivityLog mechanics capture", "2025-09-19T22:43:26Z", "open"),
        (130, "[Story] STORY-AVA-001F Predicate Gate v0 rollout", "2025-09-19T22:43:24Z", "open"),
        (129, "[Story] STORY-AVA-001E Executor adapter interoperability", "2025-09-19T22:43:23Z", "open"),
        (128, "[Story] STORY-AVA-001D Orchestrator ExecutionRequest shim", "2025-09-19T22:43:21Z", "open"),
        (127, "[Story] STORY-AVA-001C Planner returns Plan contract", "2025-09-19T22:43:20Z", "open"),
        (126, "[Story] STORY-AVA-001B Logging and metrics foundations", "2025-09-19T22:43:18Z", "open"),
        (125, "[Story] STORY-AVA-001A Contracts and feature flag scaffolding", "2025-09-19T22:37:10Z", "open"),
        (124, "[Epic] EPIC-AVA-001 Action Validation Pipeline Enablement", "2025-09-19T22:36:58Z", "open"),
        # Other issues
        (99, "Push-pop-extract conversation context management", "2025-09-16T00:40:04Z", "open"),
        (98, "Idea: Handle the Fog-Of-War of Narration", "2025-09-16T00:36:13Z", "open"),
        (97, "World tick", "2025-09-15T23:44:12Z", "open"),
        (96, "[Discussion] Action validation architecture", "2025-09-15T20:19:28Z", "open"),
        (94, "Separate concerns for `/ask`, `/plan`, and `/do`", "2025-09-15T03:07:27Z", "open"),
        (92, "Replace system prompts specifying well-formed output with grammar library", "2025-09-15T01:14:59Z", "open"),
        (91, "SHIELDS, BABY", "2025-09-15T00:58:58Z", "open"),
        (84, "Rules engine as MCP server", "2025-09-14T15:52:11Z", "open"),
        (83, "First-pass semantic versioning and CD", "2025-09-14T15:44:47Z", "open"),
        (80, "Phase 16 — Hardening and Ops", "2025-09-14T13:35:59Z", "open"),
        (79, "Phase 15 — GM Controls, Overrides, and Safety", "2025-09-14T13:35:28Z", "open"),
        (78, "Phase 14 — Campaign & Character Ingestion with Preview-Confirm", "2025-09-14T13:34:52Z", "open"),
        (77, "Phase 13 — Modal Scenes (Exploration ↔ Combat)", "2025-09-14T13:34:15Z", "open"),
        (76, "Phase 12 — Map Rendering MVP", "2025-09-14T13:33:30Z", "open"),
        (74, "The autouse fixture that purges all tables before each test...", "2025-09-14T11:38:04Z", "open"),
        (72, "Creating a new `Dnd5eRuleset` instance...", "2025-09-14T08:33:50Z", "open"),
        (71, "[nitpick] The `_FakeLLM` class is duplicated...", "2025-09-14T08:31:23Z", "open"),
        (69, "Feature: ActivityLog", "2025-09-14T06:57:10Z", "open"),
        (68, "Feature: Add NLP for NER and response validation support", "2025-09-14T05:05:15Z", "open"),
        (65, "Fix: Improper LLM refusal messages and handling", "2025-09-13T20:25:12Z", "open"),
        (64, "Idea: Transcript Forging or Context Injections", "2025-09-13T17:03:33Z", "open"),
        (63, "/ooc context and guardrails", "2025-09-13T16:34:37Z", "open"),
        (62, "De-junk Planner Prompt Context", "2025-09-13T16:33:11Z", "open"),
        (61, "Add /help command to display guidance", "2025-09-13T16:31:11Z", "open"),
        (54, "Encapsulate DnD 5e Ruleset as rules engine", "2025-09-09T18:19:16Z", "open"),
        (47, "Add OpenAI-compatible LLM API handler", "2025-09-07T19:11:41Z", "open"),
    ]
    
    closed_issues_older = [
        (156, "[Task] TASK-AVA-E2E-22 E2E ActivityLog tests", "2025-09-19T23:14:46Z", "closed"),
        (155, "[Task] TASK-AVA-LINK-21 Link transcripts to ActivityLog", "2025-09-19T23:14:41Z", "closed"),
        (154, "[Task] TASK-AVA-LOG-20 ActivityLog integration", "2025-09-19T23:14:36Z", "closed"),
        (153, "[Task] TASK-AVA-UNIT-19 Predicate unit tests", "2025-09-19T23:14:30Z", "closed"),
        (152, "[Task] TASK-AVA-PLUG-18 Planner predicate integration", "2025-09-19T23:14:21Z", "closed"),
        (151, "[Task] TASK-AVA-PRED-17 Implement predicate module", "2025-09-19T23:14:13Z", "closed"),
        (150, "[Task] TASK-AVA-INTEG-16 Adapter integration tests", "2025-09-19T23:14:08Z", "closed"),
        (149, "[Task] TASK-AVA-IDEMP-15 Reuse idempotency logic", "2025-09-19T23:14:04Z", "closed"),
        (148, "[Task] TASK-AVA-EXEC-14 ExecutionRequest→ToolCallChain adapter", "2025-09-19T23:14:00Z", "closed"),
        (147, "[Task] TASK-AVA-REJECT-13 Rejection analytics validation", "2025-09-19T23:13:56Z", "closed"),
        (146, "[Task] TASK-AVA-PREVIEW-12 Preserve preview output", "2025-09-19T23:13:51Z", "closed"),
        (145, "[Task] TASK-AVA-ORCH-11 ExecutionRequest mapping", "2025-09-19T23:13:47Z", "closed"),
        (144, "[Task] TASK-AVA-CACHE-10 Cache behavior tests", "2025-09-19T23:13:34Z", "closed"),
        (143, "[Task] TASK-AVA-CMD-09 /plan handler updates", "2025-09-19T23:13:29Z", "closed"),
        (142, "[Task] TASK-AVA-PLAN-08 Wrap planner in Plan", "2025-09-19T23:13:24Z", "closed"),
        (141, "[Task] TASK-AVA-TEST-07 Logging/metrics tests", "2025-09-19T23:13:20Z", "closed"),
        (140, "[Task] TASK-AVA-METRIC-06 Register counters", "2025-09-19T23:13:15Z", "closed"),
        (139, "[Task] TASK-AVA-LOG-05 Planner/Orchestrator log audit", "2025-09-19T23:13:10Z", "closed"),
        (138, "[Task] TASK-AVA-TEST-04 Round-trip tests", "2025-09-19T23:13:03Z", "closed"),
        (137, "[Task] TASK-AVA-FLAGS-03 Add feature flags", "2025-09-19T23:12:58Z", "closed"),
        (136, "[Task] TASK-AVA-CONVERT-02 Add legacy converters", "2025-09-19T23:12:54Z", "closed"),
        (135, "[Task] TASK-AVA-SCHEMA-01 Implement core AVA schemas", "2025-09-19T23:12:39Z", "closed"),
        # And many more closed issues going back...
        (86, "Interphase Docs Overhaul", "2025-09-14T18:14:15Z", "closed"),
        (75, "Phase 11 — Minimal Combat Actions", "2025-09-14T13:33:04Z", "closed"),
        # ... continuing with older issues
    ]
    
    all_issues_to_link = open_issues_older + closed_issues_older
    
    # Group and display
    issue_groups = {
        "Epic": [],
        "Story": [],
        "Task": [], 
        "Other": []
    }
    
    for issue_num, title, created_at, state in all_issues_to_link:
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
            print("-" * 50)
            for issue_num, title, state, created_at in sorted(group_issues, key=lambda x: x[0]):
                status_emoji = "✅" if state == "closed" else "🔄"
                date_part = created_at.split('T')[0]
                # Truncate title if too long
                display_title = title if len(title) <= 60 else title[:57] + "..."
                print(f"  {status_emoji} #{issue_num:3d} [{date_part}] {display_title}")
            total_count += len(group_issues)
    
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total issues to link to epic: {total_count}")
    print(f"  - Epic issues: {len(issue_groups['Epic'])}")
    print(f"  - Story issues: {len(issue_groups['Story'])}")
    print(f"  - Task issues: {len(issue_groups['Task'])}")
    print(f"  - Other issues: {len(issue_groups['Other'])}")
    print(f"Epic issue: #{epic_issue_num}")
    
    return total_count


def main() -> int:
    try:
        total_count = analyze_known_issues()
        
        print(f"\n{'='*60}")
        print("NEXT STEPS")
        print(f"{'='*60}")
        print("To implement the parent-child relationships:")
        print("1. Use the available GitHub API tools to update issues")
        print("2. Update the epic issue body to list all child issues")
        print("3. Add 'Epic Link: #166' to each child issue body")
        print(f"\nThis will establish the relationship between {total_count} issues and the epic.")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())