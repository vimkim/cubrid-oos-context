"""Shared helpers for checking and rendering OOS Spec/ADR JIRA sync state."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "docs" / "maintenance" / "jira-sync-manifest.json"
ADR_DIR = REPO_ROOT / "docs" / "adr"


@dataclass
class DriftItem:
    """One out-of-sync item between the SoT repository and the JIRA manifest."""

    target_id: str
    kind: str  # "hub" or "adr"
    reasons: list[str]
    ko_file: str
    comment_id: str | None = None


def sha256_file(path: Path) -> str:
    """Return the lowercase hex SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_adr_frontmatter(path: Path) -> dict[str, Any]:
    """Parse minimal YAML frontmatter fields (id, status, last_updated, jira_issues)."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    block = text[4:end]
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        if current_list_key and re.match(r"^\s+-\s+", line):
            item = re.sub(r"^\s+-\s+", "", line).strip().strip("\"'")
            result.setdefault(current_list_key, []).append(item)
            continue
        current_list_key = None
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip().strip("\"'")
            if val == "":
                result[key] = []
                current_list_key = key
            else:
                result[key] = val
    return result


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    """Load the JSON sync manifest."""
    return json.loads(path.read_text(encoding="utf-8"))


def detect_drifts(manifest: dict[str, Any]) -> tuple[list[DriftItem], list[str]]:
    """Compare repository files against the sync manifest.

    Returns (drifts, structural_errors).
    """
    drifts: list[DriftItem] = []
    errors: list[str] = []

    hub = manifest.get("hub_description", {})
    hub_reasons: list[str] = []
    for rel, expected_hash in hub.get("source_sha256", {}).items():
        fp = REPO_ROOT / rel
        if not fp.is_file():
            errors.append(f"Missing hub source file: {rel}")
        elif sha256_file(fp) != expected_hash:
            hub_reasons.append(f"source changed: {rel}")

    hub_ko = hub.get("ko_file", "")
    hub_ko_path = REPO_ROOT / hub_ko
    if not hub_ko_path.is_file():
        errors.append(f"Missing hub Korean file: {hub_ko}")
    elif sha256_file(hub_ko_path) != hub.get("ko_sha256"):
        hub_reasons.append(f"Korean draft changed: {hub_ko}")

    if hub_reasons:
        drifts.append(DriftItem(target_id="HUB", kind="hub", reasons=hub_reasons, ko_file=hub_ko))

    registered_adr_files: set[str] = set()
    for entry in manifest.get("adrs", []):
        adr_id = entry["id"]
        src_rel = entry["source_file"]
        ko_rel = entry["ko_file"]
        registered_adr_files.add(src_rel)
        reasons: list[str] = []

        src_path = REPO_ROOT / src_rel
        if not src_path.is_file():
            errors.append(f"{adr_id}: missing source file {src_rel}")
        else:
            if sha256_file(src_path) != entry.get("source_sha256"):
                reasons.append(f"source changed: {src_rel}")
            fm = parse_adr_frontmatter(src_path)
            for field in ("id", "status", "last_updated"):
                if str(fm.get(field, "")) != str(entry.get(field, "")):
                    reasons.append(
                        f"frontmatter {field}={fm.get(field)!r} != manifest {entry.get(field)!r}"
                    )

        ko_path = REPO_ROOT / ko_rel
        if not ko_path.is_file():
            errors.append(f"{adr_id}: missing Korean file {ko_rel}")
        elif sha256_file(ko_path) != entry.get("ko_sha256"):
            reasons.append(f"Korean draft changed: {ko_rel}")

        if not entry.get("comment_id"):
            reasons.append("missing JIRA comment_id (new ADR not yet posted)")

        if reasons:
            drifts.append(
                DriftItem(
                    target_id=adr_id,
                    kind="adr",
                    reasons=reasons,
                    ko_file=ko_rel,
                    comment_id=entry.get("comment_id"),
                )
            )

    for adr_path in sorted(ADR_DIR.glob("*.md")):
        rel = adr_path.relative_to(REPO_ROOT).as_posix()
        if rel not in registered_adr_files:
            errors.append(f"Unregistered ADR file in docs/adr/: {rel}")

    return drifts, errors
