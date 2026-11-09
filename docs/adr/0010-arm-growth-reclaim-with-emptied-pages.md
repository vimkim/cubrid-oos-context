---
status: proposed
---

# Arm growth-side reclaim with emptied pages, not chunk deletes

> **Amends** [OOS-CONTEXT.md](../../OOS-CONTEXT.md) §4, the growth-gate sweep mechanism of the empty-page reclaim invariant, and the glossary term "Pending-delete counter". The invariant itself is unchanged: an OOS file reserves a new sector only when no safely reclaimable empty page exists ([ADR-0009](0009-reclaim-empty-pages-before-growth-not-while-idle.md) decision 2).

Proposed on 2026-11-05 for CBRD-27925 and CBRD-27872 (Work821). Revised on 2026-11-09 after the growth arena (Work829): the owner chose this set as step 1 and in-place reuse as step 2 (see Follow-up). It takes effect when the OOS owner accepts it. Until then §4 stays normative.

## Context

The owner asked whether the rule "reserve no new sector while a reclaimable empty page exists" costs INSERT and UPDATE too much, and whether a weaker bound on file growth would do.

At `feature/oos-merge` `d52b1889e`, the cost comes from how the growth gate is armed, not from the rule:

- `oos_delete` arms the gate after every successful chain delete (`oos_file.cpp:3512`), whether or not the delete emptied a page. The vacuum fast path reclaims the pages a delete batch emptied, but it does not disarm the gate.
- An armed growth collects and sorts the whole sector table, then READ-fixes every allocated page from the cursor until it reclaims one. A lap that reclaims nothing walks the whole file. Concurrent growers of the same file wait for it (`oos_reclaim_sweep_step`, 1816-2000).
- So after any vacuum batch, the next growth of the file usually walks the whole file and finds nothing. On a large file this is a full read of the file on the INSERT path.

The same structure has a correctness gap (Work818). An INSERT rollback notes its delete while it holds the page WRITE latch. A sweep that cannot READ-fix that page skips it, and the lap settlement clears the counter, so the empty page waits for the next unrelated delete.

A TLA+ model of one OOS file compared the current gate, two fixes for the rollback race, a per-allocation page budget (the weaker bound), and an emptied-page set. The model has bounded pages and chunks, one grower (the per-file single-flight serializes growers), vacuum deletes, the fast path, one rollback that holds a latch, restarts, and optionally writes between the grower's steps.

| Design | Current rule | File size bounded |
| --- | --- | --- |
| Current gate (`SKIPPED` on a busy page) | Fails (the Work818 race) | Only without writes during a growth |
| (a) Count a busy page as `DEFERRED` | Holds | Only without writes during a growth |
| (b) Retry set for pages emptied by rollback | Holds | Only without writes during a growth |
| Examine at most N pages per allocation (N = 1, 2) | Fails | No |
| **Emptied-page set** | **Holds** | **Yes, also with writes during a growth** |

A second set of models (the growth arena, five candidates) attacked the set design itself by lifting one model restriction at a time. Four gaps broke the current rule or the size bound, and each has a fix that passes:

| Lifted restriction | Without the fix | Fix |
| --- | --- | --- |
| One grower. The source holds single-flight only around the sweep and releases it before `oos_file_alloc_new` (`oos_file.cpp:1890`, 2012-2026). | Rule fails: a second grower allocates while the first checks a candidate. | Hold the per-file growth lock through `file_alloc`, or reuse the page in place. |
| No insert failure. An insert can fail after it obtained a page and before its first record. | Rule fails, and the file grows to the cap: the empty page is in no set. | The failure path adds the page (decision 2). |
| No set overflow during a lap. | Rule fails: a page emptied behind the lap cursor while the set overflows is missed, and the lap clears the mark. | Overflow during a lap keeps the file unknown (decision 4). |
| No restart with writes. | The file grows to the cap: the lap ends and the growth allocates without reading the set that writes filled during the lap. | Read the set again after the lap (decision 4). |

Removing a refilled page lazily, when a growth finds it non-empty, also failed: a page refilled and emptied again between growths is skipped every time, or rechecked without end. One case passed no candidate: a rollback that takes a new latch on every candidate at the right moment, with writes during the growth, grows the file to the cap in every design. This is recorded as a model limit.

A cursor-ordered sweep can be dodged: a write refills a page just before the cursor reaches it and empties it after. A page budget can be blocked: one latch and live chunks fill each budget window. The emptied-page set reaches each emptied page directly. In the model it also examined no page during a growth in which no page was empty; every other design did.

## Decision

