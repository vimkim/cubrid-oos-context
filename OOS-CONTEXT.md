# CUBRID OOS (Out-of-row Overflow Storage) — Normative Specification

> Normative specification and single source of truth for CUBRID OOS. The `feat/oos` branch is an incomplete implementation being brought into conformance before merge to `develop`.
> Last updated: 2026-07-13 | Implementation branch: `feat/oos` | Milestone: M2 (the only active milestone — all remaining OOS work; M3 & M4 cancelled)
> **Spec note (2026-07-13):** The fixed `DB_PAGESIZE/4` record gate is superseded by a PostgreSQL-style four-record physical-capacity target. The target subtracts heap-page fixed overhead and four slot entries, divides by four, and aligns down; like PostgreSQL TOAST, it does **not** include heap unfill/fillfactor policy. With the current 16KB I/O page layout the target is 4,060B. Tracked by CBRD-27057; see §1.
> **Historical note (2026-06-18):** CBRD-26776 (PR #7158) introduced PG TOAST-style largest-first demotion, changed the then-current gate from 2KB to fixed 4KB, lowered the profitable demotion threshold to `> OR_OOS_INLINE_SIZE`, and stopped after reaching the target instead of externalizing every eligible value. The fixed 4KB gate is now superseded; largest-first ordering and the 16B profitability rule remain normative.

### Requirement Status

- **Normative** (default): required OOS behavior. Implementation differences are conformance gaps.
- **Proposed**: not accepted and not required.
- **Implementation status — non-normative**: dated progress or temporary state on `feat/oos` or an experimental branch.
- **Historical**: superseded behavior retained only for context.

### Current Implementation Status — Non-normative

- `feat/oos` is incomplete and is expected to converge on this specification before merge to `develop`.
- CBRD-27057 replaces the raw `DB_PAGESIZE/4` gate. The current working-tree implementation uses the 4,060B physical target for both the trigger and demotion stop, excludes `PRM_ID_HF_UNFILL_FACTOR`, and has target/boundary/unfill-independence coverage.
- Temporary crash-on-invariant instrumentation marked `REVERT BEFORE MERGE` remains in `heap_file.c` and `vacuum.c`. It is a merge-readiness item, not required OOS behavior.
- Experimental-branch implementations do not become normative or implemented-on-`feat/oos` merely because they are described here; verify their merge status explicitly.

## Quick Reference

| Concept | Detail |
|---------|--------|
| OOS trigger | record > the PostgreSQL-style four-record heap target (`heap_oos_inline_target_size()`; 4,060B with the current 16KB I/O page layout) → demote largest variable values (value strictly greater than `OR_OOS_INLINE_SIZE` = 16B) one-by-one until the record reaches the target or candidates are exhausted. The target accounts for physical heap-page/slot overhead but intentionally excludes heap unfill, matching PostgreSQL's separation of TOAST threshold and fillfactor. Type-agnostic — BLOB/CLOB locators demote like any variable value (ADR-0002) |
| OOS file type | `FILE_OOS`, lazily created; at most one per heap file |
| OOS inline stub | 16-byte inline reference: head OOS OID (8B) + full length (8B) |
| HAS_OOS flag | MVCC header bit 3 (`OR_MVCC_FLAG_HAS_OOS = 0x08`) |
| IS_OOS flag | VOT entry bit 0 (`OR_VAR_BIT_OOS = 0x1`) |
| Key sources | `heap_file.c`, `oos_file.cpp`, `object_representation.h`, `object_representation_constants.h` |
| Branch | `feat/oos` |
| JIRA | CBRD-26517 (main), CBRD-26458 (unloaddb perf), CBRD-26516 (redundant oos_read), CBRD-26637 (error handling), CBRD-26658 (3-tier bestspace), CBRD-26668 (vacuum integration, done), CBRD-26776 (largest-first demotion, done), CBRD-27057 (four-record physical target), CBRD-26937 (OOS+bigone rejection), CBRD-26950 (vacuum slot-reuse data loss — CRITICAL), CBRD-26830 (TDE plaintext leak — security), CBRD-26912 (STORAGE PREFER_INLINE, proposed) |

### Core Terminology

| Term | Definition |
|------|-----------|
| OOS-backed attribute | An attribute value whose heap representation is an OOS inline stub |
| OOS value | The complete serialized attribute value, excluding OOS record headers |
| OOS File | `FILE_OOS` type file; at most one per heap file |
| OOS Page | Slotted page within OOS file (size = DB_PAGESIZE) |
| OOS chunk record | One physical slotted-page record containing an OOS record header and a payload fragment |
| OOS value chain | One or more OOS chunk records containing one complete OOS value |
| OOS OID | The 8-byte physical `OID` of one OOS chunk record (volid 2B + pageid 4B + slotid 2B) |
| Head OOS OID | The OOS OID stored in an inline stub; identifies chunk index 0 of the value chain |
| Next-chunk OID | The OOS OID in an OOS record header that links to the following chunk record |
| OOS inline stub | The 16-byte heap representation of an OOS-backed attribute: head OOS OID (8B) + full length (8B) |
| Full length | Total serialized OOS value length across all chunks, excluding OOS record headers |
| HAS_OOS flag | Record-level MVCC header flag — true iff the heap record contains at least one OOS inline stub |
| IS_OOS flag | Per-attribute VOT flag — true iff this variable-area entry contains an OOS inline stub instead of an inline value |
| OOS Expand | **Record-level, eager**: replace every OOS inline stub with its value, rebuilding the whole record (`HEAP_GET_CONTEXT.expand_oos` → `heap_record_replace_oos_oids`). For callers that consume raw recdes bytes. _Avoid_: "resolve" for this. |
| OOS Resolve | **Attribute-level, lazy**: obtain one OOS-backed attribute's logical value on demand (`heap_attrvalue_read_oos_inline` → `oos_read`). _Avoid_: "expand" for this. |
| OOS Read | **Storage-level**: `oos_read` follows one OOS value chain from its head OOS OID and reconstructs the complete OOS value. Do not use as a synonym for attribute-layer Resolve. |
| OOS inline target | Maximum aligned heap recdes length for which four records plus four slot entries physically fit on a non-header heap page. It is derived from `heap_nonheader_page_capacity()` and intentionally excludes heap unfill, like PostgreSQL `MaximumBytesPerTuple(4)` excludes relation fillfactor. |
| OOS Demotion | **Write-time, trigger-side**: at INSERT/UPDATE, when the record exceeds the OOS inline target, move the *largest* eligible variable values to OOS one-by-one until the record reaches that target or candidates are exhausted — PG TOAST-style (`heap_attrinfo_determine_disk_layout`, CBRD-26776). Not every eligible value is externalized; smaller ones may stay inline. _Avoid_: "bulk externalization" (that was the old M1 behavior). |
| Numerable file | A file that records page-allocation order so callers can fetch the nth page (`file_numerable_find_nth`). OOS was created numerable through `4ddbc7c`; the ADR-0001 non-numerable migration is implemented on `oos-m2-all-plans-experimental` (2026-07-02, pending verification/merge). _Avoid_: indexed file, ordered file |
| Bestspace sync | Tier-3 fallback that walks OOS data pages once to recharge free-space hints when the cache and best[] both miss. _Avoid_: full scan, refill |
| Sector-bitmap walk | Enumerating a file's data pages from its partial/full sector bitmap (`file_get_all_data_sectors`) instead of a page chain or page numbering — the planned OOS enumeration (ADR-0001). _Avoid_: data-sector scan |
| Mark-delete | A numerable-file dealloc that flags a user-page-table slot as deleted instead of removing it; `find_nth` then skips it. Accumulation drives `find_nth` into an O(n) per-call slow path |

---

## 1. What is OOS?

**OOS (Out-of-row Overflow Storage)** separates large variable-length columns from heap records into dedicated OOS files to reduce unnecessary disk I/O. Instead of reading a full 3KB record for a 4-byte ID, only small columns are read from the heap.

```
AS-IS:
[ id | name | big_text (4.5KB) | big_blob (4.5KB) ]  <- entire heap record (~9KB > 4KB)

TO-BE:
[ id | name | OOS inline stub (16B) | OOS inline stub (16B) ] <- compact heap record
                  |                |
                  v                v
           [ big_text ]     [ big_blob ]             <- OOS file (separate)
```

### Trigger Conditions — Largest-First Demotion (CBRD-26776; physical target CBRD-27057)

OOS demotion is a two-stage, **incremental** process (`heap_attrinfo_determine_disk_layout`, `heap_file.c`). It mirrors PostgreSQL's tuple-toaster main loop, minus compression:

1. **Record gate**: only externalize if `header_size + payload_size + mvcc_extra > heap_oos_inline_target_size()`. The same target is used for loop termination. With the current 16KB I/O page layout it is 4,060B. CUBRID's `DB_PAGESIZE` is 16,344B after the 40B file-I/O reservation, so neither the I/O-page quarter (4,096B) nor `DB_PAGESIZE/4` (4,086B) is the correct physical target.
2. **Eligibility**: an attribute value is a candidate iff `is_variable && column_size > OR_OOS_INLINE_SIZE` (strictly greater than 16B) — i.e. its value is bigger than the 16-byte OOS inline stub (head OOS OID + full length) that replaces it, so demoting it actually shrinks the record. The rule is **type-agnostic**: BLOB/CLOB values are eligible too (ADR-0002) — the in-row value is the ELO locator string, and only those locator bytes go to OOS (the LOB payload stays in external LOB storage). LOB copy semantics are preserved on the OOS path: `heap_attrinfo_dbvalue_to_recdes` performs the same `db_elo_copy_with_prefix` step as the inline writer before serializing.
3. **Largest-first loop**: sort candidates by size **descending**, then demote one at a time (subtracting `column_size`, adding back 16B per demote), and **`break` as soon as the record drops to ≤ the OOS inline target**. If candidates are exhausted first, the record may remain above the target; possible values stay OOS-backed and the later OOS+bigone guard either accepts the record as an ordinary slotted-page record or rejects it if it would require `REC_BIGONE`. If there are no eligible values, `has_oos` remains false and an ordinary inline record (for example 14KB) or non-OOS `REC_BIGONE` remains valid.

The target follows PostgreSQL's `MaximumBytesPerTuple(4)` policy:

```text
records_per_page = 4
page_capacity = heap_nonheader_page_capacity()

oos_inline_target = ALIGN_BELOW(
  (page_capacity - records_per_page * SPAGE_SLOT_SIZE)
    / records_per_page,
  HEAP_MAX_ALIGN)
```

`heap_nonheader_page_capacity()` already excludes the slotted-page header, the heap chain record, and its slot. The formula then reserves four user-record slots before dividing. It intentionally does **not** subtract `heap_hdr->unfill_space`: PostgreSQL's TOAST threshold likewise does not include relation fillfactor; fillfactor/unfill remains an independent page-selection policy.

With the current 16KB layout:

```text
IO_PAGESIZE                          16,384
DB_PAGESIZE                          16,344
heap_nonheader_page_capacity()       16,268
four user SPAGE_SLOT entries             16
(16,268 - 16) / 4                    4,063
ALIGN_BELOW(4,063, 4)                4,060
```

Therefore four target-sized recdes plus their slots physically fit (`4 × (4,060 + 4) = 16,256 ≤ 16,268`), while the next aligned record size does not (`4 × (4,064 + 4) = 16,272 > 16,268`). This is a physical-capacity invariant, not a promise that heap bestspace will ignore configured unfill and actually pack four records on every page.

```
record > oos_inline_target ?
 ├─ no  → all values inline (no OOS)
 └─ yes → candidates = variable values with size > 16B, sorted by size DESC
           for cand in candidates:
             record already ≤ oos_inline_target ?  → break
             demote cand to OOS; payload -= cand_size; payload += 16B
           candidates exhausted above target? → apply OOS+bigone rejection rule
```

Example with the current 16KB layout (target = 4,060B):
- Record ~2.3KB ≤ 4,060B → OOS not triggered (under the old M1 rule this *would* have triggered at the 2KB gate)
- Record ~5KB (vc1=3000B + vc2=2000B) → demote largest (vc1) → record ~2KB ≤ 4,060B → **break**. Only vc1 goes to OOS; vc2 stays inline.
- Record ~9KB (vc1=4500B + vc2=4500B) → demote vc1 → ~4.5KB still > 4,060B → demote vc2 → fits. Both go to OOS.

**Conservative estimate (always safe)**: the loop compares against the pre-loop `header_size`, which is recomputed only once *after* the loop. Because payload is monotonically decreasing and header is monotonically non-increasing, the in-loop value is an over-estimate — so the loop may **over-demote** by at most one value near a VOT offset-size boundary (BYTE↔SHORT↔INT), but can never **under-demote** relative to that estimate. Afterward, the OOS+bigone guard ensures the result is either a valid slotted-page record or a rejected write.

**Old M1 behavior (for contrast)**: a single gate at `DB_PAGESIZE/8` (2KB), then *every* variable column `> 512B` was bulk-externalized in one pass — no sorting, no early stop. Replaced by CBRD-26776 (merged, PR #7158).

### OOS + bigone Rejection (CBRD-26937)

Demotion only moves *variable* attributes, so a record can still exceed the bigone threshold after every eligible value is demoted — e.g. a huge fixed-length `BIT(n)`/`CHAR` attribute, or many `≤16B` variable values. A record that contains OOS inline stubs **and** would be stored as a `REC_BIGONE` overflow record is an unsupported combination. `heap_attrinfo_transform_to_disk_internal` rejects it — *after* demotion, *before* writing any OOS value chain — with `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` (-1375):

```
if (has_oos && heap_is_big_length (expected_size))   // expected_size = record size after demotion
    → er_set (ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE); return S_ERROR;
```

- Rejection threshold is `heap_Maxslotted_reclength` (~16KB, the bigone threshold), **not** the OOS inline target. An OOS-backed heap record left between the target and ~16KB because candidates were exhausted is valid.
- Only fires when `has_oos` is true; ordinary non-OOS bigone records are unaffected.
- Gate sits before `heap_attrinfo_insert_to_oos`, so no orphan OOS value chains are written on rejection.

---

## 2. Architecture & Design

### CUBRID Storage Context

- **Heap file**: One per table. Contains slotted pages. Each page holds multiple records via a slot directory.
- **Overflow page**: When a single record exceeds one page, CUBRID chains overflow pages. OOS addresses the variable-column dimension specifically.
- **MVCC (Multi-Version Concurrency Control)**: In-place MVCC — records carry insert/delete transaction IDs in their MVCC header.
- **WAL (Write-Ahead Logging)**: All modifications logged before being applied to pages.
- **Vacuum**: Background process that reclaims space from records no longer visible to any active transaction.

### Comparison with Other Databases

| | PostgreSQL (TOAST) | MySQL (Off-page) | CUBRID OOS (current) |
|---|---|---|---|
| **Trigger** | `MaximumBytesPerTuple(4)` (~2KB), independent of fillfactor | ~8KB (row) | PG-style four-record heap target (4,060B with current 16KB I/O page layout), independent of unfill; value > 16B |
| **Stop semantics** | Largest-first, stop when row fits | Largest-first | **Largest-first, stop when record fits (CBRD-26776)** |
| **Separation** | Column-level | Column-level | Column-level |
| **Inline reference size** | 18B | 20B | **16B** (OOS inline stub) |
| **Compression** | pglz / lz4 | COMPRESSED format | None — deferred to future; CTO leans type-layer (`mr_data_writeval`), not OOS-layer (see Design Discussions) |
| **Storage** | TOAST table | Overflow pages | OOS file (FILE_OOS) |
| **Chunk split** | ~2KB chunks | Page-unit chain | OOS page-unit chain |
| **UPDATE reuse** | Unchanged values keep inline reference | Unchanged values keep inline reference | Always new value chain/head OID (M1) |

### Why This Design?

OOS is an evolution of CUBRID's existing Overflow Page mechanism:

| | Overflow (AS-IS) | OOS (TO-BE) |
|---|---|---|
| Separation unit | Entire record | Per-column |
| Page structure | Dedicated overflow page (1 record/page) | **Slotted page** (multiple records/page) |
| Internal fragmentation | Large | Reduced |
| File mapping | 1 heap file : 1 overflow file | 1 heap file : at most 1 OOS file |

**Why slotted pages**: Multiple OOS chunk records per page reduce internal fragmentation. The tradeoff is potential page lock contention when different transactions modify chunk records on the same page.

**Design decision**: Uses low-level heap/slotted page APIs the team knows well. References existing Overflow file implementation patterns. The CUBRID team chose this over PostgreSQL-style TOAST tables (which would require multi-table transaction sync) or simple overflow page modification (which wouldn't help with network/replication layers).

### Record Binary Layout

```
Heap Record (on disk):
+------------------+------------------+-------+--------------------------------+
|  MVCC Header     |  Variable Offset |  Fixed|  Variable Area                 |
|  (flags+txn ids) |  Table (VOT)     |  Cols |  (inline values or OOS stubs)   |
+------------------+------------------+-------+--------------------------------+

VOT Entry (per variable column):
  [offset_value (30 bits) | RESERVED (1 bit) | IS_OOS (1 bit)]

  IS_OOS = 1  ->  variable area contains an OOS inline stub (16 bytes) at this offset
  IS_OOS = 0  ->  variable area contains actual value at this offset

OOS inline stub (OR_OOS_INLINE_SIZE = 16 bytes):
  [head OOS OID (8 bytes) | full length (8-byte DB_BIGINT)]

MVCC Header Flags (5 bits total):
  bit 0: has insert ID
  bit 1: has delete ID
  bit 2: has prev version LSA
  bit 3: HAS_OOS (new for OOS)
  bit 4: reserved

  WARNING: MVCC header size lookup uses only lower 3 bits (idx & 0x07)
  HAS_OOS (bit 3) does NOT affect header size -- it's metadata only.
```

### Multi-Chunk OOS Chain

When a column value exceeds one OOS page, it's split into chunks stored as a linked list:

```
Insertion order (reverse):
  chunk_2 (tail of value) -> inserted first, next_oid = NULL
  chunk_1 (middle)        -> inserted second, next_oid = chunk_2 OID
  chunk_0 (head of value) -> inserted last, next_oid = chunk_1 OID

  Heap record's inline stub stores the head OOS OID pointing to chunk_0.

Read order (forward):
  Follow chain: chunk_0 -> chunk_1 -> chunk_2 -> reassemble value

Each OOS chunk record:
+-------------------+-------------+------------------+-----------------------------+
| total_data_length | chunk_index | next-chunk OID   | payload fragment            |
| (4-byte int)      | (4-byte int)| (8B; NULL last)  | (up to max chunk payload)   |
+-------------------+-------------+------------------+-----------------------------+

total_data_length is the complete OOS value length and excludes every OOS record header.
```

Reverse insertion reason: when inserting earlier chunks, the next chunk's OID must already be known.

### Best Page Policy (3-Tier Bestspace — M2, CBRD-26658)

Mirrors the heap file's proven 15+ year bestspace architecture. OOS file page 0 holds `OOS_HDR_STATS` (best[10] hints, space estimates, persisted to disk as non-logged hints). A separate global cache (`OOS_BESTSPACE_CACHE`) uses dual hash tables (VFID→entry, VPID→entry) with its own mutex, fully independent from heap's `bestspace_mutex`.

```
oos_find_best_page()
│
├─ [1] Fix header page (WRITE latch), load OOS_HDR_STATS best[] hints
├─ [2] oos_stats_find_page_in_bestspace()
│   ├── Tier 1: Global hash cache lookup (VFID key)
│   ├── Tier 2: best[10] circular array scan
│   └── Tier 3: Candidate page fix (CONDITIONAL_LATCH, zero-wait)
├─ [3] If not found → oos_stats_sync_bestspace()
│   └── Scan OOS file pages (max 20%, 100 page limit)
│       → Recharge best[] and global cache → retry
└─ [4] Still not found → oos_file_alloc_new()
```

- **Delete/rollback**: `oos_rv_redo_delete()` calls `oos_stats_del_bestspace_by_vpid()` to evict stale cache entries
- **Crash recovery**: Sync scanner auto-rediscovers free space (self-healing, since hints are non-logged)
- **Concurrency**: Zero-wait conditional latch avoids deadlocks during multi-transaction INSERT
- **Implementation status — DONE (CBRD-26954, 2026-07-01):** the fit-check previously over-reserved by one slot. `oos_find_best_page` now compares `rec_length` directly against `spage_max_space_for_new_record`, matching the heap contract; commit `e51dc8fd1b` removed the redundant `sizeof(SPAGE_SLOT)` addition.

> **Planned change (ADR-0001, CBRD-26831):** Tier-3 sync currently enumerates pages with `file_numerable_find_nth` because the OOS file is created `is_numerable=true`. This is the only *always-permanent + numerable* file in CUBRID, and once per-page vacuum dealloc is wired it enters an unvalidated mark-delete-churn regime. The plan is to make `FILE_OOS` **non-numerable** and enumerate via a **sector-bitmap walk** (`file_get_all_data_sectors`). That walk reads a frozen bitmap snapshot, so sampled pages must be fixed with `OLD_PAGE_MAYBE_DEALLOCATED` (read-only hint path only; the insert path keeps plain `OLD_PAGE`). Do it *before* `oos_remove_page` gets vacuum callers. See `docs/adr/0001-oos-page-enumeration-non-numerable.md`. _Status 2026-07-02: implemented on `oos-m2-all-plans-experimental` (creation `is_numerable=false`; sync + stats converted to the bitmap walk via `oos_collect_data_page_vpids` with `OLD_PAGE_MAYBE_DEALLOCATED` + `PAGE_OOS` type check). The ADR's skipped-page observability counter (Consequence 3) is NOT yet added. Pending TC verification/merge._

---

## 3. CRUD Flows

### INSERT

```
heap_insert()
  |
  +-> heap_attrinfo_determine_disk_layout()
  |   +-> record > PG-style four-record heap target?
  |       sort eligible variable values (size > 16B) by size DESC,
  |       demote largest first until target reached or candidates exhausted
  |   +-> (reject if record still > ~16KB while has_oos -> ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE)
  |
  +-> OOS VFID: heap header has VFID? if not: oos_file_create()
  |
  +-> For each selected OOS-backed attribute:
  |   +-> oos_insert() -> returns head OOS OID
  |
  +-> Build heap record:
      +-> variable area: OOS inline stub (16B) + IS_OOS flag in VOT
      +-> MVCC header: set HAS_OOS flag
      +-> spage_insert() into heap page

WAL: log both heap insert + OOS inserts
```

### SELECT (OOS Resolve)

```
heap_get() / scan
  |
  +-> Read heap record from page
  |
  +-> Check OR_MVCC_FLAG_HAS_OOS in MVCC header
  |   +-> 0: return as-is (no OOS)
  |   +-> 1: proceed to resolve
  |
  +-> heap_record_replace_oos_oids()   (record-level Expand; opt-in via
  |   HEAP_GET_CONTEXT.expand_oos since CBRD-26729 — see §3 Census. Most
  |   fetches DON'T set it and instead let the attribute layer Resolve per column)
      +-> Iterate VOT: for each OOS-backed attribute
          +-> oos_read() -> fetch actual value from OOS file
      +-> Reconstruct full record (size expands significantly)
```

### Visible-version fetch family (CBRD-26847 census)

All "visible version" fetchers funnel into `heap_get_visible_version_internal`. OOS **Expand** is
opt-in via a single flag (`HEAP_GET_CONTEXT.expand_oos`, checked once in `heap_record_replace_oos_oids`,
`heap_oos.cpp`). Choosing rule: **a path needs Expand only if it consumes raw recdes bytes (ships to
client `LC_COPYAREA`, re-inserts into a heap, byte-compares, or `OR_BUF`-parses); otherwise the
attribute layer Resolves per attribute and the cheap fetch is correct AND faster.** See ADR
`docs/adr/0003-oos-expansion-is-opt-in.md`.

| Function | Expands? | Use when |
|----------|----------|----------|
| `heap_get_visible_version` | No | recdes read via attribute layer / fixed / header / existence |
| `heap_get_visible_version_expand_oos` | Yes | recdes consumed as raw bytes |
| `heap_scan_get_visible_version` | No (by design) | heap scan; attr layer resolves lazily |
| `heap_get_last_version` | No | update/delete latest-version fetch (callers read via attr layer) |

**Census result:** of ~22 `_expand_oos` call sites, only **5 genuinely need Expand**
(`xlocator_lock_and_fetch_all`, `redistribute_partition_data`, `catcls_delete_instance`,
`catcls_update_instance`, `catcls_update_class_stats`); the other ~17 were mechanically migrated and
should revert to the cheap fetch. **Mirror hazard:** raw-byte paths that *forgot* to Expand leak
unresolved OOS inline stubs — known instance `xlocator_fetch_all` → unloaddb/compactdb (`load_object.c` is
OOS-blind). Ticket of record: **CBRD-26948 (OPEN)** — making Expand opt-in in PR #7093 (CBRD-26729)
left `xlocator_fetch_all` no longer expanding, re-leaking OIDs to unloaddb/compactdb. (Was loosely
attributed to CBRD-26583 / PR 7093.)

### UPDATE (Always New OID — M1)

**3-step process:**

1. Determine OOS candidates for new record -> `oos_insert()` -> new value chains and head OOS OIDs
2. Write updated heap record with new OOS inline stubs
3. Previous heap record (with old OOS inline stubs) saved to undo log as-is
4. Old OOS value chains remain alive — old transactions may access them via MVCC undo
5. When vacuum removes the old heap-record version, `oos_delete()` cleans up its OOS value chains

```
Before UPDATE:
  heap: [ ... | OOS stub { head OID (1|1|33), full length } | 'bbbbb' ]
  OOS page 1, slot 33: 'aaaa...(4500B)'

UPDATE tbl SET vc2 = 'hello' WHERE id = 1;

Step 1: oos_insert -> new value chain and head OOS OID
  OOS page 2, slot 44: 'aaaa...(4500B)'             <- new record

Step 2: Update heap record
  heap: [ ... | OOS stub { head OID (1|2|44), full length } | 'hello' ]
  undo log: [ ... | OOS stub { head OID (1|1|33), full length } | 'bbbbb' ]

Step 3: Old OOS value chain stays alive
  OOS page 1, slot 33: 'aaaa...(4500B)'              <- MVCC readers may need it
  -> vacuum will oos_delete when cleaning old heap record from undo log
```

**Ownership invariant**: Each OOS value chain is owned by exactly one logical heap-record version. OOS value chains are not shared across record versions. The inline stub stores the head OOS OID; non-head OOS OIDs are linked from the preceding chunk record.

**Current limitation**: Always creates a new OOS value chain and head OOS OID even if the value is unchanged. Value-chain reuse is **deferred to a future improvement** — it is NOT in M2 scope (M3, which had planned it, is cancelled). Verified against code: UPDATE always allocates fresh value chains (`heap_attrinfo_insert_to_oos`), which the vacuum forward-walk relies on for old/new head-OID disjointness.

### DELETE

```
heap_delete()
  |
  +-> Add MVCC delete ID to record
  |   +-> Modified record stored back to heap page
  |
  +-> OOS inline stubs: DO NOT TOUCH
      +-> OOS value chains NOT deleted (MVCC readers may need them)
      +-> OOS-backed attributes NOT resolved (heap page has 16KB limit)
      +-> Vacuum handles OOS cleanup later
```

**Why not delete immediately**: Deleted records still exist on the heap page (MVCC). The 16KB page limit means OOS-backed attributes cannot be resolved in place because the expanded record may not fit. OOS cleanup is therefore deferred to vacuum.

---

## 4. Recovery, Replication & MVCC

### Recovery & Replication Invariants

These invariants MUST hold — test scenarios verify each one:

1. **WAL completeness**: Every OOS insert/delete is logged. After crash + recovery, OOS state matches the last committed transaction state.
2. **Undo correctness**: Update/delete undo retains the previous record **as-is, including its OOS inline stubs** — undo does NOT store resolved values (that would bloat the undo log and defeat the whole point of OOS). Rollback restores the previous record, whose head OOS OIDs still point to live value chains; MVCC snapshot reads reconstruct the old version the same way (via `prev_version_lsa` → undo recdes → `oos_read`), which is exactly why old OOS value chains must survive until vacuum (see invariant 3). The vacuum forward-walk depends on this — it extracts head OOS OIDs straight out of the undo recdes. _(Corrected 2026-06-02: the prior text claimed undo holds fully-resolved values with no stubs, which contradicts invariant 3 and the code; it had misled a fix proposal toward deleting old OOS values inline.)_
3. **No orphan OOS value chains after update**: On update, old OOS value chains remain for MVCC. When vacuum removes the old heap-record version, `oos_delete()` cleans up its value chains.
4. **Delete safety**: Deleted heap records retain their OOS inline stubs. OOS value chains are NOT deleted at delete time — they remain accessible until vacuum.
5. **Replication log completeness**: Replication log contains enough info to replay OOS operations on replica. OOS OIDs in replication log point to correct OOS pages on replica.
6. **OOS file <-> heap file 1:1**: Each heap file has at most one OOS file. The OOS VFID is stored in the heap header page.

### Replication Notes

- **Slave OOS OIDs may differ from master** — only value equality is guaranteed, not OID equality.
- Replication log must carry sufficient data for slave to perform its own `oos_insert` operations.

### Vacuum + OOS (IMPLEMENTED — CBRD-26668, PR #6986 merged)

DELETE/UPDATE never clean OOS value chains inline; vacuum reclaims them when it reclaims the dead heap-record versions that owned them. Three cleanup paths (`vacuum_oos.cpp`, `heap_oos.cpp`):

1. **Forward-walk (MVCC old versions)** — `vacuum_forward_walk_oos_delete_atomic` (`vacuum_oos.cpp:154`): pulls old head OOS OIDs straight out of the UPDATE/DELETE undo recdes (relies on invariant 2) and `oos_delete`s their value chains. Runs in *its own* sysop with no enclosing sysop, so a mid-walk failure rolls back only its own deletes.
2. **Within-sysop (current record)** — `vacuum_heap_oos_delete_within_sysop` (`vacuum_oos.cpp:383`): deletes OOS value chains owned by a heap record being vacuumed, inside the caller's sysop.
3. **Eager (non-MVCC / SA_MODE)** — `heap_oos_delete_unreferenced` (`heap_oos.cpp:425`): single-process mode has no vacuum, so old value chains are deleted synchronously at UPDATE time, comparing old and new head OOS OIDs to keep any chain the post-image still references.

- **Chunk record vs page**: vacuum deletes OOS *chunk records* (slots), but does **not** yet deallocate emptied OOS *pages* — `oos_remove_page` (`oos_file.cpp:1008`) has no vacuum caller; empty-page reclaim is CBRD-26786 (proposed). This is exactly why ADR-0001's non-numerable migration window is still open (no live page-dealloc path to preserve).
- **Crash mid-delete**: each chunk delete is logged within a sysop, so recovery redo/undo keeps OOS state atomic with the heap reclamation.

---

## 5. Implementation Conformance Status — Non-normative

### Known Bugs

| Issue | Description | Impact | JIRA |
|---|---|---|---|
| **Vacuum deletes live data in reused OOS slot** | Vacuum frees an OOS slot → another row's `oos_insert` reuses the same `(volid,pageid,slotid)` (OOS pages are `ANCHORED`) → block retry (worker pause / mid-block error / crash recovery; `start_lsa` only advances on full-block completion) re-derives the old OID from the immutable undo image and re-deletes it, now hitting the *live* row's chunk (whole chain if multi-chunk). Probe `oos_chunk_exists` checks "occupied", not "mine" — `oos_record_header` has no owner OID / generation. Found in PR #6986 review | **CRITICAL — silent data loss.** Fix (owner/generation field in chunk header) TBD/ANALYSIS | CBRD-26950 |
| ~~TDE not applied to OOS pages~~ | **DONE on `feat/oos`**: CBRD-26830 / commit `138f624964` added both defenses: `xfile_apply_tde_to_class_files` includes an existing OOS file, and lazy creation applies the class TDE algorithm before publishing the OOS VFID | Fixed 2026-06-16 | CBRD-26830 |
| ~~OOS inline-stub writer bounds-checked the wrong pointer~~ | **DONE on `feat/oos`**: CBRD-26814 / commit `bceac0ddc` checks the actual stub write position `*ptr_varvals`, restoring the `S_DOESNT_FIT` grow-and-retry path. BLOB/CLOB locators remain OOS-demotable per ADR-0002 | Fixed 2026-07-03 | CBRD-26814 |
| unloaddb 1.6-1.7x slower | `heap_attrinfo_start` called per `heap_next` in `feat/oos` branch | Performance regression | CBRD-26458 |
| ~~UPDATE calls `oos_read` 3x redundantly~~ | Record-level Expand redundancy removed: `heap_record_replace_oos_oids` is now opt-in via `HEAP_GET_CONTEXT.expand_oos`, so non-raw-byte fetches use the cheap attribute-layer Resolve. Residual "UPDATE re-reads unchanged OOS-backed attributes" is M1 design (no OID reuse), not a bug — confirmed by CBRD-26953 | **DONE** (CBRD-26729 in `feat/oos`) | CBRD-26516 |
| CDC flashback OOS-stub Resolve | CDC flashback needs to replace OOS inline stubs with actual values in recdes | Missing feature | — |
| Unnecessary OOS replication log in `locator_add_or_remove_index` | OOS replication log forced in unrelated context | Refactoring needed | — |
| RECDES length 4-byte limit | OOS recdes max size limited to 2GB (4-byte length). May need 8-byte extension for 16EB max | Design limitation | — |
| `spacedb`/`diagdb` can't see OOS space | `cubrid spacedb` counts `FILE_OOS` as heap — no `SPACEDB_OOS_FILE`; OOS files store no owner metadata in `FILE_DESCRIPTORS` so can't be attributed to a table. _2026-07-02: the `FILE_OOS` utility **asserts** (`file_tracker_item_spacedb` `assert_release(false)`, `file_tracker_get_and_protect`, `file_header_dump_descriptor`) crashed manual QA (`cbrd_20644`, `tbl_enc_08/14`, `_02_show_archive_log_header`, `json_backup_restore`); fixed on `oos-m2-all-plans-experimental` by intentionally folding OOS into `SPACEDB_HEAP_FILE` (TOAST-style "table storage" accounting, zero output drift) and letting read-only tracker scans pass OOS unprotected. Durable follow-up: `FILE_OOS_DES{class_oid}` owner descriptor → standard conditional-lock protection + per-table attribution (prerequisite for CBRD-26871)._ | No release-build tool proves a row went OOS or how much space OOS uses per table — only debug `oos.log` does. Forces the OOS test merge-gate onto debug builds. Unprotected tracker pass leaves a narrow SERVER_MODE checkdb-vs-DROP race until the descriptor lands | QA tooling ask (CBRD-26871) |

### Limitations (Milestone 1)

| Limitation | Impact | Future Fix |
|---|---|---|
| ~~No OOS file cleanup on DROP TABLE~~ | ~~OOS file leaked after its heap file was destroyed~~ | **DONE** (CBRD-26608: `oos_remove_file`) |
| ~~Bestspace = last-insert-page only~~ | ~~Hotspot on single page, wasted space~~ | **DONE** (CBRD-26658: 3-tier bestspace) |
| ~~Bulk-externalize every variable value > 512B~~ | ~~Small values needlessly go OOS → extra `oos_read` I/O, OOS file bloat~~ | **DONE** (CBRD-26776: largest-first incremental demotion; historical gate 2KB→4KB, later superseded by the PG-style four-record target; profitable threshold 512B→strictly greater than 16B) |
| ~~No deferred OOS cleanup after DELETE/UPDATE~~ | ~~Dead record versions left their OOS value chains permanently allocated~~ | **DONE** (CBRD-26668: vacuum integration) |
| No OOS value-chain reuse on update | Extra I/O when value unchanged | Future improvement (deduplication; M3 cancelled, not in M2) |
| Ordered fix deadlock risk | Two tx's accessing OOS pages in different order | Future improvement (M4 cancelled, not in M2) |
| No PEEK mode for OOS reads | Always COPY semantics, extra memcpy | Future |
| No across-page compaction | Fragmentation over time | Future |
| `S_DOESNT_FIT` handling incomplete | Caller must handle buffer overflow | Upper-layer |

### Optimization Ideas

**A. Update OOS value-chain reuse (CBRD-26516)** _(future improvement — was the cancelled M3 plan; not in M2)_: In `heap_attrinfo_set_uninitialized`, prevent resolving OOS values via `heap_attrvalue_read` for unchanged attributes. Reuse the existing value chain/head OOS OID instead of creating a new chain. **Prerequisite:** the vacuum forward-walk (`vacuum_forward_walk_oos_delete_atomic`) must first gain an old∩new head-OID sharing check, or it will delete a chain the live post-image still references.

**B. Defer `oos_insert` to `attrinfo_force` (Heesoo's idea)**: Unify `insert -> oos_log_insert -> oos_repl_log_insert` flow timing to `attrinfo_force`. This enables generating OOS replication log at the same time as heap record replication log, allowing PK inclusion in OOS replication log. Implementation: separate `oos_repl_log` function (existing repl log function overwrites LSA in sequence: `tail_lsa -> repl_insert_lsa -> repl_rec->lsa`, so OOS LSAs must be collected separately).

**C. Minimize `pgbuf_fix` for multiple `oos_insert`**: When multiple OOS values target the same page, perform `pgbuf_fix` once instead of per-insert.

**D. `oos_read` PEEK mode**: Current COPY mode requires allocating and freeing recdes each time. PEEK mode would avoid this. Requires removing `is_oos` parameter from `heap_attrvalue_transform_to_dbvalue()` and separating `spage_get_record` / `spage_insert` into OOS-specific variants.

**E. Ordered OOS page fix for deadlock prevention**: Enforce globally consistent page fix order (e.g., VPID ascending) to prevent deadlocks between transactions accessing the same OOS pages in different order.

### Proposed Design Discussions — Non-normative (2026/3/5 feedback)

- **Multi-attribute OOS storage**: Combine multiple OOS values into one physical record vs. the current one-value-chain-per-attribute design. Direction TBD.
- **OOS page latch contention**: Yechan's proposal — partition page into 4-64 sections with atomic latches. Deferred unless latch bottleneck becomes severe.
- **OVF + OOS simultaneous**: A record containing OOS inline stubs that would *also* become `REC_BIGONE` (recdes > ~16K overflow) is now **rejected** at write time with `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` (CBRD-26937), not silently built. Test the *rejection* (e.g. large fixed `BIT(n)`/`CHAR` + OOS-backed varchar that stays > ~16KB after demotion) rather than coexistence.
- **OOS value compression (DEFERRED to future — not M2, not built)**: Investigation (CBRD-26756) initially landed on a 2026-05-08 meeting lean toward compressing at the **common OOS-entry point** (PG TOAST `EXTENDED`-style: try compress → if still big, store OOS), covering every variable type going to OOS — today only `VARCHAR` is LZ4-compressed (at the type/OR layer, ≥255B); `VARNCHAR`/`VARBIT`/`JSON`/`SET`/`MULTISET`/`SEQUENCE` are not compressed anywhere. CBRD-26881 then reframed the real fork as **type-serialization layer (`mr_data_writeval`)** vs **OOS boundary**, deferring the choice to ANALYSIS. **Current direction (CTO): defer compression to a future milestone and, when done, control it at the data-type serialization layer (`mr_data_writeval`), NOT the OOS layer** — this supersedes the earlier OOS-entry lean in CBRD-26756. Zero compression code exists in `oos_file.cpp`/`heap_oos.cpp` today. (Beware: the two tickets label their options "A"/"B" in *opposite* directions — describe by layer location, not letter.)
- **CHAR type as OOS candidate**: Evaluate storing CHAR columns as OOS when they exceed threshold.
- **Per-column inline preference (CBRD-26912, proposed — NOT yet merged)**: `STORAGE PREFER_INLINE` column option (à la PG `SET STORAGE MAIN`) that pushes a hot column to the *back* of the largest-first demote order, so its values are externalized only as a last resort. Soft only — the value still demotes if needed; afterward the ordinary OOS+bigone guard still guarantees either a valid slotted-page record or a rejected write. Stored as a new `SM_ATTFLAG_OOS_PREFER_INLINE` bit; the sole policy change is adding it as the primary sort key in `heap_attrinfo_determine_disk_layout`.

---

## 6. Test Scenarios

### Testing Principles

- **Use `BIT VARYING` (VARBIT)**, NOT `VARCHAR`: CUBRID compresses strings, making disk size unpredictable. VARBIT is not compressed, so disk size is exact. _(Holds today; if future type-layer compression — CBRD-26756/26881 — ever extends to VARBIT, disk size stops being exact and this rule needs revisiting.)_
- **Pattern**: `CAST(REPEAT('AA', N) AS BIT VARYING)` produces N bytes on disk.
- **Size verification**: Use `DISK_SIZE(col)` (not `LENGTH` which returns bits).
- **Distinct values**: Use different hex patterns ('AA', 'BB', 'CC', etc.) to distinguish values.
- **OOS trigger**: record > the PG-style four-record heap target (4,060B with the current 16KB I/O page layout); then the *largest* variable values (size strictly greater than 16B) are demoted one-by-one until the record reaches the target or candidates are exhausted — **not** every eligible value. The target excludes heap unfill, matching PG's separation of TOAST threshold and fillfactor.

### Common Table Setup

```sql
CREATE TABLE oos_test (
    id INT PRIMARY KEY,
    small_col VARCHAR(100),
    big_col1 BIT VARYING,
    big_col2 BIT VARYING
);
-- big_col1/big_col2 with large VARBIT values trigger OOS
```

### Test Categories

#### 1. Basic CRUD (4 tests)
- **1.1 Insert + Select consistency**: Insert an OOS-backed heap record, verify `DISK_SIZE()` and value equality
- **1.2 Non-trigger verification**: Records below threshold stay in heap (no OOS)
- **1.3 Largest-first demotion (discriminating test for CBRD-26776)**: Record > the OOS inline target with two unequal eligible columns; verify only the largest values needed to reach the target are demoted. Release builds can't see per-attribute OOS placement (`DISK_SIZE` returns the logical value size regardless), so confirm via debug `oos.log` `oos_insert ... src.size=` (CBRD-26871)
- **1.4 Bulk insert**: 100+ rows with varying sizes, verify all sizes correct

#### 2. UPDATE (3 tests)
- **2.1 OOS-backed attribute value change**: Update an OOS-backed attribute, verify the new value and eventual cleanup of the old value chain
- **2.2 Inline attribute change**: Even changing only an inline attribute creates new OOS value chains for the record version (M1 behavior)
- **2.3 Repeated updates**: Multiple updates to same row, final value correct

#### 3. DELETE (2 tests)
- **3.1 Delete + verify gone**: DELETE row, verify `COUNT(*)` decreases
- **3.2 Delete all + reinsert**: DELETE all rows, INSERT new rows, verify table reusable

#### 4. ACID (4 tests)
- **4.1 Atomicity (ROLLBACK)**: INSERT + UPDATE in transaction, ROLLBACK, verify original state
- **4.2 UPDATE ROLLBACK**: OOS-backed attribute UPDATE + ROLLBACK restores the original OOS value via undo log
- **4.3 Durability**: COMMIT -> server restart -> data survives
- **4.4 Isolation (MVCC)**: Session 1 updates (uncommitted), Session 2 sees old value

#### 5. Crash Recovery (5 tests)
- **5.1 Committed INSERT redo**: INSERT + COMMIT + `kill -9` -> restart -> data present
- **5.2 Uncommitted INSERT undo**: INSERT (no commit) + `kill -9` -> restart -> data gone
- **5.3 Uncommitted UPDATE undo**: UPDATE (no commit) + crash -> original value restored (undo retains the previous record's OOS inline stubs **as-is**; on rollback their head OOS OIDs still point to live value chains — see invariant 2, NOT resolved values)
- **5.4 Mixed committed/uncommitted**: Committed data survives, uncommitted data undone
- **5.5 Multi-chunk crash recovery**: 50KB+ value (multi-chunk chain) survives crash

#### 6. MVCC Concurrency (3 tests)
- **6.1 UPDATE visibility**: Session 1 updates OOS (uncommitted), Session 2 reconstructs the old value via `prev_version_lsa` -> undo recdes -> `oos_read` (undo holds OOS inline stubs, not resolved values — see invariant 2)
- **6.2 DELETE visibility**: Deleted OOS-backed heap record still visible to an earlier snapshot
- **6.3 Concurrent multi-UPDATE**: Different sessions update different rows simultaneously, values don't mix

#### 7. Multi-chunk OOS (3 tests)
- **7.1 Large value (>16KB)**: Insert 50KB value spanning multiple OOS pages, verify chain
- **7.2 Multi-chunk update**: Update multi-chunk OOS value, verify new chain correct
- **7.3 Mixed sizes**: Same table with single-chunk and multi-chunk OOS values

#### 8. Replication (4 tests)
- **8.1-8.4**: INSERT/UPDATE/DELETE/multi-chunk operations replicated correctly to slave. Verify value equality (OOS OIDs may differ between master and slave).

#### 9. Edge Cases (6 tests)
- **9.1 Record gate boundary**: Verify the derived target and both sides of the boundary; with the current layout, 4,060B does not trigger and the next representable aligned size does
- **9.2 Column eligibility floor**: Variable value ≤ 16B (`OR_OOS_INLINE_SIZE`) is never demoted, even when the record exceeds the target (demoting it would not shrink the record)
- **9.3 NULL values**: NULL in OOS-eligible column
- **9.4 Empty values**: Zero-length VARBIT in OOS-eligible column
- **9.5 Many OOS-backed attributes**: 10+ attributes demoted in a single heap record
- **9.6 OOS + bigone rejection (CBRD-26937)**: Record with an OOS-backed attribute + a large fixed `BIT(n)` that stays > ~16KB after demotion → INSERT/UPDATE rejected with `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` (-1375), row not stored. A non-OOS bigone, or an OOS-backed heap record left between the OOS inline target and ~16KB because candidates were exhausted, still succeeds

#### 10. Stress Tests (2 tests)
- **10.1 Bulk 1000+ rows**: All with OOS, verify all values correct
- **10.2 Repeated updates 50+**: Same row updated 50+ times, final value correct

### Key Test SQL Pattern

```sql
-- OOS INSERT + verify (record must exceed the derived OOS inline target; 4,060B in the current layout)
CREATE TABLE t (id INT, vc1 BIT VARYING, vc2 BIT VARYING);
INSERT INTO t VALUES (1, CAST(REPEAT('AA', 3000) AS BIT VARYING),
                         CAST(REPEAT('BB', 2000) AS BIT VARYING));
-- Record ~5KB > target → largest (vc1) demoted to OOS → ~2KB fits → vc2 stays inline

-- Verify size (DISK_SIZE is the logical value size — identical whether inline or OOS)
SELECT id, DISK_SIZE(vc1), DISK_SIZE(vc2) FROM t WHERE id = 1;
-- Expected: 1, 3000, 2000

-- Verify value equality
SELECT (vc1 = CAST(REPEAT('AA', 3000) AS BIT VARYING)),
       (vc2 = CAST(REPEAT('BB', 2000) AS BIT VARYING))
FROM t WHERE id = 1;
-- Expected: 1, 1

-- ROLLBACK test
COMMIT;
UPDATE t SET vc1 = CAST(REPEAT('CC', 3000) AS BIT VARYING) WHERE id = 1;
ROLLBACK;
SELECT (vc1 = CAST(REPEAT('AA', 3000) AS BIT VARYING)) FROM t WHERE id = 1;
-- Expected: 1 (rollback restored the previous record, whose OOS inline stubs still reference live value chains)
```

---

## Milestones — Non-normative Planning Status

- **M1** (Feb 2026, DONE): Basic POC — insert/read/update/delete, WAL, recovery, replication
- **M2** (active — umbrella for all remaining OOS work): Drop table, bestspace optimization, in-page compaction, vacuum integration, **largest-first OOS demotion (CBRD-26776, done) + OOS/bigone rejection (CBRD-26937)**
- ~~**M3** (was: OOS value-chain reuse on update / deduplication)~~ — **CANCELLED (2026-06-02).** Value-chain reuse is deferred to a future improvement; it is NOT folded into M2 (current code always allocates a fresh chain/head OOS OID — verified via `heap_attrinfo_insert_to_oos`). See **Limitations** and **Optimization Ideas → A**.
- ~~**M4** (TBD): Ordered fix deadlock handling, monitoring tools~~ — **CANCELLED (2026-06-02).** Deferred to future improvements; not in M2. (Ordered-fix deadlock prevention is also tracked under Limitations and Optimization Ideas → E.)

---

## Writing Conventions

When writing OOS-related code comments or documentation:

- Use **OOS OID** only for the 8-byte physical OID of a chunk record; use **head OOS OID** when emphasizing the OID stored in the heap record
- Use **OOS inline stub** for the 16-byte heap representation (head OOS OID + full length); never call the full stub an OOS OID or pointer
- Use **OOS value** for the complete serialized attribute value, **OOS chunk record** for one physical slotted-page record, and **OOS value chain** for the complete one-or-more-chunk storage object
- Use **OOS-backed attribute** for a particular row value; a schema column is merely eligible and its values may remain inline
- Use **OOS file** / **OOS value** / **OOS chunk record** when referring to a concrete object; use **OOS subsystem** for the feature as a whole
- Always add a space between inline code and Korean text: `` `oos_read` 는 `` (not `` `oos_read`는 ``)
- Describe the record demotion gate as the **PG-style four-record heap target** derived by `heap_oos_inline_target_size()`; do not call it raw `DB_PAGESIZE/4`. State that it excludes heap unfill, like PG TOAST excludes fillfactor. The profitable demotion threshold remains `> OR_OOS_INLINE_SIZE` (strictly greater than 16B); `DB_PAGESIZE/8` / 512B are historical pre-CBRD-26776 values
- State ownership as: each OOS value chain is owned by exactly one logical heap-record version; value chains are not shared across versions
- Do not describe unimplemented features as existing (no PEEK mode, no OOS dedup, no across-page compaction in M1)
