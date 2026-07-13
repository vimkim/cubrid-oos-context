---
status: accepted
---

# BLOB/CLOB locator columns remain OOS-demotable (type-agnostic eligibility)

> _History: an earlier same-day draft of this ADR recorded the opposite decision (exclude LOBs), proposed while root-causing the `bug_xdbms3693` crash. It was reversed on 2026-07-02 — before any merge — once the crash was fully attributed to the stub-writer bounds bug and the LOB-copy semantics of the OOS path were verified. This file records the accepted decision._

## Context & Decision

A BLOB/CLOB column's in-row value is a `DB_ELO` **locator** (`dbtype_def.h:1031`, a path string, ~88B in practice) pointing into external LOB storage (`es.c`) — the payload is already out-of-row. While diagnosing `bug_xdbms3693` (50 BLOB + 50 CLOB columns crashed the OOS stub writer), excluding LOB types from OOS demotion was considered, on the theory that demoting an already-external reference is redundant indirection.

**Decision:** BLOB/CLOB columns **stay OOS-eligible** under the ordinary rule (`is_variable && column_size > OR_OOS_INLINE_SIZE`). OOS demotion is **type-agnostic**: it moves a column's serialized value bytes out of the record, and a locator is simply this column's value.

**Why:**

1. **The crash had nothing to do with LOB eligibility.** Root cause was the stub writer bounds-checking `buf->ptr` (VOT position) instead of the real write position `*ptr_varvals` — fixed independently, restoring the `S_DOESNT_FIT` → grow-and-retry contract for any sizing drift.
2. **LOB copy semantics are preserved on the OOS path.** `heap_attrinfo_insert_to_oos` → `heap_attrinfo_dbvalue_to_recdes` contains the *same* `db_elo_copy_with_prefix` branch as the inline writer (same `LOB_FLAG_INCLUDE_LOB && HEAP_WRITTEN_ATTRVALUE` gate, same `HEAP_WRITTEN_LOB_ATTRVALUE` re-entry guard), and serializes the post-copy locator into the OOS record. Insert-select LOB copying behaves identically whether the column is demoted or inline.
3. **Exclusion would permanently defeat the record gate for locator-heavy schemas.** With 100 LOB columns (~8.8KB of locators) and exclusion in force, the record stays > 4KB inline forever with zero demotion candidates — exactly the record shape OOS exists to shrink.
4. **The indirection cost is self-limiting.** Largest-first demotion makes ~88B locators the *smallest* candidates; they demote only after every larger column, i.e. only when the record cannot fit otherwise.

## Considered Options

- **Keep LOBs eligible (chosen).** Type-agnostic mechanism, no special cases; copy semantics verified symmetric; the bounds fix alone carries crash-safety.
- **Exclude `DB_TYPE_BLOB`/`DB_TYPE_CLOB` from candidates.** Rejected: adds a type carve-out to a byte-level mechanism; leaves locator-heavy records permanently above the gate; its correctness motivation (suspected skipped LOB copy on the OOS path) was disproven by reading `heap_attrinfo_dbvalue_to_recdes`.
- **Externalize the LOB payload itself through OOS.** Out of scope: LOB storage (`es.c`) is a separate subsystem with its own lifecycle; a different feature, not a demotion-policy question.

## Consequences

1. **Read indirection for demoted locators is 3-hop** (`row → OOS stub → OOS record → locator → LOB file`). Accepted cost; occurs only for records that couldn't fit otherwise (see Why-4).
2. **Vacuum/delete of an OOS record holding a locator deletes only the locator bytes, never the external LOB file** — identical to deleting a heap record with an inline locator. LOB file lifecycle stays owned by the LOB layer.
3. **`bug_xdbms3693` becomes the canonical regression** for the stub-writer bounds fix: its inline-remaining LOB columns regenerate locators mid-write (size drift), and its demoted columns write stubs through the corrected check — exercising the full `S_DOESNT_FIT` retry.
4. **No eligibility change to document in the demotion loop** — the rule stays `is_variable && column_size > OR_OOS_INLINE_SIZE`, no type conditions.
