# CUBRID OOS (Out-of-row Overflow Storage) — Normative Specification

> Normative specification and single source of truth for required CUBRID OOS behavior.
> Last updated: 2026-10-08 (document modification only). Implementation observations carry their own evidence dates and revisions.

## Authority and reading paths

Requirements in this file are **normative** unless explicitly marked proposed, historical, or outside the stated release scope. An accepted design is a requirement, even when an observed implementation has a conformance gap. Source code establishes behavior at that revision; JIRA establishes ticket workflow state. Neither silently changes accepted requirements.

Keep all required behavior in this canonical file and read it completely when the [OOS context loader](/home/vimkim/.agents/skills/cubrid-oos-context/SKILL.md) selects a specification-dependent task. The loader owns file override, complete-read, fingerprint, and reuse policy. Follow these additional pointers only when their condition applies:

| Read when | Reference |
|---|---|
| Comparing an engine/PR with requirements, diagnosing an issue, or checking implementation progress | [Implementation observations](docs/reference/implementation-observations.md): one maintained entry per issue, with dated revision evidence; reverify before making a current-state claim |
| Explaining a superseded rule, earlier milestone, alternative, or optimization proposal | [Design history](docs/reference/design-history.md): non-normative snapshots and proposals |
| Preparing test data or choosing regression coverage | [Test recipes](docs/reference/test-recipes.md): examples and scenarios, with expectations derived from this specification |
| Discussing CDC/flashback historical images | [Historical-value vocabulary](CONTEXT.md), [ADR-0004](docs/adr/0004-durable-oos-supplemental-images.md), and [ADR-0005](docs/adr/0005-defer-oos-history-from-the-11-5-merge.md); apply the release scope in §5 |
| Needing rationale for page enumeration, LOB eligibility, or Expand | [ADR-0001](docs/adr/0001-oos-page-enumeration-non-numerable.md), [ADR-0002](docs/adr/0002-oos-lob-locator-demotion.md), or [ADR-0003](docs/adr/0003-oos-expansion-is-opt-in.md), respectively |

The reference documents contain evidence and rationale. They do not add hidden requirements or replace a complete read of this file. Historical text in a linked report is interpreted under the accepted requirements here.

### Core Terminology

| Term | Definition |
|---|---|
| OOS-backed attribute | A row value represented by an inline stub; a schema column is only eligible |
| OOS value | Complete serialized attribute bytes, excluding chunk headers |
| OOS file / page | `FILE_OOS`; slotted data pages of `DB_PAGESIZE`; at most one file per heap |
| OOS chunk record | One slotted-page record: OOS header plus a payload fragment |
| OOS value chain | One or more chunk records holding one complete value |
| OOS OID | Physical 8B chunk OID: volid 2B, pageid 4B, slotid 2B |
| Head OOS OID | Stub's OID of chunk index 0 |
| Next-chunk OID | Header link to the following chunk |
| OOS inline stub | 24B: head OID 8B, full length 8B, packed head identity stamp 8B |
| Full length | Total serialized value length, excluding all chunk headers |
| HAS_OOS / IS_OOS | Record MVCC flag / attribute VOT flag; true iff the record contains a stub / this entry is a stub |
| OOS Expand | Record-level, eager replacement of every stub; `HEAP_GET_CONTEXT.expand_oos` → `heap_record_replace_oos_oids` |
| OOS Resolve | Attribute-level, lazy value retrieval; `heap_attrvalue_read_oos_inline` → `oos_read` |
| OOS Read | Storage-level `oos_read` reconstructs one chain; distinct from Resolve |
| OOS inline target | Aligned physical four-record heap-capacity target, independent of unfill (§1) |
| OOS Demotion | INSERT/UPDATE moves largest eligible values until the target or candidate exhaustion (§1) |
| Numerable file | Tracks allocation order for nth-page access (`file_numerable_find_nth`) |
| Bestspace sync | Tier-3 page sampling recharges hints after cache/best[] misses (§2) |
| Sector-bitmap walk | Enumerates partial/full bitmap data pages (`file_get_all_data_sectors`) rather than nth-page order |
| Mark-delete | Numerable deallocation flags a page-table entry; skipping accumulated entries makes `find_nth` O(n) per call |
| Pending-delete counter (미회수 삭제 카운터) | Per-VFID zero/non-zero growth-gate hint; full accounting/boot contract in §4 |
| Growth-gate sweep (성장 게이트 sweep) | Incremental cursor-resumed bitmap reclaim at the single growth point (§4) |
| LSA reclaim gate (LSA 게이트) | Defers empty pages that may still be undo destinations; horizon contract in §4 |

