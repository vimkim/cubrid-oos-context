# OOS design history and proposals

Last updated: 2026-10-08 (document modification).

Read when explaining an earlier behavior, milestone, alternative, or optimization proposal. This file is **non-normative**. Material moved from `OOS-CONTEXT.md` at repository commit `0eab7df` retains its source dates; unpinned descriptions are historical context, not current implementation claims. Required behavior remains in [OOS-CONTEXT.md](../../OOS-CONTEXT.md).

## Supersession timeline

| Source date | Earlier rule or proposal | Accepted successor |
|---|---|---|
| M1; replaced 2026-06-18 (CBRD-26776, PR #7158) | `DB_PAGESIZE/8` (2KB) gate; externalize every variable value >512B with no sorting/stop | Largest-first incremental demotion, initially with a fixed quarter-page gate and >16B profitability floor |
| 2026-07-13 (CBRD-27057) | Fixed quarter-page gate | Physical four-record heap-capacity target; [§1](../../OOS-CONTEXT.md#1-what-is-oos) contains the accepted formula |
| 2026-08-13 (CBRD-27230) | M1 exclusive-version ownership, always-new UPDATE chains, undo-image forward-walk cleanup, earlier sharing-check reuse proposal, June reuse deferral | Newest-version ownership, borrowed undo references, UPDATE-unassigned reuse, commit-conditional notifications; [§3](../../OOS-CONTEXT.md#update-ownership-and-chain-reuse-cbrd-27230) |
| 2026-09-04; policy reconciliation recorded 2026-09-09 (CBRD-26950) | 16B stub/header and rejected slot-0 counter proposal | 24B layout with pre-insert page-LSA identity stamp; [identity evidence entry](implementation-observations.md#cbrd-26950-identity-stamp-repair) retains the successive PR heads |
| 2026-09-22 (ADR-0005) | ADR-0004 durable-history implementation direction and activation/compatibility contract | Complete deferral from PR #7990 / 11.5 and reopened design; [release scope](../../OOS-CONTEXT.md#cdcflashback-deferred-from-the-115-merge) |

The largest-first rule survived the gate and stub-size changes. The old >16B floor is historical; accepted eligibility uses the 24B stub. `STORAGE PREFER_INLINE` is accepted merge scope, not the older “proposed” label; its implementation evidence belongs under [CBRD-26912](implementation-observations.md#cbrd-26912-inline-preference).

## M1 UPDATE and vacuum

The following sequence records the superseded M1 ownership model. It is useful for interpreting old code/reviews, but does not prescribe UPDATE or cleanup behavior. The always-new-chain/forward-walk mechanism was documented before the accepted design of 2026-08-13; the cleanup description cited CBRD-26668 / PR #6986 without pinning its function line numbers to a commit.

### Historical UPDATE sequence

**Historical sequence:**

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
  -> M1 vacuum would oos_delete when cleaning old heap record from undo log
```

**Ownership invariant (M1, superseded on paper)**: Each OOS value chain is owned by exactly one logical heap-record version. OOS value chains are not shared across record versions. The inline stub stores the head OOS OID; non-head OOS OIDs are linked from the preceding chunk record.

### Historical cleanup paths

In the recorded M1 MVCC implementation, DELETE/UPDATE did not clean OOS value chains inline; vacuum reclaimed them when it reclaimed the dead heap-record versions that owned them. The source description recorded these paths (`vacuum_oos.cpp`, `heap_oos.cpp`):

1. **Forward-walk (MVCC old versions)** — `vacuum_forward_walk_oos_delete_atomic` (`vacuum_oos.cpp:154`): pulls old head OOS OIDs straight out of the UPDATE/DELETE undo recdes (relies on canonical recovery invariant 2) and `oos_delete`s their value chains. Runs in *its own* sysop with no enclosing sysop, so a mid-walk failure rolls back only its own deletes.
2. **Within-sysop (current record)** — `vacuum_heap_oos_delete_within_sysop` (`vacuum_oos.cpp:383`): deletes OOS value chains owned by a heap record being vacuumed, inside the caller's sysop.
3. **Eager (non-MVCC / SA_MODE)** — `heap_oos_delete_unreferenced` (`heap_oos.cpp:425`): single-process mode has no vacuum, so old value chains are deleted synchronously at UPDATE time, comparing old and new head OOS OIDs to keep any chain the post-image still references.

The 2026-06-02 correction established that undo contains stubs, not expanded values. That representation remains required, while using the undo image as an OOS deletion source is superseded. The rollback data-loss evidence and repair status belong in the [CBRD-27237 entry](implementation-observations.md#cbrd-27237-rollback-and-vacuum).

## Storage design background

The comparison below retains the older database/design background. Its M1 UPDATE row is explicitly historical. Read the canonical specification for accepted gates, layouts, and reuse semantics; this comparison establishes no current PostgreSQL/MySQL product claim.

### Comparison with Other Databases

| | PostgreSQL (TOAST) | MySQL (Off-page) | CUBRID OOS (carried comparison) |
|---|---|---|---|
| **Trigger** | `MaximumBytesPerTuple(4)` (~2KB), independent of fillfactor | ~8KB (row) | PG-style four-record heap target (4,060B with current 16KB I/O page layout), independent of unfill; value > 24B |
| **Stop semantics** | Largest-first, stop when row fits | Largest-first | **Largest-first, stop when record fits (CBRD-26776)** |
| **Separation** | Column-level | Column-level | Column-level |
| **Inline reference size** | 18B | 20B | **24B** (OOS inline stub) |
| **Compression** | pglz / lz4 | COMPRESSED format | None; see the compression proposal history below |
| **Storage** | TOAST table | Overflow pages | OOS file (FILE_OOS) |
| **Chunk split** | ~2KB chunks | Page-unit chain | OOS page-unit chain |
| **UPDATE reuse** | Unchanged values keep inline reference | Unchanged values keep inline reference | Always new chain (historical M1; superseded by accepted CBRD-27230) |

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

Accepted decisions already have maintained rationale in [ADR-0001](../adr/0001-oos-page-enumeration-non-numerable.md) (enumeration), [ADR-0002](../adr/0002-oos-lob-locator-demotion.md) (LOB eligibility), and [ADR-0003](../adr/0003-oos-expansion-is-opt-in.md) (Expand). CDC/flashback analysis is in [ADR-0004](../adr/0004-durable-oos-supplemental-images.md), under [ADR-0005](../adr/0005-defer-oos-history-from-the-11-5-merge.md)'s superseding release scope.

## Proposals and deferred optimizations

Candidates B–E and the discussion notes below were carried without exact source revisions. They remain proposals or historical implementation descriptions. Candidate A was superseded by an accepted design; see the timeline above. The OVF+OOS coexistence idea was superseded by the canonical [OOS+bigone rejection](../../OOS-CONTEXT.md#oos--bigone-rejection-cbrd-26937), whose recipe is in [test scenarios](test-recipes.md#9-edge-cases-6-tests).

### Earlier optimization candidates

**A. Historical reuse proposal (CBRD-26516; superseded 2026-08-13)**: In `heap_attrinfo_set_uninitialized`, prevent resolving OOS values via `heap_attrvalue_read` for unchanged attributes. Reuse the existing value chain/head OOS OID instead of creating a new chain. **Earlier proposed prerequisite:** add an old∩new head-OID sharing check to the vacuum forward-walk. The accepted CBRD-27230 design instead removes that forward-walk and uses commit-conditional notifications; this candidate is not the implementation contract.

**B. Defer `oos_insert` to `attrinfo_force` (Heesoo's idea)**: Unify `insert -> oos_log_insert -> oos_repl_log_insert` flow timing to `attrinfo_force`. This enables generating OOS replication log at the same time as heap record replication log, allowing PK inclusion in OOS replication log. Implementation: separate `oos_repl_log` function (existing repl log function overwrites LSA in sequence: `tail_lsa -> repl_insert_lsa -> repl_rec->lsa`, so OOS LSAs must be collected separately).

**C. Minimize `pgbuf_fix` for multiple `oos_insert`**: When multiple OOS values target the same page, perform `pgbuf_fix` once instead of per-insert.

**D. `oos_read` PEEK mode**: The carried COPY-mode description required allocating and freeing recdes each time. PEEK mode would avoid this. Requires removing `is_oos` parameter from `heap_attrvalue_transform_to_dbvalue()` and separating `spage_get_record` / `spage_insert` into OOS-specific variants.

**E. Ordered OOS page fix for deadlock prevention**: Enforce globally consistent page fix order (e.g., VPID ascending) to prevent deadlocks between transactions accessing the same OOS pages in different order.

### Proposed Design Discussions — Non-normative (2026/3/5 feedback)

- **Multi-attribute OOS storage**: Combine multiple OOS values into one physical record vs. the recorded one-value-chain-per-attribute design. Direction TBD.
- **OOS page latch contention**: Yechan's proposal — partition page into 4-64 sections with atomic latches. Deferred unless latch bottleneck becomes severe.
- **OOS value compression (DEFERRED to future — not M2, not built)**: Investigation (CBRD-26756) initially landed on a 2026-05-08 meeting lean toward compressing at the **common OOS-entry point** (PG TOAST `EXTENDED`-style: try compress → if still big, store OOS), covering every variable type going to OOS — the source notes reported only `VARCHAR` is LZ4-compressed (at the type/OR layer, ≥255B); `VARNCHAR`/`VARBIT`/`JSON`/`SET`/`MULTISET`/`SEQUENCE` are not compressed anywhere. CBRD-26881 then reframed the real fork as **type-serialization layer (`mr_data_writeval`)** vs **OOS boundary**, deferring the choice to ANALYSIS. **Direction recorded in the source notes (CTO): defer compression to a future milestone and, when done, control it at the data-type serialization layer (`mr_data_writeval`), NOT the OOS layer** — this supersedes the earlier OOS-entry lean in CBRD-26756. The source notes reported no compression code in `oos_file.cpp`/`heap_oos.cpp`; no engine revision was recorded for that observation. (Beware: the two tickets label their options "A"/"B" in *opposite* directions — describe by layer location, not letter.)
- **CHAR type as OOS candidate**: Evaluate storing CHAR columns as OOS when they exceed threshold.

## Milestone snapshots

- **M1** (Feb 2026, DONE): Basic POC — insert/read/update/delete, WAL, recovery, replication
- **M2** (recorded as active in the old planning notes — umbrella for remaining OOS work): Drop table, bestspace optimization, in-page compaction, vacuum integration, **largest-first OOS demotion (CBRD-26776, done) + OOS/bigone rejection (CBRD-26937)**
- ~~**M3** (was: OOS value-chain reuse on update / deduplication)~~ — **CANCELLED (2026-06-02).** At cancellation, reuse was deferred and described as outside M2, with fresh chains observed in `heap_attrinfo_insert_to_oos` (no source revision recorded). The 2026-08-13 accepted CBRD-27230 design supersedes that reuse deferral; the cancelled milestone label does not exclude the accepted requirement.
- ~~**M4** (TBD): Ordered fix deadlock handling, monitoring tools~~ — **CANCELLED (2026-06-02).** Deferred to future improvements; not in M2. (See candidate E above.)

## Original source material

The original context was compiled from the human-readable `~/gh/cubrid-oos-vault/`:
`content/CLAUDE.md` (core knowledge), `AGENTS.md` (architecture), `content/oos-todo.md` (bugs/ideas), `content/OOS-Presentation.md` (rationale/comparisons), and `content/OOS-Test-Scenarios.md` (tests). These are supporting references, not dependencies or substitutes for the canonical specification.
