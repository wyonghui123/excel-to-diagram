#!/usr/bin/env python
"""
bug_triage.py v1.0 (2026-06-19)
Bug triage tool: classify bug severity + recommend workflow

Usage:
    python bug_triage.py --interactive
    python bug_triage.py --description "cascade delete deletes wrong records" --files "model/user.py,model/order.py" --affected-users "all"
    python bug_triage.py --list  # List active bugs

Severity classification:
    P1 Critical: service down / data loss / security
    P2 High: main flow blocked / data corruption
    P3 Medium: edge case issue
    P4 Low: UI/UX minor

Workflow:
    P1: Immediate hotfix (5 steps, 15-60 min)
    P2: Parallel hotfix (3 steps, 1 hour)
    P3: Backlog (after F1 done)
    P4: Backlog (next sprint)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Constants
COORD_DIR = Path(r"d:\filework\.coord")
BUGS_FILE = COORD_DIR / "bugs.json"

# Severity definitions
SEVERITY_DEFINITIONS = {
    "P1": {
        "name": "Critical",
        "description": "Service down / data loss / security issue",
        "response_time": "< 15 minutes",
        "workflow": "immediate_hotfix",
        "requires_approval": True,
    },
    "P2": {
        "name": "High",
        "description": "Main flow blocked / data corruption",
        "response_time": "< 1 hour",
        "workflow": "parallel_hotfix",
        "requires_approval": True,
    },
    "P3": {
        "name": "Medium",
        "description": "Edge case issue",
        "response_time": "< 1 day",
        "workflow": "backlog",
        "requires_approval": False,
    },
    "P4": {
        "name": "Low",
        "description": "UI/UX minor",
        "response_time": "< 1 week",
        "workflow": "backlog",
        "requires_approval": False,
    },
}

# Triage questions
TRIAGE_QUESTIONS = [
    ("service_crashes", "Does the service crash? (Y/N)"),
    ("data_loss", "Does it cause data loss or corruption? (Y/N)"),
    ("security", "Is it a security issue? (Y/N)"),
    ("main_flow_blocked", "Does it block the main user flow? (Y/N)"),
    ("edge_case_only", "Does it only happen in edge cases? (Y/N)"),
]


def load_bugs():
    """Load bugs.json"""
    if not BUGS_FILE.exists():
        return {"active": [], "resolved": []}
    try:
        with open(BUGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading bugs.json: {e}", file=sys.stderr)
        return {"active": [], "resolved": []}


def save_bugs(bugs):
    """Save bugs.json"""
    COORD_DIR.mkdir(parents=True, exist_ok=True)
    with open(BUGS_FILE, "w", encoding="utf-8") as f:
        json.dump(bugs, f, indent=2, ensure_ascii=False)


def classify_bug(answers):
    """
    Classify bug based on triage answers.

    answers: dict like {
        "service_crashes": True/False,
        "data_loss": True/False,
        "security": True/False,
        "main_flow_blocked": True/False,
        "edge_case_only": True/False,
    }

    Returns: severity (P1/P2/P3/P4)
    """
    if answers.get("service_crashes") or answers.get("data_loss") or answers.get("security"):
        return "P1"
    if answers.get("main_flow_blocked"):
        return "P2"
    if answers.get("edge_case_only"):
        return "P3"
    return "P4"


def recommend_workflow(severity):
    """Recommend workflow based on severity"""
    workflows = {
        "P1": [
            "1. cd F1-worktree; git stash push -u -m 'F1-WIP'",
            r"2. cd main-repo; git worktree add -b hotfix/bug-X ..\hotfix-bug-X-worktree main",
            "3. cd hotfix-bug-X; cp spec_template.md spec.md; fix + test + commit",
            "4. cd main-repo; git merge --no-ff --autostash hotfix/bug-X",
            "5. cd F1-worktree; git rebase main; git stash pop",
        ],
        "P2": [
            r"1. cd main-repo; git worktree add -b hotfix/bug-X ..\hotfix-bug-X-worktree main",
            "2. cd hotfix-bug-X; cp spec_template.md spec.md; fix + test + commit (PARALLEL with F1)",
            "3. After F1 done: cd F1-worktree; git rebase main",
        ],
        "P3": [
            "1. Update .coord/bugs.json (add to P3-active list)",
            "2. Continue F1 work",
            "3. After F1 merged: address P3 bug",
        ],
        "P4": [
            "1. Update .coord/bugs.json (add to P4-active list)",
            "2. Continue F1 work",
            "3. Address in next sprint",
        ],
    }
    return workflows.get(severity, [])


def add_bug(severity, description, files, affected_users=""):
    """Add bug to bugs.json"""
    bugs = load_bugs()
    bug_entry = {
        "id": f"BUG-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "severity": severity,
        "severity_name": SEVERITY_DEFINITIONS[severity]["name"],
        "description": description,
        "files": files.split(",") if files else [],
        "affected_users": affected_users,
        "status": "active",
        "created_at": datetime.now().isoformat(),
        "workflow": SEVERITY_DEFINITIONS[severity]["workflow"],
        "requires_approval": SEVERITY_DEFINITIONS[severity]["requires_approval"],
    }
    if "active" not in bugs:
        bugs["active"] = []
    bugs["active"].append(bug_entry)
    save_bugs(bugs)
    return bug_entry


def list_bugs(severity=None):
    """List active bugs, optionally filtered by severity"""
    bugs = load_bugs()
    active = bugs.get("active", [])
    if severity:
        active = [b for b in active if b["severity"] == severity]
    return active


def print_bug(bug):
    """Pretty print bug"""
    print(f"[{bug['severity']}] {bug['id']}: {bug['description']}")
    print(f"  Status: {bug['status']}")
    print(f"  Files: {', '.join(bug.get('files', []))}")
    print(f"  Workflow: {bug['workflow']}")
    print(f"  Requires approval: {bug.get('requires_approval', False)}")
    print(f"  Created: {bug['created_at']}")
    print()


def interactive_mode():
    """Interactive triage mode"""
    print("=" * 60)
    print("BUG TRIAGE v1.0")
    print("=" * 60)
    print()

    # Description
    description = input("Bug description: ").strip()
    if not description:
        print("Error: description required")
        sys.exit(1)

    files = input("Affected files (comma-separated, or empty): ").strip()
    affected_users = input("Affected users (or empty): ").strip()

    print()
    print("Answer Y/N to triage questions:")
    answers = {}
    for key, question in TRIAGE_QUESTIONS:
        while True:
            ans = input(f"  {question}: ").strip().upper()
            if ans in ("Y", "N"):
                answers[key] = (ans == "Y")
                break
            print("    Please answer Y or N")

    severity = classify_bug(answers)
    sev_def = SEVERITY_DEFINITIONS[severity]

    print()
    print("=" * 60)
    print(f"CLASSIFICATION: {severity} - {sev_def['name']}")
    print(f"Description: {sev_def['description']}")
    print(f"Response time: {sev_def['response_time']}")
    print(f"Workflow: {sev_def['workflow']}")
    print(f"Requires approval: {sev_def['requires_approval']}")
    print()

    workflow = recommend_workflow(severity)
    print("RECOMMENDED WORKFLOW:")
    for step in workflow:
        print(f"  {step}")
    print()

    # Add to bugs.json
    bug = add_bug(severity, description, files, affected_users)
    print(f"BUG ADDED: {bug['id']}")
    print(f"Saved to: {BUGS_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Bug Triage Tool v1.0")
    parser.add_argument("--interactive", action="store_true", help="Interactive triage mode")
    parser.add_argument("--description", help="Bug description")
    parser.add_argument("--files", help="Affected files (comma-separated)")
    parser.add_argument("--affected-users", default="", help="Affected users")
    parser.add_argument("--severity", choices=["P1", "P2", "P3", "P4"], help="Manual severity")
    parser.add_argument("--list", action="store_true", help="List active bugs")
    parser.add_argument("--list-p1", action="store_true", help="List P1 bugs only")
    parser.add_argument("--list-p2", action="store_true", help="List P2 bugs only")
    parser.add_argument("--workflow", choices=["P1", "P2", "P3", "P4"], help="Show workflow for severity")

    args = parser.parse_args()

    if args.interactive:
        interactive_mode()
        return

    if args.workflow:
        severity = args.workflow
        print(f"Workflow for {severity} ({SEVERITY_DEFINITIONS[severity]['name']}):")
        print()
        for step in recommend_workflow(severity):
            print(f"  {step}")
        return

    if args.list:
        bugs = list_bugs()
        if not bugs:
            print("No active bugs")
        else:
            print(f"Active bugs ({len(bugs)}):")
            for bug in bugs:
                print_bug(bug)
        return

    if args.list_p1:
        bugs = list_bugs("P1")
        print(f"P1 Critical bugs ({len(bugs)}):")
        for bug in bugs:
            print_bug(bug)
        return

    if args.list_p2:
        bugs = list_bugs("P2")
        print(f"P2 High bugs ({len(bugs)}):")
        for bug in bugs:
            print_bug(bug)
        return

    if args.description and args.severity and args.files is not None:
        bug = add_bug(args.severity, args.description, args.files, args.affected_users)
        print(f"BUG ADDED: {bug['id']}")
        print(f"Severity: {bug['severity']} ({bug['severity_name']})")
        print(f"Files: {bug['files']}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()