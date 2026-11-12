# OOS implementation observations

Last updated: 2026-11-12 (document modification).

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

Accepted 2026-08-13 against analysis source `725a32c6e`: [acceptance record](../../../my-cubrid-docs/cbrd-27230/wayfinder/tickets/T6-write-and-upload-spec.md), [reviewed issue specification](../../../my-cubrid-jira/issues/CBRD-27230-oos-update-dedup_725a32c_claude.md). The issue text uses the then-current 20B/generation-counter vocabulary and raw quarter-page gate; those details are superseded by canonical §1/§2. Its reuse, ownership, and replication decisions remain reflected in canonical [§3](../../OOS-CONTEXT.md#update-ownership-and-chain-reuse-cbrd-27230); its commit-hook notification placement was replaced on 2026-11-05 by the ADR-0008 postpone ([entry](#adr-0008-reclaim-after-finality)).

The source at `725a32c6e` always allocated fresh chains through `heap_attrinfo_insert_to_oos` and retained the undo-image forward-walk. Context `0eab7df` still labelled reuse “not yet implemented,” without a later exact engine revision. Treat that as a carried conformance observation, not a fresh absence/merge claim. Older sharing-check and June deferral proposals are superseded history.

## CBRD-27237: Rollback and vacuum

The old forward-walk consumed undo-image references without a commit/abort filter (`vacuum_process_log_record` gated only dropped files and rcvindex). Rollback could restore a live pre-image and later vacuum could delete its chains. One ordinary vacuum run sufficed; no block retry was needed. Identity matching cannot prevent it because undo and live stubs carry the same head OID/stamp.

Runtime evidence 2026-09-09: original engine `b871ea386` and the then-current routing candidate reproduced the failure. Disabled regression `OosRealVacuum.RolledBackUpdateKeepsCommittedOosAfterVacuum` is preserved in local commit `479cd960ec04196c92bf9789b1fc340af9046c2c`. This superseded the August 13 analysis-only report's “no runtime reproduction” wording. The October 8 context edit said it was absent from PR #7990/#7927 but recorded neither PR head for that absence; retain this as an unpinned snapshot.

Runtime evidence 2026-11-03 (successor observation; the September evidence above is retained): `feature/oos-merge` `dcbf09e4f7fd02ff9c8fc6493ec8887fc2919d67`, `debug_gcc` build, recorded during the CBRD-27881 survey. The preserved regression, ported to that revision with only `DISABLED_` removed (local commit `338b7a1ddda64b7976546281a0a1d998e98b3af1`, not pushed), failed in both of two runs. The original value was readable after rollback; after vacuum, `oos_read_with_alloc` returned -2. gdb showed the vacuum worker calling `vacuum_forward_walk_reclaim_oos` from `vacuum_process_log_block` (`src/query/vacuum.c:3619`), which deleted the committed original value chain through `oos_delete_chain`. The issue's SQL reproduction failed with -1389 after vacuum for the rolled-back row, while a committed-UPDATE control row stayed readable. At that revision `RVOOS_NOTIFY_VACUUM` (`src/transaction/recovery.h:209`) had no emitter, so the §3 remedy was not implemented. Not verified: recovery after kill -9, savepoint rollback, and the release build. This establishes the defect at that revision only, not at later heads. Evidence: [CBRD-27881 survey report, DF-03](../../../my-cubrid-docs/cbrd-27881/CBRD-27881-oos-refactoring-candidates_dcbf09e_claude.md) and the 2026-11-03 comment on [CBRD-27237](https://jira.cubrid.org/browse/CBRD-27237).

Canonical §3 removes the defect mechanism through the postponed notification (ADR-0008 A', accepted 2026-11-05) and removal of forward-walk deletion. An engine implementation of that remedy, committed 2026-11-05, is carried by draft PR #8434 and not merged ([ADR-0008 entry](#adr-0008-reclaim-after-finality)). The design is an accepted remedy, not proof of completed implementation or an assertion that later branches still have the defect. Verify the target revision before carrying the historical data-loss/merge-gate finding forward. Supporting [historical issue report](../../../my-cubrid-jira/issues/CBRD-27237-oos-forward-walk-rollback-delete_725a32c_claude.md).

## CBRD-26786: Empty-page reclaim

Observation recorded 2026-08-28: PR #7617 head `8ba9b5398` implemented the accepted reclaim invariant, including reviewer fixes R3/R4/B1; the context said merge to `feat/oos` was pending. It included the non-numerable migration, skipped page reclaim for legacy numerable files, and removed dead `oos_remove_page`. Vacuum fed batch candidates after unfixing the home page; LSA/growth gates covered deferral and eager/SA pages. Required invariant: canonical [§4](../../OOS-CONTEXT.md#empty-page-reclaim-invariant-cbrd-26786-accepted-2026-08-28).

The later identity repair refined touched-page candidates to actually emptied pages, once each; its report says reclaim gates/sweep/deallocation were unchanged. Read the [CBRD-26950 entry](#cbrd-26950-identity-stamp-repair) for that report's date/head. Neither snapshot proves today's integration state. ADR-0008 (accepted 2026-11-05) removed the LSA gate; its implementation status is in the [ADR-0008 entry](#adr-0008-reclaim-after-finality).

Observation 2026-11-05 under [ADR-0009](../adr/0009-reclaim-empty-pages-before-growth-not-while-idle.md): CBRD-26659 testcases `churn_abort_retry`, `churn_insert_delete`, `churn_insert_update_delete`, `churn_restart`, and `snapshots_reclaim` (private-ex `tc/pr-8128`, disabled under `disabled/`) failed at engine `e3589ae42` and testcase `01df2600a` on a 20-second idle page-count drop, which ADR-0009 no longer requires. Their oracle is being changed to reuse before growth; no native run of the changed oracle exists yet. At `feature/oos-merge` `d52b1889e`, only `file_destroy` and the `file_create` failure path release a permanent file's sectors.

## CBRD-26831: Page enumeration

Observation 2026-07-02: `oos-m2-all-plans-experimental` created `FILE_OOS` with `is_numerable=false` and converted sync/stats to `oos_collect_data_page_vpids` with `OLD_PAGE_MAYBE_DEALLOCATED` plus a `PAGE_OOS` type check. ADR-0001's skipped-page counter was not yet added; testcase verification/merge was pending. No exact experimental head was recorded. OOS had been numerable through `4ddbc7c`.

Later integration evidence belongs to [CBRD-26786](#cbrd-26786-empty-page-reclaim); neither snapshot closes the observability gap without verification. Required enumeration: canonical §2; rationale: [ADR-0001](../adr/0001-oos-page-enumeration-non-numerable.md).

## CBRD-27057: Four-record physical target

Snapshot dated 2026-09-22, carried in context `0eab7df`: draft PR #7462 implemented the physical target for trigger/stop, excluded `PRM_ID_HF_UNFILL_FACTOR`, and added target/boundary/unfill-independence coverage. PR #7990 head `7008beee0` on `feature/oos-merge` still used raw `DB_PAGESIZE/4`; that implementation was not integrated. JIRA was recorded Resolved/Fixed despite the draft remaining open/dirty; no draft head was recorded. Workflow state does not prove integration. Required formula: canonical §1.

Source verified 2026-11-05 at `feature/oos-merge` `d52b1889e`: `heap_attrinfo_determine_disk_layout` still compares the record with `DB_PAGESIZE / 4` for the trigger and the stop.

## CBRD-26912: Inline preference

Record dated 2026-09-22, added to context 2026-10-08: `STORAGE PREFER_INLINE` is accepted 11.5 merge scope. The context records PR #7334 merged into `feat/oos` as `4523843d1` on 2026-06-29 and JIRA Resolved/Fixed for target `guava`. This corrects “proposed — NOT yet merged.” It is a carried merge/workflow observation, not a new live lookup; required behavior is canonical §1.

## CBRD-27259: Forced inline storage

Implemented 2026-11-05 as commit `e19d8c613` on branch `CBRD-27259-storage-force-inline`, based on `feature/oos-merge` `d52b1889e`. Draft PR #8416 opened the same day; the commit was not integrated then. Required behavior is canonical [§1](../../OOS-CONTEXT.md#per-column-storage-policy-cbrd-26912-cbrd-26067-cbrd-27259).

At that commit, `heap_attrinfo_determine_disk_layout` leaves `OR_ATTRIBUTE_OOS_STORAGE_FORCE_INLINE` values out of the demotion candidates. `do_resolve_oos_storage_flag` maps the clause and the column type to the persisted flag for CREATE, ADD, MODIFY, and CHANGE. Chain reuse (CBRD-27230) is not implemented there, so every UPDATE lays out all values again.

The author's debug-build run on 2026-11-05 passed `test_oos_sql_storage` (40 tests) and all 13 OOS SQL GoogleTest binaries (175 tests). An SA `unloaddb`/`loaddb` round trip kept the `FORCE_INLINE` clause and kept an 8000B `FORCE_INLINE` value inline after load. HA replication and crash recovery were not run.

Commit `9ae07b949` (2026-11-05, local, after the PR #8416 head `e19d8c613`) reports a non-OOS `REC_BIGONE` with `ER_HEAP_BIGONE_WITHOUT_OOS` (-1393 at that commit) in `heap_attrinfo_transform_to_disk_internal`, right after the OOS+bigone rejection. It replaced the unpushed `aa951eebf`, which used warning severity. `heap_oos_warn_bigone_without_oos` sets a notification between `er_stack_push` and `er_stack_pop`. The author's debug-build runs passed all 13 OOS SQL GoogleTest binaries (178 tests) at `aa951eebf`, and `test_oos_sql_storage` (43 tests) and `test_oos_sql_bigone` (4 tests) at `9ae07b949`. In an SA scratch database with default parameters, a 17000B `BIT(136000)` insert logged one -1393 notification and an OOS-backed 17000B insert logged none.

## CBRD-26067: Forced outline

Source verified 2026-11-05 at `feature/oos-merge` `d52b1889e`: `STORAGE FORCE_OUTLINE` persists `SM_ATTFLAG_OOS_FORCE_OUTLINE`. `heap_attrinfo_determine_disk_layout` selects every non-NULL `FORCE_OUTLINE` value larger than 24B before the record gate, then demotes the remaining candidates as usual. This matches the CBRD-26067 issue's target behavior, whose 16B stub size is superseded by the 24B stub. A cache-first JIRA lookup on 2026-11-05 showed CBRD-26067 Resolved/Fixed for `guava`. The behavior became an accepted requirement in canonical [§1](../../OOS-CONTEXT.md#per-column-storage-policy-cbrd-26912-cbrd-26067-cbrd-27259) on 2026-11-05.

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

Observation 2026-10-27, under [ADR-0007](../adr/0007-run-deferred-cdc-regressions-in-qa-regression-only.md): private-ex PR #4210 (branch `tc/pr-7990`, head `75a02020e`) was open and moved `cbrd_27064`/`cbrd_27075` under `shell/_25_unstable/_37_elderberry/cbrd_23842_cdc/bug/`. Engine PR #7990 head `dcbf09e` excludes `_25_unstable` from gha-ci `test_shell`. Neither establishes that #4210 merged or that the QA regression ran the cases.

## CBRD-26357: Storage-format boot check

CBRD-26357 is the OOS epic under which PR #7990's commits are filed. Required behavior is canonical [§5](../../OOS-CONTEXT.md#storage-format-boot-check-adr-0006); decision and alternatives are in [ADR-0006](../adr/0006-reject-pre-stamp-databases-at-boot.md).

Source verified 2026-10-27 at PR #7990 head `dcbf09e4f7fd02ff9c8fc6493ec8887fc2919d67` (commits `1e8701b4f`, `d8ed97f77`): `disk_check_storage_format` runs in `boot_restart_server` right after `boot_mount` of volume 0 and before `dwb_load_and_recover_pages` and `log_initialize`; `xboot_emergency_patch` runs it after its mount; `boot_remove_all_volumes` has no check. `ER_BO_INCOMPATIBLE_STORAGE_FORMAT` is -1392 and `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` is -1388 at this head. `diagdb` prints `storage_format`; static asserts pin its file offset (140) and the `PAGE_TYPE`/`PERF_PAGE_TYPE` pairs.

The author's verification on 2026-10-27, recorded in the [review workspace](../../../../temp/pr7990-review-5662427700/TODO.md), reports: on a database created by a `develop` debug build, the pre-guard PR engine aborted on the page-type assert in `pgbuf_check_page_ptype_internal`; with the guard, `csql -S`, `checkdb`, `upgradedb`, and server start were refused with -1392, and `deletedb` succeeded; ctest 42/42 passed, including `test_oos_storage_format_guard`, built from `1e8701b4f` plus the then-uncommitted review repair. These runs predate head `dcbf09e` and were not repeated for this documentation change.

## ADR-0008: Reclaim after finality

No issue key; the engine work is filed under CBRD-27781 and CBRD-27237. Required behavior: canonical [§2](../../OOS-CONTEXT.md#multi-chunk-oos-chain), [§3](../../OOS-CONTEXT.md#update-ownership-and-chain-reuse-cbrd-27230), and [§4](../../OOS-CONTEXT.md#vacuum--oos), from [ADR-0008](../adr/0008-reclaim-oos-chains-after-the-delete-is-final.md), proposed 2026-11-03 and accepted 2026-11-05 by the team lead (confirmation reported by the OOS owner).

Source verified 2026-11-03 at `feature/oos-merge` `dcbf09e4f7fd02ff9c8fc6493ec8887fc2919d67`. The code follows the [rules before ADR-0008](design-history.md#reclaim-before-adr-0008), not the accepted design. The last column records the 2026-11-05 local implementation below:

| ADR-0008 requirement | Observation at `dcbf09e4f` | 2026-11-05 local implementation |
| --- | --- | --- |
| A chunk delete has no undo | `oos_log_delete_physical` appends `RVOOS_DELETE` with the whole record as undo (`src/storage/oos_file.cpp:3221`); its undo `oos_rv_redo_insert` writes it back with `spage_insert_for_recovery` | Implemented, pending verification and commit: `RVOOS_DELETE` is redo-only |
| Reclaim intents and the reclaimer | `vacuum_heap_record` deletes chunks inside its sysop through `vacuum_heap_oos_delete_within_sysop`; the forward-walk deletes inside `vacuum_forward_walk_oos_delete_atomic`; eager cleanup calls `oos_delete` inside the user transaction | Implemented, pending verification and commit: `RVOOS_RECLAIM_POSTPONE`; REMOVE and eager cleanup record intents |
| Postpone notification | `RVOOS_NOTIFY_VACUUM` has no emitter or consumer (`src/transaction/recovery.h:206-209`); the forward-walk is called from `vacuum_process_log_block` (`src/query/vacuum.c:3619`, `:3764`) | Implemented, pending verification and commit: `RVOOS_UPDATE_DROP_POSTPONE` emits, vacuum consumes; forward-walk removed |
| Next link with stamp, continuation fix tolerant of deallocation | 24B header; `oos_delete_chain` compares only the head stamp (`oos_file.cpp:3346-3352`) and fixes continuation pages with plain `pgbuf_fix` (`:3305`) | Implemented, pending verification and commit: 32B header, link stamps |
| No LSA reclaim gate | The gate is implemented (`oos_reclaim_lsa_gate_passes`, `oos_file.cpp:1516`) | Implemented, pending verification and commit: gate removed |

The remote head had moved to `f67f2f692` when this entry was written; that head was not reverified. Design evidence is model-only: [decision checks](../../../my-cubrid-docs/oos/reclaim-decisions.md) at documentation commit `554356e` (137 TLC checks). At that date no engine change, build, or performance measurement existed for this decision.

**Local implementation 2026-11-05 (Work742; committed locally, not pushed or merged).** Engine branch `CBRD-27781-postpone-commit` over `feature/oos-merge` `d52b1889e`: `62d0b35b6` (the reclaim design) and `3e8072f56` (a `log_do_postpone` fix it depends on). Debug OOS ctest 49/49 passed at `3e8072f56`. Observed in that branch:

- Recovery indexes in the OOS block: `RVOOS_DELETE` (137) is redo-only. `RVOOS_NOTIFY_VACUUM` (140) has an emitter and a consumer; it is an MVCC undo record whose undo is a no-op. New logical postpones `RVOOS_RECLAIM_POSTPONE` (142) and `RVOOS_UPDATE_DROP_POSTPONE` (143). `RVHF_DELETE_NEWHOME_NOTIFY_VACUUM` is removed: the relocated forward delete is a plain `RVHF_DELETE` again, as on `develop`. `vacuum_forward_walk_reclaim_oos` is deleted. These are pre-merge format changes under ADR-0008 decision 6: storage-format revision stays 1; recreate pre-merge databases.
- Explicit MVCCID: `log_append_mvcc_undo_data_with_mvccid` appends the notification under the UPDATE's MVCCID. The vacuum block's `oldest_visible_mvccid` is lowered to that MVCCID when needed; only debug sanity checks read it, and `vacuum_recover_lost_block_data` already takes the minimum. The notification's vacuum-info VFID is the heap file, so a dropped table skips it. The UPDATE records the heap file, not the OOS file: it holds heap data pages and must not fix the heap header page there, so vacuum's consumer, which holds no page, resolves the OOS file from the heap header.
- Postpones must all run. `log_do_postpone`, the path of a commit whose postpones overflow the postpone cache and of restart recovery, skipped a postpone at the last parent LSA of a nested system operation that started right after it. A bulk UPDATE lost the notification of its first dropped chain this way when an OOS page allocation followed, leaking that chain; `3e8072f56` fixes the comparison. The same comparison exists on `develop`.
- Restart recovery reruns an unfinished postpone. A rerun of the UPDATE-drop postpone may append a duplicate notification; its reclaim finds the chains gone and skips.
- Fail-stop: postpone handlers disable interrupt checks while reclaiming, so a user cancel cannot become a fail-stop.
- Reclaimer: `oos_delete` (identity-checked head, link stamps, tail first). Pages it empties feed the vacuum fast path from REMOVE (a scoped emptied-page sink around the sysop commit) and from the notification consumer (Work818 F3; ADR-0009 consequence 2). Eager reclaims have no fast path; the growth-gate sweep covers them.
- LSA reclaim gate removed (horizon sampling, rollback-CLR equality case). `OOS_RECLAIM_DEFERRED` now means only that the phase-2 WRITE fix was transiently unavailable.
- Eager skip diagnostics (`ER_HEAP_OOS_EAGER_CLEANUP_SKIPPED`) are emitted when the commit runs the reclaim, with op tag "commit".

Still open at that date: CBRD-27858 (heap forward slot; separate, not closed by ADR-0008); CBRD-27925 READ-latch hint loss (ADR-0009 consequence 2); the decision-7 performance measurement; CBRD-27230 chain reuse; a native database reproduction for CBRD-27925 (separate approval, Work790).

**Draft PR 2026-11-06 (successor observation; the 2026-11-05 evidence above is retained).** Draft PR CUBRID/cubrid#8434, created 2026-11-06, carries the branch: base `feature/oos-merge` (merge base `d52b1889e`), head `2e32517bb9ee4690f49907a1c0a4b90786917008`, not merged. A source review of `3e8072f56` ([report](../../../my-cubrid-docs/cbrd-27781/code-review-pr8434-3e8072f/report.md)) led to `6ac2d7de6`, `9406a0f71`, and `2e32517bb`; the report records findings R1–R5, R9, and R10 as fixed, R6, R7, and R8 as open, and debug OOS ctest 52/52 at `2e32517bb`. gha-ci run 42169072318 built `3e8072f56` and passed. Run 42189034435 builds `2e32517bb`; it completed with success at 2026-11-06 11:43 UTC (checked 2026-11-11).

- Decision 7, measured 2026-11-05 at `3e8072f56` against `d52b1889e` ([report](../../../my-cubrid-docs/cbrd-27781/perf.md)): reclaim log per discarded 6000-byte value about 6.1 KB → 0.71 KB; OOS pages after UPDATE churn 3539 → 1502; vacuum drain time 0.37 s → 0.31 s, not timed per log block. INSERT and UPDATE latency were not judged: three runs on a shared 80-core machine at load average 57–60 gave overlapping ranges. A remeasurement on a quiet machine is needed.
- Decision 7 latency, remeasured 2026-11-12 ([report](../../../my-cubrid-docs/cbrd-27781/latency-8495/README.md)), release_gcc on the shared 80-core machine (load average 18–232), arms rotated through all six orders, 12 runs each: base `50619ce53`, PR head `0d9732a63`, and PR head plus CUBRID/cubrid#8495 (CBRD-28046, `6a7ca6b4a`, local cherry-pick). 3000 single-row OOS UPDATE+COMMIT: `fdatasync` 3011 / 6006 / 3006; median 12.28 / 16.22 / 11.13 s; paired fix − base median −1.43 s (within the base IQR). UPDATE churn: all timings within the handoff criterion for every arm. Cause of the PR-alone regression: `log_append_commit_postpone` flushes the log, adding one synchronous flush per committing transaction that has a postpone. The condition is met only with #8495; PR #8434 waits for #8495 to reach `feature/oos-merge` (owner decision 2026-11-12).
- R8, source verified at `2e32517bb`: a stop between `LOG_COMMIT_WITH_POSTPONE` and `LOG_COMMIT` loses the transaction's replication records, because `log_commit_local` appends them after the postpones and restart recovery's `log_complete` appends only the commit record. Recorded without a code change as ADR-0008 consequence 8, which also scopes the eager, UPDATE-drop, and REMOVE paths.

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
