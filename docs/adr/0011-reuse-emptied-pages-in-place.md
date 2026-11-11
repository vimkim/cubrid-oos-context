---
status: proposed
---

# Reuse emptied OOS pages in place instead of deallocating them

> **Amends** [ADR-0009](0009-reclaim-empty-pages-before-growth-not-while-idle.md) decision 3 (keep the vacuum fast path) and [ADR-0010](0010-arm-growth-reclaim-with-emptied-pages.md) decision 3 (check set members with the two-phase reclaim). On acceptance it also amends [OOS-CONTEXT.md](../../OOS-CONTEXT.md) §4: the growth gate and the vacuum fast path bullets. The invariant is unchanged: an OOS file reserves a new sector only when no reusable empty page exists ([ADR-0009](0009-reclaim-empty-pages-before-growth-not-while-idle.md) decision 2).

Proposed on 2026-11-11 for CBRD-27925 (Work878). This is step 2 of the plan in ADR-0010 "Follow-up: in-place reuse". The owner chose reuse-first on 2026-11-06 and sequenced it after ADR-0010 on 2026-11-09.

## Context

With ADR-0010, a growth that finds an empty page in the emptied-page set returns it to the file manager and then takes it back:

- It READ-fixes the page, takes the OOS stats header page WRITE latch, WRITE-fixes the page again, and deallocates it in its own system operation. The header latch is held until that system operation commits.
- The following `file_alloc` takes the same page back in a second system operation and initializes it again.
- The vacuum fast path does the same deallocation for the pages a delete batch emptied, at the end of the batch. It needs a list of emptied pages threaded from `oos_delete` through the vacuum heap code.

Every OOS INSERT takes the same header WRITE latch to look up its page, so a deallocation on the INSERT path makes other INSERTs of the file wait. A deallocation also frees no space: a permanent file returns sectors to the disk only in `file_destroy` (ADR-0009 Context), so the only user of a deallocated OOS page is the next allocation of the same file.

The growth arena (Work829, candidate C) modeled reuse-first: the growth writes into the empty page under the WRITE latch it validated the page with, and the page is never deallocated. It kept the rule and the size bound in all four settings (with and without crashes, with and without writes during a growth), with no system operation per reuse. Three variants failed: no validation under the latch (writes into a deallocated page), late removal from the set (the file grows to the cap), and no reinitialization of a page whose dead slots leave no room (the rule fails).

## Decision

