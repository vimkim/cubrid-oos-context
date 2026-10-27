---
status: accepted
---

# Reject pre-stamp databases at boot with a volume-header storage-format stamp

> **Amends [ADR-0005](0005-defer-oos-history-from-the-11-5-merge.md).** ADR-0005's recreate rule stays; this ADR adds engine enforcement. Disk compatibility stays 11.5.

Accepted with the user on 2026-10-27 for PR #7990 (OOS epic CBRD-26357), answering item 2 of [review 5662427700](https://github.com/CUBRID/cubrid/pull/7990#pullrequestreview-5662427700). ADR-0005 requires recreating pre-release databases when the storage format changes, but nothing enforced it. A database created by `develop` or an earlier 11.5 build has the same disk compatibility level (11.5), so it passed every boot check. Debug builds then failed on page-type asserts; release builds misread it (for example, heap header bytes read as an OOS VFID). The engine now refuses such a database at boot, before it reads or recovers any other page.

## Decision

- **Stamp.** `disk_format()` writes `DISK_STORAGE_FORMAT_REVISION` into every volume it formats. The field is `storage_format` in `DISK_VOLUME_HEADER`; it was `reserved0`, which every earlier 11.x build wrote as 0. The stamp is written once and never updated.
- **Revision.** The revision is 1 (OOS). Bump it when an unreleased change makes existing databases unreadable.
- **Check.** `boot_restart_server` and `xboot_emergency_patch` read the stamp of volume 0 right after mounting it. This is before any other page is read and before double-write-buffer and log recovery. Boot requires equality. Any other value fails with `ER_BO_INCOMPATIBLE_STORAGE_FORMAT` (-1392 at PR head `dcbf09e`; error numbers can shift when `develop` is merged). The message tells the user to unload with the creating build and load into a database created by this build.
- **Exemption.** `deletedb` (`boot_remove_all_volumes`) does not check, so a refused database can still be removed.
- **Page types.** `PAGE_OOS` and `PERF_PAGE_OOS` are appended to the end of their enums, so `develop` page types keep their numbers. Page types are stored on disk: append new types, never insert. A static assert keeps `PERF_PAGE_TYPE` aligned with `PAGE_TYPE`.
- **Scope.** The stamp is not a disk-compatibility level and not a per-database activation state. It gives no upgrade or downgrade path. It does not settle CBRD-26939's future compatibility enforcement, which ADR-0005 leaves to that redesign.

## Considered options

- **Volume-header stamp (chosen).** Volume 0 is the earliest data read, so the old database is not modified before the refusal. Log recreation (`patchdb -r`, restore with a missing active log, `copydb`) rewrites the log header but never the volume header, so it cannot erase the marker. The field was 0 in every 11.x database, so separation is reliable. `db_charset` is a precedent for a creation-time volume-header attribute validated at boot.
- **New `disk_compatibility_level`.** Rejected. It contradicts ADR-0005, which forbids manufacturing another level, and GA 11.5 would carry a level other than 11.5. It was the only two-way option: older engines would also refuse new databases, and restoredb would refuse an old backup before restoring files.
- **`SYSTEM_METADATA_VERSION` bump.** Rejected. Boot checks it only after log recovery, vacuum boot, and catalog reads. Its error tells the user to run `upgradedb`, which cannot change a storage format.
- **Log-header stamp.** Not chosen. Every path that recreates the log header writes the current value and erases the old marker.

## Consequences

1. Boot refuses every database formatted before the stamp: `develop`, QA daily, and earlier OOS-branch databases. Persistent developer, CI, and QA databases (for example a leftover `unittestdb`) must be recreated. This is ADR-0005's recreate policy, now enforced.
2. The check is one-way. Older builds ignore the field and still open stamped databases. ADR-0005 gives pre-release artifacts no downgrade guarantee.
3. restoredb of a pre-stamp backup is refused only after the files are restored, because the backup has the same disk level. Remove the restored files with `deletedb`.
4. Released 11.4 and older databases are still refused first by the existing disk-compatibility check (`ER_LOG_INCOMPATIBLE_DATABASE`, -86; backups `ER_LOG_BKUP_INCOMPATIBLE`, -648), before volume 0 is mounted.

## Evidence

Engine `feature/oos-merge` commits `1e8701b4f` (stamp, check, error, enum order, ctest `test_oos_storage_format_guard`) and `d8ed97f77` (emergency-patch coverage, `diagdb` prints `storage_format`, static asserts), verified on 2026-10-27 at PR head `dcbf09e4f7fd02ff9c8fc6493ec8887fc2919d67`. [Design investigation](../../../../temp/pr7990-review-5662427700/t2-boot-rejection-design.md) at head `4408135c0` (investigation, not the decision record). Dated verification results are in the [implementation observation](../reference/implementation-observations.md#cbrd-26357-storage-format-boot-check).
