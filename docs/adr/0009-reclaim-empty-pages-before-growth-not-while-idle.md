---
status: accepted
---

# Reclaim empty OOS pages before growth, not while the file is idle

> **Amends** [OOS-CONTEXT.md](../../OOS-CONTEXT.md) §4, the empty-page reclaim invariant (CBRD-26786, accepted 2026-08-28). It removes the requirement that an emptied page is returned to the file manager while its OOS file receives no new allocation. The rule that a file reserves no new sector while a safely reclaimable empty page exists is unchanged.

Accepted by the OOS owner on 2026-11-05 for CBRD-27925, after Work818, an independent review of the reclaim scope that remains once ADR-0008 (reclaim after finality, on branch `docs/adr-0008-reclaim-after-finality` until its accepted text merges) is implemented, found that the two sentences of the invariant contradict each other in practice.

## Context

The invariant said: "Every fully emptied OOS data page is eventually returned to the file manager. An OOS file reserves a new sector only when no safely reclaimable empty page exists right now."

The engine finds an empty page in two ways only: the vacuum fast path, which checks the pages a committed delete batch emptied once, and the growth-gate sweep, which runs at the file's single growth point. A page that the fast path misses (INSERT rollback, a busy latch, an error, a restart) stays allocated until the same OOS file allocates a page again. Five CBRD-26659 regressions (`churn_abort_retry`, `churn_insert_delete`, `churn_insert_update_delete`, `churn_restart`, `snapshots_reclaim`) failed because they waited 20 seconds with no further OOS write and expected the page count to drop.

Returning a page while the file is idle has no storage effect. `file_dealloc` puts the page back into the file's own partial sector table. A permanent file releases its sectors to the disk only in `file_destroy` (`file_manager.c:4318` at `feature/oos-merge` `d52b1889e`; the other `disk_unreserve_ordered_sectors` call is in the `file_create` failure path). So the only consumer of a returned page is the next allocation of the same OOS file, and that allocation runs the growth-gate sweep first. An idle return frees no disk space, shrinks no file, and gives no other table any space. A mechanism that revisits idle files would add a background task, its concurrency checks, and its cost for no space benefit.

## Decision

1. An emptied OOS data page must be reclaimed or reused **before the file reserves a new sector**. Returning it while the file receives no allocation is not required.
2. The growth-side rule stays: an OOS file reserves a new sector only when no safely reclaimable empty page exists right now. Lost in-memory hints, restarts, rollbacks, and busy latches must not break it.
3. The vacuum fast path and the growth-gate sweep stay. The fast path is an optimization; the sweep is the guarantee.
4. Tests do not wait for an idle return. They write again after the deletes and check that the file reuses its emptied pages: in every cycle of a repeated workload, the peak page count stays within the first cycle's peak plus an allowance of max(2 pages, 10%), and the file's reserved sectors after a refill do not exceed the first peak. Run at least five cycles so that growth that accumulates by a page per cycle exceeds the allowance. Keeping the exact first peak and the drained page count are observations, not pass/fail oracles. Raising a timeout is not a substitute.

## Consequences

1. `SHOW HEAP OOS` and `spacedb` can show emptied pages as allocated user pages while the file is idle. This is expected.
2. CBRD-27925 no longer needs a revisit mechanism independent of growth. It keeps the growth-side obligations: the hint lost when a sweep skips a page busy under an INSERT-undo latch, the fast-path candidate supply after ADR-0008 moves chunk deletes into postpones, and the boot rule after restart.
3. The five regressions change their oracle from an idle page-count drop to reuse before growth. They stay disabled until a native run on a matching engine and testcase revision passes.

## Amendment 2026-11-05: test allowance

Decision 4 first required that the peak page count of a repeated workload not grow at all. A rerun of `cbrd_26659_snapshots_reclaim` (engine `e3589ae42`, testcase `3ec4e014d`) reached peaks of 25, 26, and 26 pages for the same 25 OOS records, after an earlier run had passed with 25, 23, and 25. The extra page held no record. Its cause was not confirmed. On that engine an empty page that the LSA gate defers is not safely reclaimable, so decision 2 permits such a page, and an exact-peak oracle can differ by a page between runs. Decision 4 now allows max(2 pages, 10%) and asks for five cycles. Decision 2 is unchanged. Evidence: `my-cubrid-docs` `cbrd-27925/growth-bound-design.md`.

## Evidence

- Independent review: `my-cubrid-docs` `cbrd-27925/adr0008-claude-review.md`, section F5.
- Original failures: `my-cubrid-docs` `cbrd-26659/reclaim-compact-diagnosis.md` (engine `e3589ae42`, testcase `01df2600a`).
