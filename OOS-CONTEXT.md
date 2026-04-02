# CUBRID OOS (Out-of-row Overflow Storage) — AI Agent Context

> Single source of truth for AI agents working on CUBRID OOS implementation and debugging.
> Last updated: 2026-04-03 | Branch: `feat/oos` | Milestone: M2 in progress

## Quick Reference

| Concept | Detail |
|---------|--------|
| OOS trigger | record > `DB_PAGESIZE/8` (2KB on 16KB pages) AND column > 512B |
| OOS file type | `FILE_OOS`, one per heap file (1:1 mapping) |
| OOS pointer | 8-byte OOS OID (volid 2B + pageid 4B + slotid 2B) in variable area |
| HAS_OOS flag | MVCC header bit 3 (`OR_MVCC_FLAG_HAS_OOS = 0x08`) |
| IS_OOS flag | VOT entry bit 0 (`OR_VAR_BIT_OOS = 0x1`) |
| Key sources | `heap_file.c`, `oos_file.cpp`, `object_representation.h`, `object_representation_constants.h` |
| Branch | `feat/oos` |
| JIRA | CBRD-26517 (main), CBRD-26458 (unloaddb perf), CBRD-26516 (redundant oos_read), CBRD-26637 (error handling), CBRD-26658 (3-tier bestspace) |

### Core Terminology

| Term | Definition |
|------|-----------|
| OOS Record | Column data split from heap record, stored in OOS file |
| OOS File | FILE_OOS type file, 1:1 with heap file (one per table) |
| OOS Page | Slotted page within OOS file (size = DB_PAGESIZE) |
| OOS OID | 8-byte pointer (volid, pageid, slotid) stored in heap record's variable area |
| HAS_OOS flag | Record-level MVCC header flag — true if any column is OOS |
| IS_OOS flag | Per-column flag in variable offset table entry |
| OOS Resolve | Replacing OOS OIDs with actual values (expands record size) |

---

## 1. What is OOS?

**OOS (Out-of-row Overflow Storage)** separates large variable-length columns from heap records into dedicated OOS files to reduce unnecessary disk I/O. Instead of reading a full 3KB record for a 4-byte ID, only small columns are read from the heap.

```
AS-IS:
[ id | name | big_text (1.7KB) | big_blob (2KB) ]  <- entire heap record

TO-BE:
[ id | name | OOS OID (8B) | OOS OID (8B) ]        <- compact heap record
                  |                |
                  v                v
           [ big_text ]     [ big_blob ]             <- OOS file (separate)
```

### Trigger Conditions

Two conditions must BOTH be met for a column to be stored as OOS:

1. **Record threshold**: `header + payload + mvcc_extra > DB_PAGESIZE / 8`
2. **Column condition**: `is_variable && column_size > 512 bytes`

Example with DB_PAGESIZE=16K (threshold = 2KB):
- Record ~1.5KB <= 2KB -> OOS not triggered
- Record ~2.1KB > 2KB, vc1=1700B > 512B -> vc1 goes to OOS, vc2=400B stays in heap
- Record ~2.3KB > 2KB, both columns > 512B -> both go to OOS

---

## 2. Architecture & Design

### CUBRID Storage Context

- **Heap file**: One per table. Contains slotted pages. Each page holds multiple records via a slot directory.
- **Overflow page**: When a single record exceeds one page, CUBRID chains overflow pages. OOS addresses the variable-column dimension specifically.
- **MVCC (Multi-Version Concurrency Control)**: In-place MVCC — records carry insert/delete transaction IDs in their MVCC header.
- **WAL (Write-Ahead Logging)**: All modifications logged before being applied to pages.
- **Vacuum**: Background process that reclaims space from records no longer visible to any active transaction.

### Comparison with Other Databases

| | PostgreSQL (TOAST) | MySQL (Off-page) | CUBRID OOS (M1) |
|---|---|---|---|
| **Trigger** | ~2KB (row) | ~8KB (row) | record > PAGESIZE/8 + column > 512B |
| **Separation** | Column-level | Column-level | Column-level |
| **Pointer size** | 18B | 20B | **8B** (OOS OID) |
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
|  (flags+txn ids) |  Table (VOT)     |  Cols |  (values or 8-byte OOS OIDs)   |
+------------------+------------------+-------+--------------------------------+

VOT Entry (per variable column):
  [offset_value (30 bits) | RESERVED (1 bit) | IS_OOS (1 bit)]

  IS_OOS = 1  ->  variable area contains OOS OID (8 bytes) at this offset
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

---

## 3. CRUD Flows

### INSERT

