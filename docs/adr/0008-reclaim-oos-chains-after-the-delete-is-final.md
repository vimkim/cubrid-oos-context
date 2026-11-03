---
status: proposed
---

# Reclaim OOS chains only after the delete is final

> **Amends** [OOS-CONTEXT.md](../../OOS-CONTEXT.md) §2 (chunk layout, identity checks, eager cleanup), §3 (UPDATE notification, REMOVE and eager roles), and §4 (recovery invariants, Vacuum + OOS, empty-page reclaim). **Supersedes** the commit-hook placement of `RVOOS_NOTIFY_VACUUM` and the LSA reclaim gate. **Amends [ADR-0006](0006-reject-pre-stamp-databases-at-boot.md)** for format changes made before the PR #7990 merge.

Proposed by the OOS owner on 2026-11-03, on the evidence of TLA+ design models. It takes effect only after the team lead confirms it; a confirmation meeting is requested for 2026-11-04. Until then the rules in `OOS-CONTEXT.md` at context commit `281a940` stay normative. On confirmation, record who confirmed it and when, change the status to accepted, and merge the specification revision that accompanies this ADR.

## Context

Three open defects at `feature/oos-merge` `dcbf09e4f` can lose committed data or corrupt a page:

- CBRD-27858 and CBRD-27781: a vacuum sysop frees a heap forward slot or an OOS chunk slot, another transaction takes it, and `log_sysop_abort` or restart undo writes the old record back over it with `spage_insert_for_recovery`.
- CBRD-27237: the forward-walk deletes the chain named by an UPDATE undo image without knowing whether the UPDATE committed, so it deletes the live chain of a rolled-back UPDATE.

A design model of the current code reproduced these defects and CBRD-26950 (before identity stamps). Each defect depends on one assumption only:

1. Space freed by an undoable delete is reusable at once (CBRD-27858, CBRD-27781). The code states it in `spage_save_space`: "Vacuum workers do not rollback their heap changes". That stopped being true when vacuum began deleting OOS chunks inside sysops that can abort.
2. Information that is not final may decide that a chain is dead (CBRD-27237).
3. An OOS OID keeps naming the same value (CBRD-26950). Identity stamps already cover it.

The existing mechanisms cover assumption 1 in separate places: latch retention, the LSA reclaim gate, and a proposed in-memory exclusion map. Heap and file-manager code avoid the same problem by releasing space only after commit through postpones.

## Decision

1. **A chunk delete is never undone.** The transaction or sysop that decides a chain is dead records a **reclaim intent** `(OOS VFID, head OOS OID, head identity stamp)` as a postpone. The **OOS reclaimer** deletes the chunks only after that unit commits, with redo-only log records. A slot it frees is reusable at once. If the deciding unit aborts, the postpone is discarded and the chain stays.
   - REMOVE removes the heap record and records the intent in one sysop; `log_sysop_commit` runs it.
   - SA/non-MVCC eager cleanup records the intent during the DML; it runs at transaction commit.