---

## 1. What is OOS?

OOS separates large variable-length attribute values from heap records into a dedicated file. The compact heap record holds inline stubs; access to small attributes avoids reading large values. A heap file has at most one lazily created `FILE_OOS` file.

### Trigger Conditions — Largest-First Demotion (CBRD-26776; physical target CBRD-27057)

At INSERT/UPDATE, `heap_attrinfo_determine_disk_layout` applies an incremental demotion policy:

1. **Record gate:** demote only when `header_size + payload_size + mvcc_extra > heap_oos_inline_target_size()`. Use the same target for the trigger and stop.
2. **Eligibility:** `is_variable && column_size > OR_OOS_INLINE_SIZE` (strictly greater than **24B**). Demotion must shrink the value's representation. This is type-agnostic, including BLOB/CLOB **locator bytes**; the external LOB payload stays in the LOB subsystem. The OOS serialization path preserves inline-path `db_elo_copy_with_prefix` semantics before writing the locator (ADR-0002).
3. **Order and stop:** consider ordinary candidates before `STORAGE PREFER_INLINE` candidates (§ below); within each group sort by size descending. Demote one at a time, subtracting `column_size` and adding 24B. Stop when the record is at or below the target or candidates are exhausted. Smaller eligible values may remain inline.
4. **Exhausted candidates:** a record may remain above the target. Keep selected values OOS-backed and apply the OOS+bigone guard below. With no candidates and no retained stubs, `has_oos` stays false; an ordinary inline record (for example 14KB) or non-OOS `REC_BIGONE` remains valid.

The PostgreSQL-style four-record physical-capacity target is:

```text
records_per_page = 4
page_capacity = heap_nonheader_page_capacity()
oos_inline_target = ALIGN_BELOW(
  (page_capacity - records_per_page * SPAGE_SLOT_SIZE) / records_per_page,
  HEAP_MAX_ALIGN)
```

`heap_nonheader_page_capacity()` excludes the slotted-page header, heap chain record, and its slot. Reserve four user-record slots before dividing, then align down. Exclude `heap_hdr->unfill_space`: this physical target is independent of heap unfill, just as PostgreSQL `MaximumBytesPerTuple(4)` excludes relation fillfactor. Page selection still obeys configured unfill; the formula is not a promise to pack four records on every page.

Current 16KB I/O layout:

```text
IO_PAGESIZE                     16,384B
DB_PAGESIZE                     16,344B (40B file-I/O reservation)
heap_nonheader_page_capacity()  16,268B
four user slots                     16B
(16,268 - 16) / 4 = 4,063B; ALIGN_BELOW(4,063, 4) = 4,060B
```

Four target-sized records fit: `4 × (4,060 + 4) = 16,256 ≤ 16,268`. The next aligned size does not: `4 × (4,064 + 4) = 16,272 > 16,268`. Neither the I/O-page quarter (4,096B) nor raw `DB_PAGESIZE/4` (4,086B) is the accepted target.

