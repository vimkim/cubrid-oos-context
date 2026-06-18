# CUBRID OOS (Out-of-row Overflow Storage) — AI Agent Context

> Single source of truth for AI agents working on CUBRID OOS implementation and debugging.
> Last updated: 2026-06-18 | Branch: `feat/oos` | Milestone: M2 (the only active milestone — all remaining OOS work; M3 & M4 cancelled)
> **Spec note (2026-06-18):** OOS demotion is now **PG TOAST-style largest-first** — record gate raised to `DB_PAGESIZE/4` (4KB), column floor lowered to `OR_OOS_INLINE_SIZE` (16B), and only the largest columns needed to make the record fit are externalized (not all eligible). Merged: CBRD-26776 (PR #7158). OOS+bigone coexistence is now rejected (CBRD-26937). See §1.

## Quick Reference

| Concept | Detail |
|---------|--------|
| OOS trigger | record > `DB_PAGESIZE/4` (4KB on 16KB pages) → demote largest variable columns (value > `OR_OOS_INLINE_SIZE` = 16B) one-by-one until record fits (PG TOAST-style; CBRD-26776) |
| OOS file type | `FILE_OOS`, one per heap file (1:1 mapping) |
| OOS pointer | 16-byte OOS OID (volid 2B + pageid 4B + slotid 2B + full_length 8B) in variable area |
| HAS_OOS flag | MVCC header bit 3 (`OR_MVCC_FLAG_HAS_OOS = 0x08`) |
| IS_OOS flag | VOT entry bit 0 (`OR_VAR_BIT_OOS = 0x1`) |
| Key sources | `heap_file.c`, `oos_file.cpp`, `object_representation.h`, `object_representation_constants.h` |
| Branch | `feat/oos` |
| JIRA | CBRD-26517 (main), CBRD-26458 (unloaddb perf), CBRD-26516 (redundant oos_read), CBRD-26637 (error handling), CBRD-26658 (3-tier bestspace), CBRD-26776 (largest-first demotion, done), CBRD-26937 (OOS+bigone rejection), CBRD-26912 (STORAGE PREFER_INLINE, proposed) |

### Core Terminology

| Term | Definition |
|------|-----------|
| OOS Record | Column data split from heap record, stored in OOS file |
| OOS File | FILE_OOS type file, 1:1 with heap file (one per table) |
| OOS Page | Slotted page within OOS file (size = DB_PAGESIZE) |
| OOS OID | 16-byte pointer (volid 2B, pageid 4B, slotid 2B, full_length 8B) stored in heap record's variable area |
| HAS_OOS flag | Record-level MVCC header flag — true if any column is OOS |
| IS_OOS flag | Per-column flag in variable offset table entry |
| OOS Expand | **Record-level, eager**: replace *every* inline OOS OID slot with its value, rebuilding the whole record (`HEAP_GET_CONTEXT.expand_oos` → `heap_record_replace_oos_oids`). For callers that consume raw recdes bytes. _Avoid_: "resolve" for this. |
| OOS Resolve | **Column-level, lazy**: read *one* OOS column's value on demand (`heap_attrvalue_read_oos_inline` → `oos_read`). What the attribute layer (`heap_attrinfo_read_dbvalues`) does. _Avoid_: "expand", "materialize" for this. |
| OOS Demotion | **Write-time, trigger-side**: at INSERT/UPDATE, when the record exceeds `DB_PAGESIZE/4`, move the *largest* eligible variable columns to OOS one-by-one until the record fits — PG TOAST-style (`heap_attrinfo_determine_disk_layout`, CBRD-26776). Not every eligible column is externalized; smaller ones may stay inline. _Avoid_: "bulk externalization" (that was the old M1 behavior). |
| Numerable file | A file that records page-allocation order so callers can fetch the nth page (`file_numerable_find_nth`). OOS is created numerable today but is slated to drop it — see ADR-0001. _Avoid_: indexed file, ordered file |
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
[ id | name | OOS OID (16B) | OOS OID (16B) ]       <- compact heap record
                  |                |
                  v                v
           [ big_text ]     [ big_blob ]             <- OOS file (separate)
```

### Trigger Conditions — Largest-First Demotion (PG TOAST-style, CBRD-26776)

OOS demotion is a two-stage, **incremental** process (`heap_attrinfo_determine_disk_layout`, `heap_file.c:12097`). It mirrors PostgreSQL's tuple-toaster main loop, minus compression:

1. **Record gate**: only externalize if `header_size + payload_size + mvcc_extra > DB_PAGESIZE / 4` (4KB on 16KB pages). If the record already fits, everything stays inline.
2. **Eligibility**: a column is a candidate iff `is_variable && column_size > OR_OOS_INLINE_SIZE` (16B) — i.e. its value is bigger than the 16-byte OOS stub (OID + length) that replaces it, so demoting it actually shrinks the record.
3. **Largest-first loop**: sort candidates by size **descending**, then demote one at a time (subtracting `column_size`, adding back 16B per demote), and **`break` as soon as the record drops to ≤ `DB_PAGESIZE/4`**. The smallest eligible columns may remain inline.

```
record > DB_PAGESIZE/4 ?
 ├─ no  → all columns inline (no OOS)
 └─ yes → candidates = variable columns with value > 16B, sorted by size DESC
           for cand in candidates:
             record already ≤ DB_PAGESIZE/4 ?  → break
             demote cand to OOS; payload -= cand_size; payload += 16B
```

Example with DB_PAGESIZE=16K (gate = 4KB):
- Record ~2.3KB ≤ 4KB → OOS not triggered (under the old M1 rule this *would* have triggered at the 2KB gate)
- Record ~5KB (vc1=3000B + vc2=2000B) → demote largest (vc1) → record ~2KB ≤ 4KB → **break**. Only vc1 goes to OOS; vc2 stays inline.
- Record ~9KB (vc1=4500B + vc2=4500B) → demote vc1 → ~4.5KB still > 4KB → demote vc2 → fits. Both go to OOS.

**Conservative estimate (always safe)**: the loop compares against the pre-loop `header_size`, which is recomputed only once *after* the loop. Because payload is monotonically decreasing and header is monotonically non-increasing, the in-loop value is an over-estimate — so the loop may **over-demote** by at most one column near a VOT offset-size boundary (BYTE↔SHORT↔INT), but can never **under-demote**. Correctness and the "record always fits a page" invariant are preserved.

**Old M1 behavior (for contrast)**: a single gate at `DB_PAGESIZE/8` (2KB), then *every* variable column `> 512B` was bulk-externalized in one pass — no sorting, no early stop. Replaced by CBRD-26776 (merged, PR #7158).

### OOS + bigone Rejection (CBRD-26937)

Demotion only moves *variable* columns, so a record can still exceed the bigone threshold after every eligible column is demoted — e.g. a huge fixed-length `BIT(n)`/`CHAR` column, or many `≤16B` variable columns. A record that carries OOS OIDs **and** would be stored as a `REC_BIGONE` overflow record is an unsupported combination. `heap_attrinfo_transform_to_disk_internal` rejects it — *after* demotion, *before* writing any OOS record — with `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` (-1375):

```
if (has_oos && heap_is_big_length (expected_size))   // expected_size = record size after demotion
    → er_set (ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE); return S_ERROR;
```

- Rejection threshold is `heap_Maxslotted_reclength` (~16KB, the bigone threshold), **not** the 4KB demotion gate. An OOS record left inline between 4KB and ~16KB is fine.
- Only fires when `has_oos` is true; ordinary non-OOS bigone records are unaffected.
- Gate sits before `heap_attrinfo_insert_to_oos`, so no orphan OOS records are written on rejection.

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
| **Trigger** | ~2KB (row) | ~8KB (row) | record > PAGESIZE/4 (4KB), value > 16B |
| **Stop semantics** | Largest-first, stop when row fits | Largest-first | **Largest-first, stop when record fits (CBRD-26776)** |
| **Separation** | Column-level | Column-level | Column-level |
| **Pointer size** | 18B | 20B | **16B** (OOS OID) |
| **Compression** | pglz / lz4 | COMPRESSED format | None (M1) |
| **Storage** | TOAST table | Overflow pages | OOS file (FILE_OOS) |
| **Chunk split** | ~2KB chunks | Page-unit chain | OOS page-unit chain |
| **UPDATE reuse** | Unchanged columns keep pointer | Unchanged columns keep pointer | Always new OID (M1) |

### Why This Design?

OOS is an evolution of CUBRID's existing Overflow Page mechanism:

| | Overflow (AS-IS) | OOS (TO-BE) |
|---|---|---|
| Separation unit | Entire record | Per-column |
| Page structure | Dedicated overflow page (1 record/page) | **Slotted page** (multiple records/page) |
| Internal fragmentation | Large | Reduced |
| File mapping | 1 table : 1 overflow file | 1 table : 1 OOS file |

**Why slotted pages**: Multiple OOS records per page reduces internal fragmentation. The tradeoff is potential page lock contention when different transactions modify OOS records on the same page.

**Design decision**: Uses low-level heap/slotted page APIs the team knows well. References existing Overflow file implementation patterns. The CUBRID team chose this over PostgreSQL-style TOAST tables (which would require multi-table transaction sync) or simple overflow page modification (which wouldn't help with network/replication layers).

### Record Binary Layout

```
Heap Record (on disk):
+------------------+------------------+-------+--------------------------------+
|  MVCC Header     |  Variable Offset |  Fixed|  Variable Area                 |
|  (flags+txn ids) |  Table (VOT)     |  Cols |  (values or 16-byte OOS OIDs)  |
+------------------+------------------+-------+--------------------------------+

VOT Entry (per variable column):
  [offset_value (30 bits) | RESERVED (1 bit) | IS_OOS (1 bit)]

  IS_OOS = 1  ->  variable area contains OOS OID (16 bytes) at this offset
  IS_OOS = 0  ->  variable area contains actual value at this offset

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
  chunk_3 (tail of value) -> inserted first, next_oid = NULL
  chunk_2 (middle)        -> inserted second, next_oid = chunk_3 OID
  chunk_1 (head of value) -> inserted last, next_oid = chunk_2 OID

  Heap record stores OOS OID pointing to chunk_1.

Read order (forward):
  Follow chain: chunk_1 -> chunk_2 -> chunk_3 -> reassemble value

Each chunk record:
+------------------+-----------------------------+
| next OOS OID     | chunk data                  |
| (8 bytes, or     | (up to max_chunk_size)      |
|  NULL if last)   |                             |
+------------------+-----------------------------+
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

> **Planned change (ADR-0001, CBRD-26831):** Tier-3 sync currently enumerates pages with `file_numerable_find_nth` because the OOS file is created `is_numerable=true`. This is the only *always-permanent + numerable* file in CUBRID, and once per-page vacuum dealloc is wired it enters an unvalidated mark-delete-churn regime. The plan is to make `FILE_OOS` **non-numerable** and enumerate via a **sector-bitmap walk** (`file_get_all_data_sectors`). That walk reads a frozen bitmap snapshot, so sampled pages must be fixed with `OLD_PAGE_MAYBE_DEALLOCATED` (read-only hint path only; the insert path keeps plain `OLD_PAGE`). Do it *before* `oos_remove_page` gets vacuum callers. See `docs/adr/0001-oos-page-enumeration-non-numerable.md`.

---

## 3. CRUD Flows

### INSERT

```
heap_insert()
  |
  +-> heap_attrinfo_determine_disk_layout()
  |   +-> record > PAGESIZE/4?
  |       sort eligible variable columns (value > 16B) by size DESC,
  |       demote largest first until record fits (PG TOAST-style)
  |   +-> (reject if record still > ~16KB while has_oos -> ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE)
  |
  +-> OOS VFID: heap header has VFID? if not: oos_file_create()
  |
  +-> For each OOS candidate column:
  |   +-> oos_insert() -> returns OOS OID
  |
  +-> Build heap record:
      +-> variable area: OOS OID (16B) + IS_OOS flag in VOT
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
  +-> heap_record_replace_oos_oids_with_values_if_exists()
      +-> Iterate VOT: for each IS_OOS column
          +-> oos_read() -> fetch actual value from OOS file
      +-> Reconstruct full record (size expands significantly)
```

### Visible-version fetch family (CBRD-26847 census)

All "visible version" fetchers funnel into `heap_get_visible_version_internal`. OOS **Expand** is
opt-in via a single flag (`HEAP_GET_CONTEXT.expand_oos`, checked once in `heap_record_replace_oos_oids`,
`heap_oos.cpp`). Choosing rule: **a path needs Expand only if it consumes raw recdes bytes (ships to
client `LC_COPYAREA`, re-inserts into a heap, byte-compares, or `OR_BUF`-parses); otherwise the
attribute layer Resolves per column and the cheap fetch is correct AND faster.** See ADR
`docs/adr/0001-oos-expansion-is-opt-in.md` in the engine repo.

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
unresolved OOS OIDs — known instance `xlocator_fetch_all` → unloaddb/compactdb (`load_object.c` is
OOS-blind; tracked under CBRD-26583 / PR 7093).

### UPDATE (Always New OID — M1)

**3-step process:**

1. Determine OOS candidates for new record -> `oos_insert()` -> new OOS OIDs
2. Write updated heap record with new OOS OIDs
3. Previous heap record (with old OOS OIDs) saved to undo log as-is
4. Old OOS records remain alive — old transactions may access them via MVCC undo
5. When vacuum removes old heap record, `oos_delete()` cleans up old OOS records together

```
Before UPDATE:
  heap: [ ... | OOS OID (1|1|33) | 'bbbbb' ]
  OOS page 1, slot 33: 'aaaa...(4500B)'

UPDATE tbl SET vc2 = 'hello' WHERE id = 1;

Step 1: oos_insert -> new OOS OID
  OOS page 2, slot 44: 'aaaa...(4500B)'             <- new record

Step 2: Update heap record
  heap: [ ... | OOS OID (1|2|44) | 'hello' ]
  undo log: [ ... | OOS OID (1|1|33) | 'bbbbb' ]   <- old OOS OIDs preserved

Step 3: Old OOS record stays alive
  OOS page 1, slot 33: 'aaaa...(4500B)'              <- MVCC readers may need it
  -> vacuum will oos_delete when cleaning old heap record from undo log
```

**Key invariant**: One OOS OID is referenced by exactly one record (heap page or undo log). OOS OIDs are NOT shared between records.

**Current limitation**: Always creates a new OOS OID even if the value is unchanged. OOS OID reuse (deduplication) is **deferred to a future improvement** — it is NOT in M2 scope (M3, which had planned it, is cancelled). Verified against code: UPDATE always allocates fresh OIDs (`heap_attrinfo_insert_to_oos`), which the vacuum forward-walk relies on for old/new OID disjointness.

### DELETE

```
heap_delete()
  |
  +-> Add MVCC delete ID to record
  |   +-> Modified record stored back to heap page
  |
  +-> OOS OIDs: DO NOT TOUCH
      +-> OOS records NOT deleted (MVCC readers may need them)
      +-> OOS OIDs NOT resolved (heap page has 16KB limit)
      +-> Vacuum handles OOS cleanup later
```

**Why not delete immediately**: Deleted records still exist on heap page (MVCC). The 16KB page limit means we can't resolve OOS OIDs in-place (expanded record wouldn't fit). So OOS cleanup is deferred to vacuum.

