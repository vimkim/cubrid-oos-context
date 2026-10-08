# OOS implementation observations

Last updated: 2026-10-08 (document modification).

Read when comparing an engine/PR with requirements, diagnosing an issue, or checking progress. This file is **non-normative** and maintains one observation entry per issue. Required behavior remains in [OOS-CONTEXT.md](../../OOS-CONTEXT.md). Evidence dates/revisions below are independent of the modification date; reverify source/PR state or JIRA before making current claims. No snapshot establishes today's merge status.

Moved observations come from context revision `0eab7df`; missing dates/heads are explicit. Old function line numbers belong to their cited revisions. Later reports support later observations without silently changing accepted requirements.

## CBRD-26950: Identity stamp repair

The pre-fix vacuum retry could silently delete live data after an `ANCHORED` slot was reused: `start_lsa` advances only on full-block completion, so a restarted block derives the old physical OID again from immutable undo. `oos_chunk_exists` established occupancy, not identity; the pre-fix header lacked a stamp. A multi-chunk value could lose its whole chain. Found in PR #6986 review; this describes pre-fix behavior.

The accepted page-LSA design dates to 2026-09-04; logging/eager policy reconciliation was labelled 2026-09-09 in context commit `38be855` (committed September 11). Requirements are canonical [§2](../../OOS-CONTEXT.md#multi-chunk-oos-chain); the slot-0 generation-counter proposal was rejected.

| Evidence date | Revision | Observation |
|---|---|---|
| Report written 2026-09-04; repair-pending row carried as 2026-09-09 | PR #7695 head `c09d6c6d9`, base `2940b1cfb` | Page-LSA design implemented; later review repairs still pending in this earlier snapshot |
| Report updated 2026-09-11; supersedes the earlier repair state | PR #7695 head `eaf1165bb`, base `f4299ac0c` | All six accepted repair slices completed: stub field bounds, stale/retyped handling, eager diagnostics, logging precondition, undo/redo identity preservation, and final verification |

Evidence: [earlier report](../../../my-cubrid-docs/cbrd-26950/CBRD-26950-oos-identity-stamp-page-lsa_c09d6c6_claude.md), [completed-repair report](../../../my-cubrid-docs/cbrd-26950/CBRD-26950-oos-identity-stamp-page-lsa_eaf1165_claude.md). The latter records debug/release 35/35 configured tests and retry reproduction with zero lost committed values. These are that report's results, not runs performed during this reorganization. Repair completion at that head is not a PR-merge claim.

The old opening note labelled the completed head 2026-09-09 while the bug table still said repairs were open at the earlier head. This entry retains both dates/heads and uses the completed report's September 11 update date for its verification record.

## CBRD-27230: UPDATE chain reuse

Accepted 2026-08-13 against analysis source `725a32c6e`: [acceptance record](../../../my-cubrid-docs/cbrd-27230/wayfinder/tickets/T6-write-and-upload-spec.md), [reviewed issue specification](../../../my-cubrid-jira/issues/CBRD-27230-oos-update-dedup_725a32c_claude.md). The issue text uses the then-current 20B/generation-counter vocabulary and raw quarter-page gate; those details are superseded by canonical §1/§2. Its reuse, ownership, commit-hook, and replication decisions remain reflected in canonical [§3](../../OOS-CONTEXT.md#update-ownership-and-chain-reuse-cbrd-27230).

The source at `725a32c6e` always allocated fresh chains through `heap_attrinfo_insert_to_oos` and retained the undo-image forward-walk. Context `0eab7df` still labelled reuse “not yet implemented,” without a later exact engine revision. Treat that as a carried conformance observation, not a fresh absence/merge claim. Older sharing-check and June deferral proposals are superseded history.

## CBRD-27237: Rollback and vacuum

The old forward-walk consumed undo-image references without a commit/abort filter (`vacuum_process_log_record` gated only dropped files and rcvindex). Rollback could restore a live pre-image and later vacuum could delete its chains. One ordinary vacuum run sufficed; no block retry was needed. Identity matching cannot prevent it because undo and live stubs carry the same head OID/stamp.

Runtime evidence 2026-09-09: original engine `b871ea386` and the then-current routing candidate reproduced the failure. Disabled regression `OosRealVacuum.RolledBackUpdateKeepsCommittedOosAfterVacuum` is preserved in local commit `479cd960ec04196c92bf9789b1fc340af9046c2c`. This superseded the August 13 analysis-only report's “no runtime reproduction” wording. The October 8 context edit said it was absent from PR #7990/#7927 but recorded neither PR head for that absence; retain this as an unpinned snapshot.

Canonical §3 removes the defect mechanism through commit-conditional notification and removal of forward-walk deletion. That is an accepted design remedy, not proof of completed implementation or an assertion that later branches still have the defect. Verify the target revision before carrying the historical data-loss/merge-gate finding forward. Supporting [historical issue report](../../../my-cubrid-jira/issues/CBRD-27237-oos-forward-walk-rollback-delete_725a32c_claude.md).

## CBRD-26786: Empty-page reclaim

Observation recorded 2026-08-28: PR #7617 head `8ba9b5398` implemented the accepted reclaim invariant, including reviewer fixes R3/R4/B1; the context said merge to `feat/oos` was pending. It included the non-numerable migration, skipped page reclaim for legacy numerable files, and removed dead `oos_remove_page`. Vacuum fed batch candidates after unfixing the home page; LSA/growth gates covered deferral and eager/SA pages. Required invariant: canonical [§4](../../OOS-CONTEXT.md#empty-page-reclaim-invariant-cbrd-26786-accepted-2026-08-28).

The later identity repair refined touched-page candidates to actually emptied pages, once each; its report says reclaim gates/sweep/deallocation were unchanged. Read the [CBRD-26950 entry](#cbrd-26950-identity-stamp-repair) for that report's date/head. Neither snapshot proves today's integration state.

## CBRD-26831: Page enumeration

Observation 2026-07-02: `oos-m2-all-plans-experimental` created `FILE_OOS` with `is_numerable=false` and converted sync/stats to `oos_collect_data_page_vpids` with `OLD_PAGE_MAYBE_DEALLOCATED` plus a `PAGE_OOS` type check. ADR-0001's skipped-page counter was not yet added; testcase verification/merge was pending. No exact experimental head was recorded. OOS had been numerable through `4ddbc7c`.

Later integration evidence belongs to [CBRD-26786](#cbrd-26786-empty-page-reclaim); neither snapshot closes the observability gap without verification. Required enumeration: canonical §2; rationale: [ADR-0001](../adr/0001-oos-page-enumeration-non-numerable.md).

## CBRD-27057: Four-record physical target

Snapshot dated 2026-09-22, carried in context `0eab7df`: draft PR #7462 implemented the physical target for trigger/stop, excluded `PRM_ID_HF_UNFILL_FACTOR`, and added target/boundary/unfill-independence coverage. PR #7990 head `7008beee0` on `feature/oos-merge` still used raw `DB_PAGESIZE/4`; that implementation was not integrated. JIRA was recorded Resolved/Fixed despite the draft remaining open/dirty; no draft head was recorded. Workflow state does not prove integration. Required formula: canonical §1.

## CBRD-26912: Inline preference

Record dated 2026-09-22, added to context 2026-10-08: `STORAGE PREFER_INLINE` is accepted 11.5 merge scope. The context records PR #7334 merged into `feat/oos` as `4523843d1` on 2026-06-29 and JIRA Resolved/Fixed for target `guava`. This corrects “proposed — NOT yet merged.” It is a carried merge/workflow observation, not a new live lookup; required behavior is canonical §1.

## CBRD-26830: TDE

Fixed 2026-06-16 in the carried record: `feat/oos` commit `138f624964` added existing-file encryption through `xfile_apply_tde_to_class_files` and class-algorithm application before publishing a lazily created OOS VFID. Required protection is canonical §5.

## CBRD-26814: Stub writer bounds

Fixed 2026-07-03 in the carried record: `feat/oos` commit `bceac0ddc` checks the actual stub write position `*ptr_varvals`, restoring the `S_DOESNT_FIT` grow-and-retry path. BLOB/CLOB locators remain OOS-demotable per [ADR-0002](../adr/0002-oos-lob-locator-demotion.md); exclusion was a reversed proposal.

## CBRD-26458: unloaddb performance

The carried record reported unloaddb 1.6–1.7× slower with `heap_attrinfo_start` called per `heap_next` on `feat/oos`. No observation date/exact engine head was recorded. Verify the target workload/revision before treating this as a current regression.

## CBRD-26516: Redundant Resolve/Expand

The carried record labelled record-level UPDATE Expand redundancy DONE through CBRD-26729 on `feat/oos`, without a completion date/head. Non-raw-byte consumers use cheap attribute-layer Resolve under the opt-in Expand contract. CBRD-26953 distinguished residual unchanged-value re-reads as M1 behavior, rather than that redundant-Expand defect. Its accepted successor is [CBRD-27230](#cbrd-27230-update-chain-reuse).

## CBRD-26954: Bestspace fit check

Fixed 2026-07-01 in the carried record: commit `e51dc8fd1b` removed redundant `sizeof(SPAGE_SLOT)` reservation. Canonical §2 requires comparison against `spage_max_space_for_new_record`, which already reserves the slot.

## CBRD-26847: Fetch contract census

The carried census found about 22 `_expand_oos` call sites, five requiring raw-byte Expand: `xlocator_lock_and_fetch_all`, `redistribute_partition_data`, `catcls_delete_instance`, `catcls_update_instance`, `catcls_update_class_stats`. About 17 mechanically migrated sites were candidates for cheap fetch. No census date/engine revision was recorded; this is an observation, not a permanent caller-count contract. Fetch requirements remain canonical §3 / [ADR-0003](../adr/0003-oos-expansion-is-opt-in.md).

## CBRD-26948: Raw-byte fetch gap

The carried record labelled the issue OPEN without date/head: PR #7093 / CBRD-26729's opt-in Expand left `xlocator_fetch_all` → unloaddb/compactdb leaking unresolved stubs to OOS-blind `load_object.c`. Older notes loosely attributed it to CBRD-26583 / PR #7093. Verify the target revision before claiming it persists; raw-byte consumers must Expand under canonical §3.

## CBRD-27350: OOS observability

The carried record folded `FILE_OOS` into heap accounting and lacked durable per-table ownership metadata in `FILE_DESCRIPTORS`.

- 2026-07-02 experimental observation: `file_tracker_item_spacedb` (`assert_release(false)`), `file_tracker_get_and_protect`, and `file_header_dump_descriptor` asserted during QA (`cbrd_20644`, `tbl_enc_08/14`, `_02_show_archive_log_header`, `json_backup_restore`). `oos-m2-all-plans-experimental` folded OOS into `SPACEDB_HEAP_FILE` for zero output drift and allowed unprotected read-only tracker scans. No exact head was recorded. The notes identified a narrow SERVER_MODE checkdb-vs-DROP race until an owner descriptor landed.
- 2026-09-01 ticket-of-record update: CBRD-26871 was recorded resolved as duplicate; its T1 `SPACEDB_OOS_FILE` and T2 `FILE_OOS_DES{class_oid}` owner-descriptor candidates were re-filed as CBRD-27350. The descriptor was a prerequisite for conditional-lock protection/per-table attribution, not a new design decision here.
- The carried notes said only debug `oos.log` proved per-attribute placement/OOS space, forcing placement checks to debug builds. Verify current observability before choosing a build or treating this limitation as current.

## CBRD-26668: Vacuum integration

The carried record labelled deferred DELETE/UPDATE cleanup DONE, with PR #6986 merged but no recorded merge date/hash. Original forward-walk/REMOVE/eager implementation descriptions are retained in [M1 history](design-history.md#m1-update-and-vacuum). “Vacuum integration done” does not close later identity, rollback, reuse, or page-reclaim requirements.

## CBRD-26939: CDC/flashback history

The carried missing-feature note concerned historical OOS value reconstruction, not just replacing a still-live stub. Canonical §5 contains the 11.5 disposition. [ADR-0004](../adr/0004-durable-oos-supplemental-images.md) preserves 2026-09-08 analysis against `2940b1cfbc3c2d4d0fac3f9244a960350debd380`; [ADR-0005](../adr/0005-defer-oos-history-from-the-11-5-merge.md) defers the complete change on 2026-09-22. Acceptance/deferral records do not establish PR closure or later implementation.

## Other carried observations

These distinct entries have no verification date/exact engine head recorded in context `0eab7df`:

| Issue | Carried observation |
|---|---|
| CBRD-26517 | Main OOS project ticket; no workflow-state assertion |
| CBRD-26637 | OOS error-handling ticket; no workflow-state assertion |
| CBRD-26608 | DROP TABLE OOS file leak labelled DONE through `oos_remove_file`; requirement in canonical §5 |
| CBRD-26658 | Last-insert-page-only bestspace limitation labelled DONE through the three-tier policy; requirement in canonical §2 |
| CBRD-26776 | Bulk demotion limitation labelled DONE through PR #7158; dated gate/floor evolution in [history](design-history.md#supersession-timeline) |
| Replication refactoring (no issue key) | Unnecessary OOS replication log in `locator_add_or_remove_index` |
| RECDES length (no issue key) | Four-byte length limits reconstruction to about 2GB; eight-byte/16EB extension was an idea |
| Buffer handling (no issue key) | Incomplete `S_DOESNT_FIT` handling remained an upper-layer concern |
| Deferred read/compaction | No PEEK mode or across-page compaction reported; proposals in [history](design-history.md#proposals-and-deferred-optimizations) |
| Merge instrumentation | Temporary crash-on-invariant code marked `REVERT BEFORE MERGE` in `heap_file.c`/`vacuum.c`; readiness observation, not required behavior |
| Integration branch snapshot | Old context used `feat/oos`; September 22 target evidence identifies `feature/oos-merge` / PR #7990. Verify the requested branch rather than treating either name as current |