1. Each OOS file keeps an in-memory set of **emptied pages** in its reclaim state, under the bestspace mutex, with a size limit.
2. A page enters the set where it becomes empty: the chunk delete that leaves it with no record (`oos_delete_chain`, and the ADR-0008 reclaimer through the same primitive) and the recovery delete (`oos_rv_redo_delete`) that empties it. Any other path that leaves an allocated OOS data page empty, such as a failure after allocation and before the first insert, also adds it.
3. Before the file allocates a page, the growth step checks set members with the existing two-phase reclaim. A reclaimed page ends the step. One growth per file runs at a time, and it holds that per-file lock from the set check through `file_alloc`. An insert into a page of the set removes the page under the WRITE latch of that insert. A page that is busy (another thread holds its latch) stays in the set. A page that is no longer empty leaves the set under the latch that shows it, and a reclaimed page under the WRITE latch it is deallocated under. A page found already deallocated stays: no latch shows that it was not reallocated, emptied, and added again since, and a later check drops it once it is refilled. The fast path removes the pages it reclaims.
4. The set may be incomplete after a restart, a failed insertion into the set, or overflow of the size limit. Then the file is marked unknown, and its next growth runs one sector-bitmap lap over the whole file, as the boot rule does now. Pages that the lap finds busy enter the set. A completed lap clears the mark only when the set did not overflow during the lap; otherwise the file stays unknown and the next growth runs the lap again. After the lap, the growth checks the set again before it allocates.
5. The pending-delete counter is removed. A chunk delete that leaves records on the page no longer arms anything.
6. `RVOOS_INSERT` undo data carries the OOS file's VFID (8 bytes). The undo deletes the chunk and may empty the page, and recovery passes the page but not the file, so without it a rollback could not name the set that takes the page. Redo data is unchanged. A record without the VFID falls back to the bestspace hint, and then to marking every known file unknown. The change lands before the PR #7990 merge, so under [ADR-0006](0006-reject-pre-stamp-databases-at-boot.md) as amended by ADR-0008 decision 6, `DISK_STORAGE_FORMAT_REVISION` stays 1.
7. Adoption needs a measurement under CBRD-27872. INSERT time on a large OOS file after UPDATE and DELETE churn must not be worse, and file size after the churn must not be larger.

## Consequences

1. Growth costs a check per page emptied since the last growth, plus a recheck of pages still latched by a rollback. The whole-file lap remains once per file after a restart or overflow.
2. The Work818 rollback race closes: a page that is latched when checked stays in the set.
3. The ADR-0008 obligation to re-supply fast-path candidates becomes an optimization. Without the fast path, the next growth still finds every emptied page in the set.
4. Every path that empties an OOS data page must add it to the set. A path that does not strands that page until the next restart. Review and tests must cover each emptying site.
5. The log format changes before the PR #7990 merge: `RVOOS_INSERT` gains an 8-byte undo image (decision 6). The storage-format revision stays 1 and no database needs recreating for it: a new engine reads an older record through the fallback, and older readers skip undo data. The log applier reads only `RVOOS_INSERT` redo data. Rolling back the transaction that created an OOS file now passes the VFID too, because the header record uses the same log record.
6. Tests: an INSERT rollback that empties a page while a growth runs; a delete that empties no page followed by a growth, which must examine no page; a restart followed by a growth; overflow of the set limit, also during a lap; two concurrent growers of one file; an insert that fails before its first record.
7. The per-file growth lock now covers `file_alloc`. Concurrent INSERTs that need a new page of the same file wait for one allocation instead of one sweep. CBRD-27872 measures this.
8. The add hook does not depend on a caller's output list. Eager reclaim passes no list (`emptied_vpids == NULL`) and still must add the pages it empties.

## Follow-up: in-place reuse (step 2)

On 2026-11-06 the owner chose reuse-first as the target: a growth that finds an empty page in the set writes into it under the latch it checked with, and the page is never deallocated. In the arena, reuse-first held the rule with two growers and no growth lock (candidate A), and held the size bound in all four settings with one grower, including restart with writes (candidate C). It also removes the dealloc path, the vacuum fast path, and the fast-path re-supply duty. On 2026-11-09 the owner sequenced it after this decision: the set lands first, and reuse replaces deallocation after the CBRD-27872 measurement. That change needs its own ADR, and it amends [ADR-0009](0009-reclaim-empty-pages-before-growth-not-while-idle.md) decision 3 (keep the fast path).

## Evidence

- Report: `my-cubrid-docs` `cbrd-27925/growth-bound-design.md` (Work821), with the engine cost structure, the model, and its limits.
- Model and runner: `my-cubrid-docs` `cbrd-27925/growth-model/OosGrowthBound.tla` and `run.py`.
- The rollback race: `my-cubrid-docs` `cbrd-27925/adr0008-claude-review.md` (Work818).
- Growth arena (Work829): `my-cubrid-docs` branch `docs/CBRD-27925-growth-arena`, `cbrd-27925/growth-arena/`. Candidate A attacks this set design (`a-cand-attack/REPORT.md`); candidate C models reuse-first and the recheck after the lap (`c-reuse-first/REPORT.md`).

The model is a small finite design model. It does not show that code conforms or how much time is saved.