---

## 4. Recovery, Replication & MVCC

### Recovery & Replication Invariants

These invariants MUST hold — test scenarios verify each one:

1. **WAL completeness**: Every OOS insert/delete is logged. After crash + recovery, OOS state matches the last committed transaction state.
2. **Undo correctness**: Update/delete undo retains the previous record **as-is, including its OOS OIDs** — undo does NOT store resolved values (that would bloat the undo log and defeat the whole point of OOS). Rollback restores the previous record, whose OOS OIDs still point to live OOS records; MVCC snapshot reads reconstruct the old version the same way (via `prev_version_lsa` → undo recdes → `oos_read`), which is exactly why old OOS records must survive until vacuum (see invariant 3). The vacuum forward-walk depends on this — it extracts OOS OIDs straight out of the undo recdes. _(Corrected 2026-06-02: the prior text claimed undo holds fully-resolved values with no OIDs, which contradicts invariant 3 and the code; it had misled a fix proposal toward deleting old OOS inline.)_
3. **No orphan OOS records after update**: On update, old OOS records remain for MVCC. When vacuum removes old heap record, `oos_delete()` cleans up old OOS records.
4. **Delete safety**: Deleted records retain OOS OIDs in heap. OOS records NOT deleted at delete time — they remain accessible until vacuum.
5. **Replication log completeness**: Replication log contains enough info to replay OOS operations on replica. OOS OIDs in replication log point to correct OOS pages on replica.
6. **OOS file <-> heap file 1:1**: Each heap file has at most one OOS file. The OOS VFID is stored in the heap header page.

