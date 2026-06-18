---
status: accepted
---

# OOS pages use a non-numerable file enumerated by a sector-bitmap scan

## Context & Decision

`FILE_OOS` is currently created with `is_numerable=true` (`oos_file.cpp:924-925`) — making it the **only always-permanent file type in CUBRID that is numerable** (heap, btree, etc. are all non-numerable; extendible hash is numerable but `SOMETIMES_TEMP` and uses `find_nth` only as a directory-addressing primitive, never with page-dealloc churn). Once per-page OOS deallocation is wired to vacuum (decision A — it *will* be), OOS enters a regime CUBRID has never validated: **numerable + permanent + page-dealloc churn**, which drives `file_numerable_find_nth` into its mark-delete-skipping slow path (per-call O(n), sync worst case O(max_iterations·n)).

**Decision:** migrate `FILE_OOS` to a **non-numerable** permanent file and replace the `file_numerable_find_nth` loop in `oos_stats_sync_bestspace` with a **sector-bitmap walk** via `file_get_all_data_sectors`. Do this **before** `oos_remove_page` gets vacuum callers — migrating is strictly easier while no live dealloc path exists to preserve.

**Why:** the partial/full sector bitmap is the engine's most fundamental, always-maintained file metadata; it makes page dealloc free (a single bit-clear that `file_dealloc` already logs), needs **zero** per-page format and **zero** per-alloc WAL, and matches OOS's actual need — unordered free-space sampling with VPID-based resume (which also resolves the existing `full_search_vpid` TODO at `oos_file.cpp:671-675`).

## Considered Options

- **Status quo — numerable + `find_nth`.** Rejected: only always-permanent numerable file in CUBRID; mark-delete-on-permanent-with-churn is unvalidated; sync slow-path is O(max_iterations·n) once mark-delete accumulates; the `find_nth_last` speed cache is gated to temp files (`FILE_CACHE_LAST_FIND_NTH`, `file_manager.c:181-183`) so permanent OOS can never use it; and `FILE_TYPE_CAN_BE_NUMERABLE` doesn't even list `FILE_OOS`.
- **Heap-style doubly-linked `next_vpid` page chain.** Rejected despite being the *most* validated permanent model (heap does permanent + bestspace + dealloc, `heap_file.c:4684`/`:4984`): it would add a per-page chain record to every OOS page and a **2× `RVHF_CHAIN` WAL + ordered double-neighbor latch splice on every page dealloc** (`heap_file.c:4628-4684`) — *heavier* than the mark-delete path we are trying to escape, defeating the motivation under churn.
- **Sector-bitmap walk (chosen).** Cheapest under churn, no per-page machinery, rides bulletproof metadata. Cost: OOS is the first *permanent bestspace* to enumerate via the bitmap, and snapshot staleness must be handled (see Consequences).

## Consequences

1. **Sync enumeration MUST fix sampled pages with `OLD_PAGE_MAYBE_DEALLOCATED` and skip `ER_PB_BAD_PAGEID`** (today: plain `OLD_PAGE` + conditional latch, `oos_file.cpp:704`). Reason: `file_get_all_data_sectors` returns a **frozen private-memory snapshot** of the bitmap (`file_manager.c:12611-12612`), and decision A allows concurrent vacuum dealloc *during the entire walk*. `pgbuf_fix` is the only live re-validation point, so it must tolerate "already freed." Plain `OLD_PAGE` would `assert(false)`/`ER_ERROR` on that legitimate, guaranteed-to-occur race (`page_buffer.c:2358-2377`).
2. **Scope the tolerance to the read-only hint path only.** The actual insert/write path stays on plain `OLD_PAGE` so its dead-page tripwire stays armed — targeting a deallocated page at *insert* time is a real bug, not a benign race. Precedent: `px_scan_input_handler_heap` uses `OLD_PAGE_MAYBE_DEALLOCATED` read-only against live, concurrently-vacuumed heaps.
3. **Add an OOS counter** ("sync skipped a deallocated page") to keep the now-swallowed races observable — `MAYBE_DEALLOCATED` trades an ERROR-severity tripwire for a WARNING + silent skip, so the only way to keep enumeration anomalies visible is to count them.
4. **Eliminated:** per-alloc user-page-table append + WAL, mark-delete logical undo (`RVFL_USER_PAGE_MARK_DELETE`), the header user-page-table carve-out, and the `FILE_TYPE_CAN_BE_NUMERABLE` vs OOS inconsistency.
5. **Given up:** `file_numerable_truncate` (currently unused by OOS) and deterministic nth-page ordering (unused by OOS bestspace). The `scan_all=true` / O(n²) concern is moot — it was only ever reachable from the unit-test bridge.