```
heap_insert()
  |
  +-> heap_attrinfo_determine_disk_layout()
  |   +-> record > PAGESIZE/8?
  |       each variable column > 512B -> mark as OOS candidate
  |
  +-> OOS VFID: heap header has VFID? if not: oos_file_create()
  |
  +-> For each OOS candidate column:
  |   +-> oos_insert() -> returns OOS OID
  |
  +-> Build heap record:
      +-> variable area: OOS OID (8B) + IS_OOS flag in VOT
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
  OOS page 1, slot 33: 'aaaa...(1700B)'

UPDATE tbl SET vc2 = 'hello' WHERE id = 1;

Step 1: oos_insert -> new OOS OID
  OOS page 2, slot 44: 'aaaa...(1700B)'             <- new record

Step 2: Update heap record
  heap: [ ... | OOS OID (1|2|44) | 'hello' ]
  undo log: [ ... | OOS OID (1|1|33) | 'bbbbb' ]   <- old OOS OIDs preserved

Step 3: Old OOS record stays alive
  OOS page 1, slot 33: 'aaaa...(1700B)'              <- MVCC readers may need it
  -> vacuum will oos_delete when cleaning old heap record from undo log
```

**Key invariant**: One OOS OID is referenced by exactly one record (heap page or undo log). OOS OIDs are NOT shared between records.

**M1 limitation**: Always creates new OOS OID even if value unchanged. OOS OID reuse planned for M3.

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
2. **Undo correctness**: Update undo log contains fully-resolved OOS values (no OOS OIDs in undo records). Rollback restores actual previous column values.
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

### Limitations (Milestone 1)

| Limitation | Impact | Future Fix |
|---|---|---|
| No `oos_file_destroy` | OOS files grow indefinitely | M2 |
| ~~Bestspace = last-insert-page only~~ | ~~Hotspot on single page, wasted space~~ | **DONE** (CBRD-26658: 3-tier bestspace) |
| DELETE doesn't clean OOS | Orphan records until vacuum | M2 (vacuum integration) |
| No OOS OID reuse on update | Extra I/O when value unchanged | M3 (deduplication) |
| Ordered fix deadlock risk | Two tx's accessing OOS pages in different order | M4 |
| No PEEK mode for OOS reads | Always COPY semantics, extra memcpy | Future |
| No across-page compaction | Fragmentation over time | Future |
| `S_DOESNT_FIT` handling incomplete | Caller must handle buffer overflow | Upper-layer |

### Optimization Ideas

**A. Update OOS OID reuse (CBRD-26516)**: In `heap_attrinfo_set_uninitialized`, prevent reading OOS values via `heap_attrvalue_read` for unchanged columns. Reuse existing OOS OID instead of creating new one.