### Replication Notes

- **Slave OOS OIDs may differ from master** — only value equality is guaranteed, not OID equality.
- Replication log must carry sufficient data for slave to perform its own `oos_insert` operations.

### Vacuum + OOS

- DELETE does not clean OOS. Vacuum handles cleanup when reclaiming dead heap records.
- Two possible approaches (to be decided): synchronous `oos_delete` during `vacuum_heap`, or dedicated OOS vacuum job.
- If vacuum crashes mid-OOS-delete: WAL redo completes the delete on recovery. If not yet logged: vacuum retries.

---

## 5. Known Bugs, Limitations & TODO

### Known Bugs

| Issue | Description | Impact | JIRA |
|---|---|---|---|
| unloaddb 1.6-1.7x slower | `heap_attrinfo_start` called per `heap_next` in `feat/oos` branch | Performance regression | CBRD-26458 |
| UPDATE calls `oos_read` 3x redundantly | `heap_record_replace_oos_oids_with_values_if_exists()` added to `locator_fetch()` but should only be in `locator_fetch_all()` (unloaddb) | Extra I/O | CBRD-26516 |
| CDC flashback OOS OID resolve | CDC flashback needs to replace OOS OIDs with actual values in recdes | Missing feature | — |
| Unnecessary OOS replication log in `locator_add_or_remove_index` | OOS replication log forced in unrelated context | Refactoring needed | — |
| RECDES length 4-byte limit | OOS recdes max size limited to 2GB (4-byte length). May need 8-byte extension for 16EB max | Design limitation | — |
| `spacedb`/`diagdb` can't see OOS space | `cubrid spacedb` counts `FILE_OOS` as heap (`file_manager.c:12236`, `assert_release(false)` workaround — no `SPACEDB_OOS_FILE`); OOS files store no parent HFID (`file_manager.c:1431`) so can't be attributed to a table | No release-build tool proves a row went OOS or how much space OOS uses per table — only debug `oos.log` does. Forces the OOS test merge-gate onto debug builds | QA tooling ask (CBRD-26871) |

