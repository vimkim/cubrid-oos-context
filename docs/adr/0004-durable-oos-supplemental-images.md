---
status: accepted
---

# Preserve OOS historical values in supplemental images

Accepted with the user on 2026-09-08 for CBRD-26939. CDC and flashback must reconstruct supported before/after images after vacuum has reclaimed the corresponding OOS value chains. Store complete expanded images in supplemental WAL when the image contains OOS-backed attributes, while preserving ordinary recovery logging and normal OOS reclamation. This accepts additional serialization and WAL volume when supplemental logging is enabled in exchange for keeping historical readers independent of OOS chain lifetime.

## Historical compatibility

Guarantee newly written OOS history once this support is implemented. Return an explicit error for older OOS images that cannot be safely reconstructed; do not silently skip a change or substitute a value. Older non-OOS history is not excluded by this decision. For the initial implementation, reject unresolved legacy OOS images: occupancy and matching payload length cannot prove that a reused slot still holds the historical value. No timestamp-based cutoff mechanism has been selected.

## Write failure and reader compatibility

Accepted in interview round 2 on 2026-09-08: failure to construct or append a required supplemental image fails the originating write through normal rollback handling. A successful commit must not silently omit required CDC/flashback history.

Require upgraded engines and historical-log readers before new-format writes begin. Downgrade after those writes is unsupported. The implementation must identify and enforce a compatibility restriction; a new supplemental subtype alone is insufficient because older readers do not reliably reject it. The concrete guard is under source investigation and is not selected by this ADR yet.

## Database activation

Accepted in interview round 3 on 2026-09-08: support explicit, one-way in-place activation for existing databases enabling durable OOS history. Preserve current data and readable non-OOS history. Upgrade engines and HA/log readers before activation, and durably establish the compatibility restriction before any new-format image is written. Databases that have not activated retain their existing compatibility level; do not apply a global compatibility bump to all ordinary databases.

The existing disk-compatibility startup check is a candidate old-engine guard, but it does not fence independent older HA log readers; coordinated reader rollout remains necessary. The implementation must validate activation, recovery, and backup/restore.

Accepted in interview round 4 on 2026-09-08: initial activation is offline, after a clean database shutdown, followed by restart with upgraded engines/readers. Fresh databases created by the fixed engine use the current format immediately, with no separate activation step. Supplemental logging still controls image emission. Older engines cannot open those fresh databases, including before their first OOS change. Existing databases retain the explicit activation policy above.

## Alternatives

Retaining OOS chains for historical readers would require a durable retention horizon covering delayed or disconnected consumers and flashback, with corresponding space-growth and recovery obligations. A hybrid would require both lifetime protocols and transitions between them. Prefer durable supplemental images for this implementation.

## Scope and status

Keep `bug_bts_4633` as a separate diagnosis within the overall PR #6864 success objective. Its observed MVCC undo-read crash is not attributed to CDC by this decision. Retain `cbrd_27075` as CDC regression coverage alongside the currently failing `cbrd_27064`.

This ADR records accepted behavior, not a completed implementation or final specification. The decision frontier is closed after Q1–Q9; the user confirmed proceeding with the accepted contract on 2026-09-08. Encoding, publication ordering, compatibility enforcement details, and verification belong in the implementation specification.

Evidence: [diagnosis and experiments](../../../my-cubrid-docs/cbrd-26939/2940b1c_codex/diagnosis-and-design.md), engine `2940b1cfbc3c2d4d0fac3f9244a960350debd380`. The reduced DELETE workload fails with vacuum enabled, passes with vacuum disabled, and fails after vacuum is restored.
