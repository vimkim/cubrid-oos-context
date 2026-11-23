#!/usr/bin/env python3
"""Check whether cubrid-oos-context Spec/ADRs are in sync with the JIRA manifest."""

from __future__ import annotations

import sys
from jira_sync_lib import MANIFEST_PATH, detect_drifts, load_manifest


def main() -> int:
    """Exit 0 when manifest matches all Spec/ADR files; exit 1 on drift or errors."""
    if not MANIFEST_PATH.is_file():
        print(f"ERROR: manifest not found: {MANIFEST_PATH}", file=sys.stderr)
        return 1

    manifest = load_manifest(MANIFEST_PATH)
    drifts, errors = detect_drifts(manifest)
    hub_key = manifest.get("hub_issue", {}).get("key", "UNKNOWN")

    if errors:
        print("Structural errors detected:")
        for err in errors:
            print(f"  - {err}")

    if drifts:
        print(f"JIRA sync drift detected for {hub_key}:")
        for item in drifts:
            joined = "; ".join(item.reasons)
            print(f"  - {item.target_id} ({item.ko_file}): {joined}")
        print("Next step: run `python3 scripts/render-jira-sync.py --drifted`")

    if errors or drifts:
        return 1

    print(
        f"OK: {len(manifest.get('adrs', []))} ADRs and hub description match "
        f"{hub_key} manifest (commit {manifest.get('hub_issue', {}).get('synced_commit')})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