### Limitations (Milestone 1)

| Limitation | Impact | Future Fix |
|---|---|---|
| No `oos_file_destroy` | OOS files grow indefinitely | M2 |
| ~~Bestspace = last-insert-page only~~ | ~~Hotspot on single page, wasted space~~ | **DONE** (CBRD-26658: 3-tier bestspace) |
| ~~Bulk-externalize every variable column > 512B~~ | ~~Small columns needlessly go OOS → extra `oos_read` I/O, OOS file bloat~~ | **DONE** (CBRD-26776: largest-first incremental demotion; record gate 2KB→4KB, column floor 512B→16B) |
| DELETE doesn't clean OOS | Orphan records until vacuum | M2 (vacuum integration) |
| No OOS OID reuse on update | Extra I/O when value unchanged | Future improvement (deduplication; M3 cancelled, not in M2) |
| Ordered fix deadlock risk | Two tx's accessing OOS pages in different order | Future improvement (M4 cancelled, not in M2) |
| No PEEK mode for OOS reads | Always COPY semantics, extra memcpy | Future |
| No across-page compaction | Fragmentation over time | Future |
| `S_DOESNT_FIT` handling incomplete | Caller must handle buffer overflow | Upper-layer |

### Optimization Ideas

**A. Update OOS OID reuse (CBRD-26516)** _(future improvement — was the cancelled M3 plan; not in M2)_: In `heap_attrinfo_set_uninitialized`, prevent reading OOS values via `heap_attrvalue_read` for unchanged columns. Reuse existing OOS OID instead of creating new one. **Prerequisite:** the vacuum forward-walk (`vacuum_forward_walk_delete_old_oos`) must first gain an old∩new OID sharing check, or it will delete an OID the live post-image still references.