**Conservative estimate:** compare using pre-loop `header_size`, recomputed once after demotion. Payload decreases and the header cannot grow, so this is an overestimate: at a VOT BYTE↔SHORT↔INT boundary the loop may over-demote by at most one value, but cannot under-demote relative to that estimate. The final guard still requires a valid slotted-page record or rejection. Worked examples are in [test recipes](docs/reference/test-recipes.md#demotion-worked-examples); former gate/floor values are in [history](docs/reference/design-history.md#supersession-timeline).

### Per-column inline preference (CBRD-26912)

`STORAGE PREFER_INLINE` is an accepted soft hint for the CUBRID 11.5 OOS merge. Its values remain eligible but sort after ordinary candidates, descending by size within each group; demote them as a last resort when necessary. Store the setting in `SM_ATTFLAG_OOS_PREFER_INLINE`; its sole storage-policy effect is the primary sort key in `heap_attrinfo_determine_disk_layout`. Apply the ordinary OOS+bigone guard afterward.

### OOS + bigone Rejection (CBRD-26937)

OOS stubs combined with `REC_BIGONE` overflow are unsupported. Large fixed `BIT(n)`/`CHAR` or many ≤24B variable values may keep a demoted record above the bigone threshold. In `heap_attrinfo_transform_to_disk_internal`, reject **after demotion and before any OOS chain insert**:

```text
if (has_oos && heap_is_big_length(expected_size))
  er_set(ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE); return S_ERROR;
```

The error is `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` (-1375). The rejection boundary is `heap_Maxslotted_reclength` (~16KB), not the OOS inline target. OOS-backed records between the target and that boundary are valid when candidates run out. Non-OOS bigone records are unaffected. Running the gate before `heap_attrinfo_insert_to_oos` avoids orphan chains on rejection.

---

## 2. Architecture & Design

An OOS file uses slotted pages so multiple chunk records can share a page. Values larger than one page form chains; file/page hints and identity checks serve different roles.

### Record Binary Layout

```text
Heap record: MVCC header | variable offset table (VOT) | fixed columns | variable area
VOT entry: offset_value (30 bits) | RESERVED (1 bit) | IS_OOS (1 bit)
  OR_VAR_BIT_OOS = 0x1: set -> 24B stub at the offset; clear -> inline value
Stub: head OOS OID (8B) | full length (8B bigint) | identity stamp (8B packed LSA)
  OR_OOS_INLINE_SIZE = 24
MVCC flags: bit 0 insert ID; bit 1 delete ID; bit 2 prev-version LSA;
  bit 3 HAS_OOS (OR_MVCC_FLAG_HAS_OOS = 0x08); bit 4 reserved
```

MVCC header-size lookup uses only the lower three bits (`idx & 0x07`); HAS_OOS is metadata and does not change header size.

### Multi-Chunk OOS Chain

When a column value exceeds one OOS page, it's split into chunks stored as a linked list:

```
Insertion order (reverse):
  chunk_2 (tail of value) -> inserted first, next_oid = NULL
  chunk_1 (middle)        -> inserted second, next_oid = chunk_2 OID
  chunk_0 (head of value) -> inserted last, next_oid = chunk_1 OID

  Heap record's inline stub stores the head OOS OID and identity stamp of chunk_0.

Read order (forward):
  Follow chain: chunk_0 -> chunk_1 -> chunk_2 -> reassemble value

Each OOS chunk record (24-byte header followed by payload):
  total_data_length (4B) | chunk_index (4B) | next-chunk OID (8B; NULL last)
  identity_stamp (8B LOG_LSA) | payload fragment (variable length)

total_data_length is the complete OOS value length and excludes every OOS record header.
```

Each chunk stores the page LSA captured under its write latch before that insert is logged. Stamps are per chunk, not chain-wide; the stub stores only the head's stamp. Insert redo/delete undo restore the stored stamp from the logged image. Pack the stub stamp into one bigint; the header stores raw `LOG_LSA`. Recreate test databases built with older unreleased layouts and use matching install artifacts.

**Accepted identity checks (CBRD-26950):** validate the expected head stamp before returning payload or deleting a chain. Under the head latch, tolerate deallocated/retyped pages and missing/reused slots without interpreting another page type as a slotted page. Reads reject stale references with `ER_HEAP_OOS_CORRUPTED_RECORD`, rather than returning another occupant's bytes. Deletion compares identity under the same write latch that deletes the head; an absent/reused head is a clean no-op. Matching malformed/non-head references and operational failures are errors. Stub parsing, extraction, and replica fixup respect the VOT-defined field width before reading/writing the 24B stub. The stub writer checks the actual `*ptr_varvals` write position, preserving `S_DOESNT_FIT` grow-and-retry behavior.

**Accepted logging policy (2026-09-09):** stamp uniqueness across slot reuse and retry safety require logged operations. Supported no-logging bulk loads may repeat a stamp because skipped appends do not advance page LSA; callers cannot rely on stale-reference discrimination there. Check actual `log_is_no_logging`, not the startup parameter: SA `loaddb --no-logging` enables it after startup. This exception does not weaken the logged guarantee or authorize unsafe stale-reference producers; no alternative identity mechanism is selected.

**Accepted eager-cleanup policy (2026-09-09):** vacuum skips absent/reused heads silently. Eager cleanup completes DML but emits a diagnostic for skipped cleanup; successful calls leave no stray error stack. Matching malformed heads/operational failures remain errors. Repair progress has one [CBRD-26950 entry](docs/reference/implementation-observations.md#cbrd-26950-identity-stamp-repair).

### Best Page Policy (3-Tier Bestspace — CBRD-26658)

OOS file page 0 holds `OOS_HDR_STATS`: best[10] hints and space estimates, persisted as non-logged hints. The independent `OOS_BESTSPACE_CACHE` uses dual hash tables (VFID→entry, VPID→entry) and its own mutex rather than heap's `bestspace_mutex`.

```text
oos_find_best_page()
  Fix header (WRITE latch), load best[] hints
  -> global VFID cache -> best[10] circular hints
  -> fix candidate with CONDITIONAL_LATCH (zero wait)
  -> on miss, oos_stats_sync_bestspace(): sample pages (max 20%, 100-page limit)
     recharge hints/cache and retry
  -> on remaining miss, reach the single growth point through the reclaim gate (§4)
```

Fit checks compare `rec_length` directly with `spage_max_space_for_new_record`; its result already accounts for the new slot. Delete/rollback evicts stale VPID cache entries through `oos_stats_del_bestspace_by_vpid`. Recovery rediscovers free space through sync; correctness must survive lost non-logged hints. Conditional latches avoid waiting while choosing a candidate.

**Accepted enumeration (ADR-0001):** `FILE_OOS` is a non-numerable permanent file. Tier-3 sync enumerates pages with a sector-bitmap walk (`file_get_all_data_sectors`), using VPID-based resume rather than nth-page order. Install this before per-page vacuum deallocation. The bitmap is a frozen private-memory snapshot and concurrent deallocation is permitted throughout the walk:

- Fix read-only sampled pages with `OLD_PAGE_MAYBE_DEALLOCATED`; skip `ER_PB_BAD_PAGEID` and count skipped-deallocated-page observations.
- Keep the actual insert/write path on plain `OLD_PAGE`: targeting a freed page there is a bug.
- Use the file manager's bitmap metadata without adding a per-page chain or per-allocation enumeration WAL.

Rationale and rejected alternatives are in [ADR-0001](docs/adr/0001-oos-page-enumeration-non-numerable.md); implementation evidence is under [CBRD-26831](docs/reference/implementation-observations.md#cbrd-26831-page-enumeration).

---

## 3. CRUD Flows

### INSERT

`heap_insert` → `heap_attrinfo_determine_disk_layout` applies §1 demotion/rejection. Create the associated OOS file if absent, then `oos_insert` each selected value and obtain its head OOS OID plus stamp. Build the heap record with 24B stubs, per-attribute IS_OOS flags, and record HAS_OOS; insert it with `spage_insert`. Log both heap and OOS inserts when logging is enabled.

### SELECT: Resolve and Expand

Read the heap record and its flags. Attribute-layer consumers use **Resolve**:
`heap_attrinfo_read_dbvalues` → `heap_attrvalue_read_oos_inline` → `oos_read`, reconstructing only accessed OOS-backed attributes.

Raw-byte consumers require **Expand**: `heap_record_replace_oos_oids` replaces every stub and rebuilds the whole `RECDES`, gated by `HEAP_GET_CONTEXT.expand_oos`. Choose Expand when shipping bytes in client `LC_COPYAREA`, re-inserting into another heap, comparing record bytes, or parsing through `OR_BUF`. Fixed/header/CHN-only or existence checks and attribute-layer consumers use the cheap fetch.

### Visible-version fetch family (CBRD-26847)

These fetchers funnel into `heap_get_visible_version_internal`. Expand is opt-in, as accepted by [ADR-0003](docs/adr/0003-oos-expansion-is-opt-in.md):

| Function | Expands? | Consumer contract |
|---|---|---|
| `heap_get_visible_version` | No | Attribute layer / fixed / header / existence |
| `heap_get_visible_version_expand_oos` | Yes | Raw record bytes |
| `heap_scan_get_visible_version` | No | Heap scan; attribute layer resolves lazily |
| `heap_get_last_version` | No | UPDATE/DELETE latest-version fetch via attribute layer |

New callers must justify the fetch contract. The `_expand_oos` suffix signals that the resulting `RECDES` may leave the attribute layer. The caller census and unloaddb/compactdb gap are maintained under [CBRD-26847](docs/reference/implementation-observations.md#cbrd-26847-fetch-contract-census) and [CBRD-26948](docs/reference/implementation-observations.md#cbrd-26948-raw-byte-fetch-gap).

### UPDATE ownership and chain reuse (CBRD-27230)

**Accepted on 2026-08-13:** reuse existing OOS value chains for attributes **not assigned by the UPDATE statement**. Preserve their entire 24-byte stub, including head OOS OID, length, and identity stamp; reuse requires neither value comparison nor a read/reinsert of those values. Assigned attributes follow ordinary demotion and insertion, even if assigned an equal value.

**Ownership invariant:** an OOS value chain is owned by the newest logical record version that references it. Older versions hold borrowed references through their undo images. Release a dropped chain exactly once through the committing UPDATE's notification, consumed by vacuum, or through vacuum's removal of the row's last version (REMOVE path). Undo images are never a deletion source.

1. Plan reused stubs, newly inserted values, and the list of dropped chain references.
2. Write the new heap record and retain the previous record **as-is** in undo, including its stubs, for rollback and snapshot readers.
3. For committed UPDATEs, emit **`RVOOS_NOTIFY_VACUUM`** from a commit hook before `logtb_complete_mvcc`, listing `(head OOS OID, expected identity stamp)` pairs. Vacuum consumes the notification when reclamation is safe for MVCC readers. Remove the UPDATE undo-image forward-walk deletion path.
4. Use CBRD-26950 identity-checked deletion for vacuum retry idempotency. Identity checks alone cannot decide whether a shared chain was dropped: borrowed and live stubs can have the same stamp.
5. Include a marker item per reused attribute in replication and replica-side fixup; preserve replica-local OOS references (§4).

DELETE's REMOVE path and the SA/non-MVCC eager path keep their roles. Eager cleanup compares old and new references so a chain retained by the post-image survives. Commit notifications do not authorize deleting borrowed chains while older snapshots can still read them.

This supersedes the M1 always-new-chain/exclusive-version ownership rule and the older sharing-check proposal. Acceptance does not establish implementation completion. See the [CBRD-27230 evidence entry](docs/reference/implementation-observations.md#cbrd-27230-update-chain-reuse) and [historical M1 flow](docs/reference/design-history.md#m1-update-and-vacuum).

### DELETE

In MVCC mode, `heap_delete` sets the delete ID and writes the record back to the heap page. Retain stubs and their chains for older readers until vacuum. Do not Resolve OOS values in place: expansion may exceed the 16KB heap-page limit. The SA/non-MVCC eager path retains its separate cleanup role.

---

## 4. Recovery, Replication & MVCC

### Recovery & Replication Invariants

1. **WAL completeness:** with logging enabled, log every OOS insert/delete and recover the last committed transaction state. The §2 no-logging exception omits recovery and stamp-uniqueness guarantees.
2. **Undo correctness:** UPDATE/DELETE undo retains the previous record as-is with its OOS inline stubs, rather than expanded values. Rollback restores that record with live referenced chains. Snapshot reads reconstruct it via `prev_version_lsa` → undo `RECDES` → `oos_read`; keep borrowed chains alive until MVCC-safe reclamation. Undo is a read/rollback source, never an OOS deletion source.
3. **No orphan chains after UPDATE:** use the accepted §3 ownership and commit-conditional notification contract for dropped chains; retain reused chains. Remove the historical forward-walk mechanism rather than assuming old/new references are disjoint.
4. **DELETE safety:** retain stubs and chains until vacuum can safely remove the row's last version. Do not Resolve OOS values in place during heap DELETE.
5. **Replication completeness:** supply enough information for the replica to reconstruct equivalent values and correct **replica-local** references. Master and replica OOS OIDs may differ.
6. **File association:** each heap file has at most one OOS file; its VFID is stored in the heap header.

### Replication References

The replica performs its own `oos_insert` for newly written values and fixes the heap stub with its own head OOS OID and identity stamp; master physical references must not become replica storage references. The accepted UPDATE-reuse design adds per-attribute reuse markers and replica-side fixup using the replica's retained chain. Value equality is the guarantee, not OID equality.

### Vacuum + OOS

In MVCC mode, UPDATE/DELETE retain chains needed by old readers; cleanup occurs only after visibility permits it. The accepted cleanup sources are committed UPDATE notifications for dropped chains and REMOVE for a row's last version. REMOVE deletes within the caller's sysop; notification cleanup uses atomic system operations. Chunk deletes are logged so a mid-delete failure/recovery rolls back or replays the appropriate atomic operation. The SA/non-MVCC eager path reclaims unreferenced chains synchronously and follows §2 diagnostic policy.

Deleting a **chunk record** frees a slot. Reclaiming an empty **page** returns it to the file manager and is a separate requirement below. The old forward-walk implementation and its dates/functions live in [design history](docs/reference/design-history.md#m1-update-and-vacuum), with issue-specific progress in [CBRD-26668](docs/reference/implementation-observations.md#cbrd-26668-vacuum-integration) and [CBRD-27237](docs/reference/implementation-observations.md#cbrd-27237-rollback-and-vacuum).

### Empty-Page Reclaim Invariant (CBRD-26786; accepted 2026-08-28)

Every fully emptied OOS data page is eventually returned to the file manager. An OOS file reserves a new sector only when no safely reclaimable empty page exists **right now**. This is an invariant, including the SA/non-MVCC eager path; cache coverage or a best-effort vacuum optimization is insufficient.

Three mechanisms deliver the invariant:

- **Vacuum fast path:** after a committed delete batch and after unfixing the home heap page, feed candidate OOS pages once per heap-page batch to `oos_reclaim_empty_pages`. Use a two-phase check to revalidate emptiness before deallocation. Identity repair refines the candidate list to pages actually emptied by deletion, each reported once. Freeing chunks does not itself free their pages.
- **LSA reclaim gate:** for each reclaim call, sample the horizon as the minimum head LSA of active regular transactions and active system tdes, clamped to the pre-scan append LSA. Deallocate an empty page only when its page LSA is older. Otherwise classify it **deferred**: abort by a still-active deleter may need to undo chunk deletes into that page. It becomes reclaimable when the writer finishes.
- **Growth-gate sweep:** at the file's single growth point (`oos_alloc_page_with_reclaim`), use a per-VFID, non-evicting in-memory side map `{pending_deletes, swept_this_boot, sweep_cursor}` under the bestspace mutex. The pending-delete counter records deletes not yet accounted for by a completed sweep lap; only zero/non-zero matters. Pending deletes, or the boot rule after lost hints, arm an incremental sector-bitmap sweep (`oos_reclaim_sweep_step`) resumed from the saved cursor. Stop at the first reclaimed page, which the following `file_alloc` immediately reuses. A lap reclaiming nothing settles the counter; deferred pages keep it armed while growth proceeds. Hint loss costs one boot-rule lap, never a page; bitmap and on-disk emptiness are authoritative.

The [ADR-0001 non-numerable enumeration contract](#best-page-policy-3-tier-bestspace--cbrd-26658) is the prerequisite. Revision-specific PR evidence and historical implementation caveats are maintained under [CBRD-26786](docs/reference/implementation-observations.md#cbrd-26786-empty-page-reclaim).

---

## 5. File Lifecycle, Security & Release Scope

### File Lifecycle and TDE

Destroy the associated OOS file when its heap is destroyed on DROP TABLE (`oos_remove_file`). For TDE-enabled classes, apply the class encryption algorithm to an existing OOS file and to a lazily created OOS file **before publishing its VFID**. OOS pages must not leak plaintext. BLOB/CLOB demotion moves locator bytes only; OOS chunk deletion does not delete external LOB files, whose lifecycle remains with the LOB layer (ADR-0002).

### CDC/Flashback: Deferred from the 11.5 Merge

**Accepted on 2026-09-22, ADR-0005:** defer the complete CBRD-26939 OOS-history change from PR #7990 and the CUBRID 11.5 OOS merge: durable supplemental images, reader behavior, compatibility changes, activation machinery, new CDC error handling, and the associated CCI update. Keep disk compatibility **11.5**. Introduce neither an artificial 11.6 disk level nor a per-database activation state to preserve unreleased feature artifacts. Recreate pre-release feature databases/logs when storage/log formats change; those artifacts have no cross-revision compatibility guarantee.

Keep `cbrd_27064` and `cbrd_27075` enabled and visibly failing until the deferred work is redesigned. Their failures do not justify exclusion, masking, or expectation rewrites to make PR #7990 green. Close engine PR #7897 and CCI PR #112 while preserving history, branches, and research; retain PR #7990's testcase PRs for independent non-CDC expectation corrections. The unrelated intermittent `issue_11202_temp_volume_create` failure stays outside this decision.

The PR #7990 correction uses an additive revert and ordinary fast-forward commits. Its decision forbids force-push, amend, rebase, and history rewrite for that correction. After local verification/review, run full PR CI and distinguish the two expected CDC failures from unrelated failures. This is PR #7990 scope, not a Git policy for this documentation repository.

[ADR-0004](docs/adr/0004-durable-oos-supplemental-images.md) retains durability analysis as evidence and a **candidate direction**. Its compatibility/activation contract is superseded for this merge. Encoding, publication ordering, reader failure behavior, and compatibility enforcement require future redesign; the earlier durable-image direction is not an accepted implementation contract. For CDC/flashback discussion, also read [CONTEXT.md](CONTEXT.md) and [ADR-0005](docs/adr/0005-defer-oos-history-from-the-11-5-merge.md).

### Deferred Capabilities and Proposals

The accepted OOS design uses separate value chains per attribute and has no OOS-layer compression requirement, PEEK mode, cross-row/content-equality deduplication, or across-page compaction. Ordered page-fix/deadlock work and broader compression remain future work. Proposed multi-attribute storage, section latches, and CHAR eligibility changes are not accepted requirements. See [design history](docs/reference/design-history.md#proposals-and-deferred-optimizations) for their rationale and dates; UPDATE-unassigned chain reuse is already accepted in §3.

---

## Writing Conventions

- Use the glossary's terms precisely: **OOS OID** names a physical chunk OID, **head OOS OID** names the stub's OID, and **OOS inline stub** names the full 24B representation rather than a pointer/OID.
- Distinguish **OOS value**, **chunk record**, and **value chain**. Use **OOS-backed attribute** for a row value; a schema column is eligible and may remain inline. Use **OOS subsystem** for the whole feature.
- Keep **Expand** (record), **Resolve** (attribute), and **Read** (storage) distinct. Avoid “bulk externalization” for accepted demotion, “indexed/ordered file” for numerable, “full scan/refill” for bestspace sync, “data-sector scan” for sector-bitmap walk, and “full sweep” for cursor-resumed reclaim.
- Describe the gate as the **PG-style four-record heap target**, derived by `heap_oos_inline_target_size()` independently of unfill; state eligibility as `> OR_OOS_INLINE_SIZE` (24B). Former `DB_PAGESIZE/8`/512B and raw quarter-page rules are historical.
- Use the accepted [UPDATE ownership invariant](#update-ownership-and-chain-reuse-cbrd-27230); label exclusive-version ownership as historical M1.
- Add a space between inline code and Korean text: `` `oos_read` 는 ``.
- Label implementation, proposal, and history; accepted design does not establish implementation or merge completion. Cite dated observations for progress claims.