1. A growth that takes a page from the emptied-page set, or finds an empty page in the lap, **writes into it in place**. It does not deallocate the page, and it holds no header-page latch for it. Only `file_destroy` deallocates OOS data pages.
2. The page is taken under a conditional WRITE fix and validated under that latch: the page is `PAGE_OOS`, it belongs to the file, it holds no record, and it has room for the record. Bestspace hint lookups use the same validation. The latch is held until the caller's write, as for a new page. A page found busy stays in the set; a page found non-empty, retyped, or foreign leaves the set under the latch that shows it; a page found deallocated stays in the set (ADR-0010 decision 3).
3. A taken page leaves the set at once, under the latch it is taken with. The insert also drops it under the same latch.
4. An empty page whose dead slots leave no room for the record is reinitialized as a new OOS page and then reused. The reinitialization is logged redo-only. An undo would set the page type back to unknown, and the page would stay allocated without a type, so no growth could take it again. No undo can target an empty OOS page: chunk deletes are redo-only (ADR-0008), and a page with an INSERT still to undo holds that chunk.
5. Growth order, under the file's growth lock: the emptied-page set, the bestspace sync when the header estimates promise free pages, the lap when the file is unknown, the set again after the lap, then `file_alloc`. The lap READ-checks a page before it WRITE-fixes it, so a page held by a reader does not enter the set as busy.
6. A delete that leaves a page empty removes the page's bestspace entry and adds the page to the emptied-page set only. Empty pages reach inserts through the set. The bestspace cache keeps its fixed number of entries (1,000 for all OOS files) for partly filled pages, because only bestspace hints offer those pages.
7. The vacuum fast path and the emptied-page list it needs are removed: `oos_reclaim_empty_pages`, `vacuum_oos_reclaim_empty_pages`, the sysop commit that collects emptied pages, the thread-local sink, and the `emptied_vpids` parameter of `oos_delete`. The pages a delete empties reach the growth through the set, as ADR-0010 decision 2 requires.
8. Adoption needs the CBRD-27872 measurement against ADR-0010's implementation. INSERT time after churn, including concurrent INSERTs that need a new page, must not be worse, and sector counts and the per-cycle peak page count after churn must not be larger (ADR-0009 decision 4). Result, release builds of `94ed2ea46` (ADR-0010) and `b24fe8741e`, 6 runs of 3 churn cycles per build and row count:

   | Rows | Build | Peak pages, cycles 1 / 2 / 3 | Sectors | UPDATE ms, cycles 2+ (median) |
   | --- | --- | --- | --- | --- |
   | 2,000 | ADR-0010 | up to 1,678 / 1,819 / 1,758 | 32 | 128.8 |
   | 2,000 | this ADR | 2,001 / 2,001 / 2,001 | 32 | 110.8 |
   | 6,000 | ADR-0010 | up to 3,961 / 4,379 / 4,793 | 94 | 385.8 |
   | 6,000 | this ADR | 6,001 / 6,001 / 6,001 | 94 | 334.0 |

   Sector counts are equal. ADR-0010 peaks are snapshots between deallocation and reallocation, so they are lower bounds; this ADR's pages are never deallocated, so its peak is the file's allocated page count, which does not grow after cycle 1. Single and concurrent INSERTs after churn showed no difference. A churn cycle needs about 2,571 fewer page allocations and deallocations, and log records per 1,000 inserts go from 10.2K to 6.2K. Two defects were found and fixed by the measurement: copying the whole set on every growth made a bulk UPDATE 2.6 times slower (`f8cdfca747`), and without decision 6 the file grew 5% after cycle 1 (`b24fe8741e`).

## Consequences

1. Reusing an empty page costs one conditional WRITE fix and an ownership check, with no system operation, no header latch, and no extra log record unless the page needs reinitialization.
2. `SHOW HEAP OOS` and `spacedb` count emptied pages as allocated user pages until they are reused. This is already true while a file is idle (ADR-0009 Consequence 1). The file's sector count does not change.
3. The bestspace sync now runs under the growth lock. Growers of one file that queue for the lock run their syncs one after another instead of at the same time. An INSERT runs at most one sync instead of up to two. The measurement in decision 8 covers concurrent INSERTs.
4. The reclaimer API for notified chains (CBRD-27781) no longer returns an emptied-page list. Branches that still call it with one need a rebase.
5. No log record type or storage format changes. The reinitialization uses the existing `RVPGBUF_NEW_PAGE` record, redo-only, as the vacuum dropped-files page does.
6. A failed lookup of the file's header page now fails the INSERT. Before, it fell back to `file_alloc`, which reads the same file header.
7. Tests: an emptied page is reused by the next growth and the file does not grow; a reused page leaves the set at once; a busy page stays a candidate; an empty page with dead slots that cannot fit the record is reinitialized and reused, also after the inserting transaction aborts; restart, then one lap and reuse; set overflow, then a lap. Mutations of late removal, no recheck after the lap, no reinitialization, a reinitialization undone by rollback, and dropping a busy page each fail a test. Removing only the drop at take time fails none, because the insert drops the page under the same latch. A churn of inserts and deletes does not grow the file past its first peak; it fails without decision 6. A crash between the reinitialization and the insert is not tested.

## Evidence

- Implementation: `CUBRID/cubrid` branch `CBRD-27925-emptied-set`, `5d7eda23c` (remove the fast path), `b8a7e5d74` (reuse in place), `f8cdfca747` (take set members one at a time) and `b24fe8741e` (decision 6), on PR #8434 head `94ed2ea46`.
- Model: `my-cubrid-docs` `cbrd-27925/growth-arena/c-reuse-first/REPORT.md` and `OosReuseFirst.tla` (Work829).
- Measurement: `my-cubrid-docs` branch `docs/CBRD-27872-reuse-measure`, `cbrd-27872/growth-cost-reuse-measurement.md`.

The model is a small finite design model. It does not show that code conforms or how much time is saved.