**B. Defer `oos_insert` to `attrinfo_force` (Heesoo's idea)**: Unify `insert -> oos_log_insert -> oos_repl_log_insert` flow timing to `attrinfo_force`. This enables generating OOS replication log at the same time as heap record replication log, allowing PK inclusion in OOS replication log. Implementation: separate `oos_repl_log` function (existing repl log function overwrites LSA in sequence: `tail_lsa -> repl_insert_lsa -> repl_rec->lsa`, so OOS LSAs must be collected separately).

**C. Minimize `pgbuf_fix` for multiple `oos_insert`**: When multiple OOS values target the same page, perform `pgbuf_fix` once instead of per-insert.

**D. `oos_read` PEEK mode**: Current COPY mode requires allocating and freeing recdes each time. PEEK mode would avoid this. Requires removing `is_oos` parameter from `heap_attrvalue_transform_to_dbvalue()` and separating `spage_get_record` / `spage_insert` into OOS-specific variants.

**E. Ordered OOS page fix for deadlock prevention**: Enforce globally consistent page fix order (e.g., VPID ascending) to prevent deadlocks between transactions accessing the same OOS pages in different order.

### Design Discussions (2026/3/5 feedback)

- **Multi-column OOS storage**: Combine multiple OOS columns into one record vs. current per-column storage. Direction TBD.
- **OOS page latch contention**: Yechan's proposal — partition page into 4-64 sections with atomic latches. Deferred unless latch bottleneck becomes severe.
- **OVF + OOS simultaneous**: Need test cases where CHAR column causes recdes > 16K (overflow) AND varchar > 512B (OOS) simultaneously.
- **CHAR type as OOS candidate**: Evaluate storing CHAR columns as OOS when they exceed threshold.

---

## 6. Test Scenarios

### Testing Principles

- **Use `BIT VARYING` (VARBIT)**, NOT `VARCHAR`: CUBRID compresses strings, making disk size unpredictable. VARBIT is not compressed, so disk size is exact.
- **Pattern**: `CAST(REPEAT('AA', N) AS BIT VARYING)` produces N bytes on disk.
- **Size verification**: Use `DISK_SIZE(col)` (not `LENGTH` which returns bits).
- **Distinct values**: Use different hex patterns ('AA', 'BB', 'CC', etc.) to distinguish values.
- **OOS trigger**: record > 2KB AND column > 512B (for 16KB pages).

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
- **1.3 Partial activation**: Record > 2K but only columns > 512B go to OOS
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
- **5.3 Uncommitted UPDATE undo**: UPDATE (no commit) + crash -> original value restored (tests undo log with resolved OOS values)
- **5.4 Mixed committed/uncommitted**: Committed data survives, uncommitted data undone
- **5.5 Multi-chunk crash recovery**: 50KB+ value (multi-chunk chain) survives crash

#### 6. MVCC Concurrency (3 tests)
- **6.1 UPDATE visibility**: Session 1 updates OOS (uncommitted), Session 2 sees old value via MVCC undo (where resolved original values are stored)
- **6.2 DELETE visibility**: Deleted OOS record still visible to earlier snapshot
- **6.3 Concurrent multi-UPDATE**: Different sessions update different rows simultaneously, values don't mix

#### 7. Multi-chunk OOS (3 tests)
- **7.1 Large value (>16KB)**: Insert 50KB value spanning multiple OOS pages, verify chain
- **7.2 Multi-chunk update**: Update multi-chunk OOS value, verify new chain correct
- **7.3 Mixed sizes**: Same table with single-chunk and multi-chunk OOS values

#### 8. Replication (4 tests)
- **8.1-8.4**: INSERT/UPDATE/DELETE/multi-chunk operations replicated correctly to slave. Verify value equality (OOS OIDs may differ between master and slave).

#### 9. Edge Cases (5 tests)
- **9.1 Threshold boundary**: Record exactly at 2KB boundary
- **9.2 Column at 512B boundary**: Column exactly 512B (should NOT trigger OOS)
- **9.3 NULL values**: NULL in OOS-eligible column
- **9.4 Empty values**: Zero-length VARBIT in OOS-eligible column
- **9.5 Many OOS columns**: 10+ columns all OOS in single record

#### 10. Stress Tests (2 tests)
- **10.1 Bulk 1000+ rows**: All with OOS, verify all values correct
- **10.2 Repeated updates 50+**: Same row updated 50+ times, final value correct

### Key Test SQL Pattern

```sql
-- OOS INSERT + verify
CREATE TABLE t (id INT, vc1 BIT VARYING, vc2 BIT VARYING);
INSERT INTO t VALUES (1, CAST(REPEAT('AA', 1700) AS BIT VARYING),
                         CAST(REPEAT('BB', 600) AS BIT VARYING));

-- Verify size
SELECT id, DISK_SIZE(vc1), DISK_SIZE(vc2) FROM t WHERE id = 1;
-- Expected: 1, 1700, 600

-- Verify value equality
SELECT (vc1 = CAST(REPEAT('AA', 1700) AS BIT VARYING)),
       (vc2 = CAST(REPEAT('BB', 600) AS BIT VARYING))
FROM t WHERE id = 1;
-- Expected: 1, 1

-- ROLLBACK test
COMMIT;
UPDATE t SET vc1 = CAST(REPEAT('CC', 1700) AS BIT VARYING) WHERE id = 1;
ROLLBACK;
SELECT (vc1 = CAST(REPEAT('AA', 1700) AS BIT VARYING)) FROM t WHERE id = 1;
-- Expected: 1 (rollback restored original via undo log with resolved values)
```

---

## Milestones

- **M1** (Feb 2026, DONE): Basic POC — insert/read/update/delete, WAL, recovery, replication
- **M2** (3/10-4/17, IN PROGRESS): Drop table, bestspace optimization, in-page compaction, vacuum integration
- **M3** (4/20-5/29, PLANNED): OOS OID reuse on update (deduplication)
- **M4** (TBD): Ordered fix deadlock handling, monitoring tools

---

## Writing Conventions

When writing OOS-related code comments or documentation:

- Use **OOS OID** (not "pointer" or "OOS pointer")
- Use **OOS file** / **OOS record** (not "OOS storage")
- Always add a space between inline code and Korean text: `` `oos_read` 는 `` (not `` `oos_read`는 ``)
- Use exact thresholds (512B, DB_PAGESIZE/8)
- Each OOS OID is referenced by exactly one record — never imply sharing
- Do not describe unimplemented features as existing (no PEEK mode, no OOS dedup, no across-page compaction in M1)
