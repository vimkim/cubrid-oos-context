#!/usr/bin/env python3
"""Validate Korean JIRA sync payloads and print dry-run cubrid-jira commands."""

from __future__ import annotations

import argparse
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from jira_sync_lib import REPO_ROOT, detect_drifts, load_manifest

HYGIENE_PATTERNS = [
    re.compile(r"/home/[A-Za-z0-9_.-]+"),
    re.compile(r"/Users/[A-Za-z0-9_.-]+"),
    re.compile(r"dev2\.baboon-rudd\.ts\.net", re.IGNORECASE),
    re.compile(r"\bWork[0-9]{3,}\b"),
    re.compile(r"\bjust\s+\w+"),
    re.compile(r"\.\./\.\./\.\./my-cubrid-"),
    re.compile(r"\.\./\.\./\.\./\.\./temp/"),
]


def validate_payload(path: Path, run_lint: bool = True) -> list[str]:
    """Validate BMP-only text, public hygiene, and optional cubrid-jira lint."""
    problems: list[str] = []
    if not path.is_file():
        return [f"missing file: {path}"]

    text = path.read_text(encoding="utf-8")
    non_bmp = [(idx, hex(ord(ch))) for idx, ch in enumerate(text) if ord(ch) > 0xFFFF]
    if non_bmp:
        problems.append(f"non-BMP characters found: {non_bmp[:3]}")

    for line_no, line in enumerate(text.splitlines(), start=1):
        for pat in HYGIENE_PATTERNS:
            if pat.search(line):
                problems.append(f"public-hygiene match at {path.name}:{line_no} ({pat.pattern})")

    if run_lint and shutil.which("cubrid-jira"):
        proc = subprocess.run(
            ["cubrid-jira", "lint", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout).strip()
            problems.append(f"cubrid-jira lint failed: {detail}")

    return problems


def build_command(hub_key: str, target_id: str, ko_rel: str, comment_id: str | None) -> list[str]:
    """Build a dry-run cubrid-jira command (never includes --yes)."""
    ko_path = str(REPO_ROOT / ko_rel)
    if target_id == "HUB":
        return [
            "cubrid-jira",
            "update",
            hub_key,
            "--description-file",
            ko_path,
            "--from",
            "markdown",
            "--output",
            "json",
        ]
    if comment_id:
        return [
            "cubrid-jira",
            "comment-update",
            hub_key,
            "--id",
            str(comment_id),
            "--body-file",
            ko_path,
            "--from",
            "markdown",
            "--output",
            "json",
        ]
    return [
        "cubrid-jira",
        "comment",
        hub_key,
        "--body-file",
        ko_path,
        "--from",
        "markdown",
        "--output",
        "json",
    ]


def select_targets(
    manifest: dict[str, Any], mode: str, only_ids: list[str]
) -> tuple[list[tuple[str, str, str | None]], list[str]]:
    """Select (target_id, ko_file, comment_id) tuples to validate and render."""
    drifts, errors = detect_drifts(manifest)
    if mode == "only":
        wanted = set(only_ids)
        targets: list[tuple[str, str, str | None]] = []
        if "HUB" in wanted:
            targets.append(("HUB", manifest["hub_description"]["ko_file"], None))
        for entry in manifest.get("adrs", []):
            if entry["id"] in wanted:
                targets.append((entry["id"], entry["ko_file"], entry.get("comment_id")))
        missing = sorted(wanted - {t[0] for t in targets})
        if missing:
            errors.append(f"Unknown target ID(s): {', '.join(missing)}")
        return targets, errors

    if mode == "all":
        targets = [("HUB", manifest["hub_description"]["ko_file"], None)]
        for entry in manifest.get("adrs", []):
            targets.append((entry["id"], entry["ko_file"], entry.get("comment_id")))
        return targets, errors

    return [(d.target_id, d.ko_file, d.comment_id) for d in drifts], errors


def main() -> int:
    """Validate selected payloads and print dry-run cubrid-jira commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--drifted", action="store_true", help="Render drifted items only (default)")
    group.add_argument("--all", action="store_true", help="Render hub and all ADRs")
    group.add_argument("--only", nargs="+", metavar="ID", help="Render specific IDs (HUB or OOS-ADR-NNNN)")
    parser.add_argument("--no-lint", action="store_true", help="Skip cubrid-jira lint")
    args = parser.parse_args()

    mode = "all" if args.all else ("only" if args.only else "drifted")
    manifest = load_manifest()
    hub_key = manifest["hub_issue"]["key"]
    targets, errors = select_targets(manifest, mode, args.only or [])

    if errors:
        for err in errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return 1

    if not targets:
        print(f"No sync drift detected for {hub_key}. Nothing to render.")
        return 0

    all_problems: list[str] = []
    commands: list[tuple[str, list[str]]] = []
    for target_id, ko_rel, comment_id in targets:
        problems = validate_payload(REPO_ROOT / ko_rel, run_lint=not args.no_lint)
        if problems:
            all_problems.extend(f"{target_id}: {p}" for p in problems)
        else:
            commands.append((target_id, build_command(hub_key, target_id, ko_rel, comment_id)))

    if all_problems:
        for prob in all_problems:
            print(f"ERROR: {prob}", file=sys.stderr)
        return 1

    print(f"# Validated {len(commands)} target(s) for {hub_key} (dry-run only; add --yes after approval):")
    for target_id, cmd in commands:
        print(f"# [{target_id}]")
        print(" ".join(shlex.quote(part) for part in cmd))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