2. **UPDATE notification through a postpone (A').** An UPDATE records the chains it drops in a postpone. A statement or savepoint rollback cancels that postpone. The postpone runs after `LOG_COMMIT_WITH_POSTPONE` and appends `RVOOS_NOTIFY_VACUUM`; restart recovery reruns it when that record is durable. Vacuum consumes the notification only when no active snapshot is older than the UPDATE's commit, then runs the reclaimer. The undo-image forward-walk deletion path is removed, as §3 already required.
   - **Open at confirmation: B3 in place of A'.** The 2026-11-04 review recommends B3, an undoable MVCC mark on the dropped chain's head, and asks the confirmation meeting to choose between A' and B3 (see Considered options). A' needs a log path the engine does not have: an MVCC log record requires a valid transaction MVCCID (`log_append.cpp:966-971`), and commit clears it in `logtb_complete_mvcc` (`log_manager.c:5267`) before postpones run (`5285`). If B3 is chosen, this decision, §3 step 3, and the chunk layout are revised before acceptance.
3. **The reclaimer converges on rerun.** It reads the chain from the head, compares the head stamp with the intent and each next chunk's stamp with the stamp stored in the link, and stops at the first absent, deallocated, retyped, or mismatching slot. It deletes from the tail and the head last. After an error or a crash it reruns from the head until the chain is gone. An error must not end a reclaim while chunks remain; whether the engine fails stop or re-queues the intent is left to the implementation. Continuation pages are fixed as possibly deallocated, like the head page.
4. **The next link carries the next chunk's stamp.** The chunk header grows from 24B to 32B: `total_data_length`, `chunk_index`, next-chunk OID, next-chunk identity stamp, own identity stamp. Insertion runs tail first, so the stamp is known when the link is written.
5. **The LSA reclaim gate is removed.** Its only stated reason was that an unfinished deleter could undo chunk deletes into an empty page. That cannot happen once chunk deletes have no undo. The vacuum fast path and the growth-gate sweep stay.
6. **Pre-merge format changes keep storage-format revision 1.** Changes in this decision land before the PR #7990 merge, so `DISK_STORAGE_FORMAT_REVISION` stays 1. Databases created by earlier pre-merge builds must be recreated under ADR-0005; the stamp does not detect them.
7. **Adoption requires a measured improvement.** The engine change merges only with a measured performance improvement over the current implementation: log bytes written per reclaimed value, vacuum time per log block on an OOS UPDATE workload, and OOS file size after UPDATE/DELETE churn, with INSERT and UPDATE latency not worse.

Out of scope: the heap side of `vacuum_heap_record` keeps its physical undo. The heap forward slot of CBRD-27858 stays protected by keeping the forward page latched until the sysop ends (draft PR #8348). Identity stamps (CBRD-26950) are unchanged.

## Considered options

Each option was checked with TLC; a failing option is listed with its counterexample.

| Decision | Option | Result |
| --- | --- | --- |
| Protecting an undoable chunk delete | Current code (`ANCHORED`, latch released per chunk) | Undo writes over another record, or finds no room |
| | D1: keep every page latch until the sysop ends | Safe for undo, but two vacuum workers wait for each other's page latch; chains cross pages in any order and page latches have no deadlock detection |
| | D2a: `ANCHORED_DONT_REUSE_SLOTS` with a postponed mark-reusable | Protects the slot number only; another insert uses the freed bytes and the undo fails with `SP_DOESNT_FIT` |
| | D2b: D2a plus a byte reservation until the sysop ends | Possible. Needs vacuum-worker reservations in `spage_save_space`, keeps the whole-record undo, and still needs the LSA gate |
| | D2c: close the page to inserts and reclaim until the sysop ends | Possible. Keeps the page's free space unusable meanwhile and needs an in-memory map with lifetime and 2PC obligations |
| | **D3: no undo (chosen)** | Possible with no protection at all, because nothing is ever written back |
| Deciding that an UPDATE dropped a chain | Current code (undo image, block ended) | Deletes the chain of a rolled-back UPDATE; with UPDATE chain reuse, also of a committed one |
| | B: also require T1's commit record | Fails after a statement rollback followed by commit |
| | A: commit-hook notification before `logtb_complete_mvcc` | Fails when the notification is flushed and the server crashes before the commit record |
| | **A': postpone notification (chosen)** | Possible; vacuum must also wait for older snapshots |
| Reclaimer order and retry | Head first | A rerun finds no head and leaves the rest of the chain |
| | Tail first without link stamps | A rerun follows a link into a reused slot and deletes another record |
| | Tail first, link stamps, error dropped | The reclaim stops with chunks left |
| | **Tail first, link stamps, rerun (chosen)** | Possible |

The 2026-11-04 review added nine more options. B2, B3, and B4 were checked with TLC in the same models; the others were judged from engine source and this specification.

| Decision | Option | Result |
| --- | --- | --- |
| Deciding that an UPDATE dropped a chain | B3: the UPDATE writes its delete MVCCID into the dropped chain's head with an undoable MVCC log record; vacuum decides as it does for heap records | Possible; vacuum must still wait for older snapshots. Rests on the engine's order: abort undoes every change before `logtb_complete_mvcc`, and vacuum processes a block only below the oldest visible MVCCID. Costs a head-page write and one MVCC record per dropped chain on UPDATE, a new recovery index, a vacuum dispatch branch, and an 8B delete MVCCID in the head. Recommended over A', subject to the UPDATE latency check of decision 7 |
| | B4: as B, and the UPDATE's undo record has no compensation record | Possible in the model. Vacuum blocks carry only undo-bearing MVCC records, not compensation records, so vacuum would need a new log lookup |
| | B6: the commit postpone reclaims the chain directly, without vacuum | Fails: a snapshot taken before the commit reads the reclaimed chain. Valid only for eager cleanup, where no concurrent reader exists |
| Recording the REMOVE intent | **Postpone in the vacuum sysop (chosen)** | Possible |
| | B2: reclaim the chains first, then remove the heap record, with no postpone | The model's reader and slot properties hold, but a heap record that still exists names a partly reclaimed chain. A crash leaves that state, and a release-build vacuum error marks the block done, so it stays. NULL-snapshot readers such as `btree_load` read it and fail with `ER_HEAP_OOS_CORRUPTED_RECORD` |
| | B5: a persistent reclaim list in the OOS file | Same meaning as A' or B3, depending on when the entry is written; adds storage and recovery code |
| Storage layout | C1: one page per chain, freed with `file_dealloc` | Removes slot reuse, because `file_dealloc` already postpones. A value just above 24B can occupy a whole page |
| | C2: never reinsert into a page; free only empty pages | Removes slot reuse. One live chunk pins a page, compaction would change OIDs that log undo images name, and page reclaim still meets undo |
| | C3: logical chunk IDs with a location map | Removes all three assumptions, at the cost of a map lookup per read, map recovery, and a much larger format change |
| | C4: overwrite the chain in place and keep the old value in undo | Puts whole values back into undo, against decision 7 |

A combined model of the chosen design, with an MVCC snapshot reader, an UPDATE that keeps its chain, page deallocation without a gate, and a crash or reclaimer error, passed every property. Each variant that undoes one decision failed its own property. With B3 in place of A', the combined model passed the same properties; with B2 in place of the REMOVE postpone, it failed only the property that an existing heap record names an intact chain.

## Consequences

1. The implementation at `dcbf09e4f` does not conform: it logs `RVOOS_DELETE` with the whole record as undo, keeps the forward-walk, has no `RVOOS_NOTIFY_VACUUM` emitter, writes 24B chunk headers, fixes continuation pages with plain `pgbuf_fix`, and implements the LSA gate. The gap is recorded in the [implementation observation](../reference/implementation-observations.md#adr-0008-reclaim-after-finality).
2. New recovery indexes are needed: the reclaim-intent postpone, the UPDATE-drop postpone, and a redo-only chunk delete. `RVOOS_NOTIFY_VACUUM` gets its emitter and consumer. The CBRD-27237 deep dive's open items still apply: a `RVOOS_NOTIFY_VACUUM` append path that takes an explicit MVCCID, and what a recovery rerun of the postpone does with an old MVCCID.
3. Reclaiming a value no longer writes its bytes as undo. The log still holds one small redo record per chunk and one intent per chain. The size of the saving is not measured yet.
4. The `cubrid-verify-vacuum-slot-undo` conformance model checks the current shape. Its OOS chunk property becomes vacuous once chunk deletes have no undo, and its model must be updated with the implementation.
5. Regression tests need: a rerun after each reclaimer step with a concurrent insert into the freed slot; a snapshot older than the UPDATE's commit reading the old chain while the notification is pending; statement and savepoint rollback before commit; a crash between `LOG_COMMIT_WITH_POSTPONE` and the notification; page deallocation during a reclaim.

## Evidence

Models and results are in the documentation repository at commit `536ee49` (branch `docs/oos-reclaim-alternatives`; the 2026-11-03 results are at `554356e`):

- [Redesign report](../../../my-cubrid-docs/oos/reclaim-redesign.md): assumptions, defect mapping, D3 design, performance discussion, and the U1 model result (80 checks).
- [Decision checks](../../../my-cubrid-docs/oos/reclaim-decisions.md): per-decision models, the combined model, counterexamples, the state invariants that explain each passing option, witnesses, and the review of the remaining alternatives (208 checks).
- [Engine facts for B2 and B3](../../../my-cubrid-docs/oos/reclaim-engine-facts.md): vacuum's commit decision, which log records reach vacuum, duplicate vacuum jobs, readers without a snapshot, UPDATE's handling of the old chain, and restart reruns, with file:line citations at `dcbf09e4f`.
- Models and runners: `my-cubrid-docs/oos/reclaim-model/` (`OosReclaim.tla`, `OosSpaceProtect.tla`, `OosDropDecision.tla`, `OosReclaimRetry.tla`, `OosReclaimDesign.tla`, `run.py`, `check_decisions.py`).
- [CBRD-27237 fix-options deep dive](../../../my-cubrid-docs/cbrd-27237/CBRD-27237-fix-options-deep-dive_dcbf09e_claude.md): the A' recommendation and the commit-hook crash window.

The models are design models with small bounds. They do not show that code conforms or that performance improves.