**B. Defer `oos_insert` to `attrinfo_force` (Heesoo's idea)**: Unify `insert -> oos_log_insert -> oos_repl_log_insert` flow timing to `attrinfo_force`. This enables generating OOS replication log at the same time as heap record replication log, allowing PK inclusion in OOS replication log. Implementation: separate `oos_repl_log` function (existing repl log function overwrites LSA in sequence: `tail_lsa -> repl_insert_lsa -> repl_rec->lsa`, so OOS LSAs must be collected separately).

**C. Minimize `pgbuf_fix` for multiple `oos_insert`**: When multiple OOS values target the same page, perform `pgbuf_fix` once instead of per-insert.

**D. `oos_read` PEEK mode**: Current COPY mode requires allocating and freeing recdes each time. PEEK mode would avoid this. Requires removing `is_oos` parameter from `heap_attrvalue_transform_to_dbvalue()` and separating `spage_get_record` / `spage_insert` into OOS-specific variants.

**E. Ordered OOS page fix for deadlock prevention**: Enforce globally consistent page fix order (e.g., VPID ascending) to prevent deadlocks between transactions accessing the same OOS pages in different order.

### Design Discussions (2026/3/5 feedback)

- **Multi-column OOS storage**: Combine multiple OOS columns into one record vs. current per-column storage. Direction TBD.
- **OOS page latch contention**: Yechan's proposal — partition page into 4-64 sections with atomic latches. Deferred unless latch bottleneck becomes severe.
- **OVF + OOS simultaneous**: A record carrying OOS OIDs that would *also* become `REC_BIGONE` (recdes > ~16K overflow) is now **rejected** at write time with `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` (CBRD-26937), not silently built. Test the *rejection* (e.g. large fixed `BIT(n)`/`CHAR` + OOS varchar that stays > ~16KB after demotion) rather than coexistence.
- **CHAR type as OOS candidate**: Evaluate storing CHAR columns as OOS when they exceed threshold.
- **Per-column inline preference (CBRD-26912, proposed — NOT yet merged)**: `STORAGE PREFER_INLINE` column option (à la PG `SET STORAGE MAIN`) that pushes a hot column to the *back* of the largest-first demote order, so it's externalized only as a last resort. Soft only — the column still demotes if nothing else fits, preserving the "record always fits a page" invariant. Stored as a new `SM_ATTFLAG_OOS_PREFER_INLINE` bit; the sole policy change is adding it as the primary sort key in `heap_attrinfo_determine_disk_layout`.

---

## 6. Test Scenarios

### Testing Principles

- **Use `BIT VARYING` (VARBIT)**, NOT `VARCHAR`: CUBRID compresses strings, making disk size unpredictable. VARBIT is not compressed, so disk size is exact.
- **Pattern**: `CAST(REPEAT('AA', N) AS BIT VARYING)` produces N bytes on disk.
- **Size verification**: Use `DISK_SIZE(col)` (not `LENGTH` which returns bits).
- **Distinct values**: Use different hex patterns ('AA', 'BB', 'CC', etc.) to distinguish values.
- **OOS trigger**: record > 4KB (`DB_PAGESIZE/4` on 16KB pages); then the *largest* variable columns (value > 16B) are demoted one-by-one until the record fits — **not** every eligible column. To force OOS, make the record clear 4KB.

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
- **1.1 Insert + Select consistency**: Insert OOS record, verify `DISK_SIZE()` and value equality
- **1.2 Non-trigger verification**: Records below threshold stay in heap (no OOS)
- **1.3 Largest-first demotion (discriminating test for CBRD-26776)**: Record > 4K with two unequal eligible columns; verify only the largest is demoted and the smaller stays inline. Release builds can't see per-column OOS placement (`DISK_SIZE` returns the logical value size regardless), so confirm via debug `oos.log` `oos_insert ... src.size=` (CBRD-26871)
- **1.4 Bulk insert**: 100+ rows with varying sizes, verify all sizes correct

#### 2. UPDATE (3 tests)
- **2.1 OOS column value change**: Update OOS column, verify new value, old value physically deleted
- **2.2 Non-OOS column change**: Even changing non-OOS column creates new OOS OIDs (M1 behavior)
- **2.3 Repeated updates**: Multiple updates to same row, final value correct

#### 3. DELETE (2 tests)
- **3.1 Delete + verify gone**: DELETE row, verify `COUNT(*)` decreases
- **3.2 Delete all + reinsert**: DELETE all rows, INSERT new rows, verify table reusable

#### 4. ACID (4 tests)
- **4.1 Atomicity (ROLLBACK)**: INSERT + UPDATE in transaction, ROLLBACK, verify original state
- **4.2 UPDATE ROLLBACK**: OOS column UPDATE + ROLLBACK restores original OOS value via undo log
- **4.3 Durability**: COMMIT -> server restart -> data survives
- **4.4 Isolation (MVCC)**: Session 1 updates (uncommitted), Session 2 sees old value

#### 5. Crash Recovery (5 tests)
- **5.1 Committed INSERT redo**: INSERT + COMMIT + `kill -9` -> restart -> data present
- **5.2 Uncommitted INSERT undo**: INSERT (no commit) + `kill -9` -> restart -> data gone
- **5.3 Uncommitted UPDATE undo**: UPDATE (no commit) + crash -> original value restored (undo retains the previous record's OOS OIDs **as-is**; on rollback those OIDs still point to live OOS records — see invariant 2, NOT resolved values)
- **5.4 Mixed committed/uncommitted**: Committed data survives, uncommitted data undone
- **5.5 Multi-chunk crash recovery**: 50KB+ value (multi-chunk chain) survives crash

#### 6. MVCC Concurrency (3 tests)
- **6.1 UPDATE visibility**: Session 1 updates OOS (uncommitted), Session 2 reconstructs the old value via `prev_version_lsa` -> undo recdes -> `oos_read` (undo holds OOS **OIDs**, not resolved values — see invariant 2)
- **6.2 DELETE visibility**: Deleted OOS record still visible to earlier snapshot
- **6.3 Concurrent multi-UPDATE**: Different sessions update different rows simultaneously, values don't mix

#### 7. Multi-chunk OOS (3 tests)
- **7.1 Large value (>16KB)**: Insert 50KB value spanning multiple OOS pages, verify chain
- **7.2 Multi-chunk update**: Update multi-chunk OOS value, verify new chain correct
- **7.3 Mixed sizes**: Same table with single-chunk and multi-chunk OOS values

#### 8. Replication (4 tests)
- **8.1-8.4**: INSERT/UPDATE/DELETE/multi-chunk operations replicated correctly to slave. Verify value equality (OOS OIDs may differ between master and slave).

#### 9. Edge Cases (5 tests)
- **9.1 Record gate boundary**: Record exactly at 4KB (`DB_PAGESIZE/4`) boundary
- **9.2 Column eligibility floor**: Variable column ≤ 16B (`OR_OOS_INLINE_SIZE`) is never demoted, even when the record > 4KB (demoting it wouldn't shrink the record)
- **9.3 NULL values**: NULL in OOS-eligible column
- **9.4 Empty values**: Zero-length VARBIT in OOS-eligible column
- **9.5 Many OOS columns**: 10+ columns all OOS in single record
- **9.6 OOS + bigone rejection (CBRD-26937)**: Record with an OOS column + a large fixed `BIT(n)` that stays > ~16KB after demotion → INSERT/UPDATE rejected with `ER_HEAP_OOS_OVERPASS_MAXOBJ_SIZE` (-1375), row not stored. A non-OOS bigone, or an OOS record left between 4KB and ~16KB, still succeeds

#### 10. Stress Tests (2 tests)
- **10.1 Bulk 1000+ rows**: All with OOS, verify all values correct
- **10.2 Repeated updates 50+**: Same row updated 50+ times, final value correct

### Key Test SQL Pattern

```sql
-- OOS INSERT + verify (record must clear DB_PAGESIZE/4 = 4KB to trigger demotion)
CREATE TABLE t (id INT, vc1 BIT VARYING, vc2 BIT VARYING);
INSERT INTO t VALUES (1, CAST(REPEAT('AA', 3000) AS BIT VARYING),
                         CAST(REPEAT('BB', 2000) AS BIT VARYING));
-- Record ~5KB > 4KB → largest (vc1) demoted to OOS → ~2KB fits → vc2 stays inline

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
-- Expected: 1 (rollback restored the previous record, whose OOS OIDs still point to live OOS records)
```

---

## Milestones

- **M1** (Feb 2026, DONE): Basic POC — insert/read/update/delete, WAL, recovery, replication
- **M2** (active — umbrella for all remaining OOS work): Drop table, bestspace optimization, in-page compaction, vacuum integration, **largest-first OOS demotion (CBRD-26776, done) + OOS/bigone rejection (CBRD-26937)**
- ~~**M3** (was: OOS OID reuse on update / deduplication)~~ — **CANCELLED (2026-06-02).** OID reuse is deferred to a future improvement; it is NOT folded into M2 (current code always allocates a fresh OID — verified via `heap_attrinfo_insert_to_oos`). See **Limitations** and **Optimization Ideas → A**.
- ~~**M4** (TBD): Ordered fix deadlock handling, monitoring tools~~ — **CANCELLED (2026-06-02).** Deferred to future improvements; not in M2. (Ordered-fix deadlock prevention is also tracked under Limitations and Optimization Ideas → E.)

---

## Writing Conventions

When writing OOS-related code comments or documentation:

- Use **OOS OID** (not "pointer" or "OOS pointer")
- Use **OOS file** / **OOS record** (not "OOS storage")
- Always add a space between inline code and Korean text: `` `oos_read` 는 `` (not `` `oos_read`는 ``)
- Use exact thresholds (`DB_PAGESIZE/4` record gate, `OR_OOS_INLINE_SIZE` = 16B column floor) — the old `DB_PAGESIZE/8` / 512B values are pre-CBRD-26776 and must not be cited as current
- Each OOS OID is referenced by exactly one record — never imply sharing
- Do not describe unimplemented features as existing (no PEEK mode, no OOS dedup, no across-page compaction in M1)
