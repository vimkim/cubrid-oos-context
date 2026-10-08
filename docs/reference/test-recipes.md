# OOS test recipes

Last updated: 2026-10-08 (document modification).

Read when preparing SQL test data or choosing regression coverage. These are **non-normative recipes**, moved from repository revision `0eab7df`; they are not new test-run results or proof of feature availability. Derive expected behavior from [OOS-CONTEXT.md](../../OOS-CONTEXT.md), and check the relevant [implementation observation](implementation-observations.md) before interpreting a capability gap. Use the native SQL/shell/medium or configured unit-test workflow appropriate to the task.

## Test scenarios

### Testing Principles

- **Use `BIT VARYING` (VARBIT)**, NOT `VARCHAR`: CUBRID compresses strings, making disk size unpredictable. VARBIT is not compressed, so disk size is exact. _(Carried compression assumption, not reverified here; if future type-layer compression — CBRD-26756/26881 — ever extends to VARBIT, disk size stops being exact and this rule needs revisiting.)_
- **Pattern**: `CAST(REPEAT('AA', N) AS BIT VARYING)` produces N bytes on disk.
- **Size verification**: Use `DISK_SIZE(col)` (not `LENGTH` which returns bits).
- **Distinct values**: Use different hex patterns ('AA', 'BB', 'CC', etc.) to distinguish values.
- **Expected placement**: derive the gate, eligibility, ordering, inline preference, and stop conditions from canonical [§1](../../OOS-CONTEXT.md#1-what-is-oos). `DISK_SIZE` alone cannot prove placement.

### Demotion worked examples

These INSERT examples use ordinary candidates under the stated 16KB layout. For inline preference or UPDATE with retained stubs, apply canonical §1/§3: preference changes candidate order, and a reused stub can remain below the demotion gate.

```
record > oos_inline_target ?
 ├─ no  → all values inline (no OOS)
 └─ yes → candidates = variable values with size > 24B, sorted by size DESC
           for cand in candidates:
             record already ≤ oos_inline_target ?  → break
             demote cand to OOS; payload -= cand_size; payload += 24B
           candidates exhausted above target? → apply OOS+bigone rejection rule
```

Example with the current 16KB layout (target = 4,060B):

- Record ~2.3KB ≤ 4,060B → OOS not triggered (under the old M1 rule this *would* have triggered at the 2KB gate)
- Record ~5KB (vc1=3000B + vc2=2000B) → demote largest (vc1) → record ~2KB ≤ 4,060B → **break**. Only vc1 goes to OOS; vc2 stays inline.
- Record ~9KB (vc1=4500B + vc2=4500B) → demote vc1 → ~4.5KB still > 4,060B → demote vc2 → fits. Both go to OOS.

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
- **1.2 Non-trigger verification**: INSERT records below the gate with no existing stubs stay inline; UPDATE may retain reused stubs below the gate
- **1.3 Largest-first demotion (discriminating test for CBRD-26776)**: Record > the OOS inline target with two unequal eligible columns; verify only the largest values needed to reach the target are demoted. The carried test notes report no release-build per-attribute placement channel (`DISK_SIZE` returns the logical value size regardless), so confirm via debug `oos.log` `oos_insert ... src.size=` ([CBRD-27350 observation](implementation-observations.md#cbrd-27350-oos-observability))
- **1.4 Bulk insert**: 100+ rows with varying sizes, verify all sizes correct

#### 2. UPDATE (3 tests)

- **2.1 OOS-backed attribute value change**: Update an OOS-backed attribute, verify the new value and eventual cleanup of the old value chain
- **2.2 Inline attribute change**: accepted CBRD-27230 expects an unassigned OOS attribute to retain its head OOS OID and identity stamp. Record fresh chains as a historical M1/conformance observation, not a passing normative oracle; see [UPDATE requirements](../../OOS-CONTEXT.md#update-ownership-and-chain-reuse-cbrd-27230).
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
- **5.3 Uncommitted UPDATE undo**: UPDATE (no commit) + crash -> original value restored (undo retains the previous record's OOS inline stubs **as-is**; on rollback their head OOS OIDs still point to live value chains — see [recovery invariant 2](../../OOS-CONTEXT.md#recovery--replication-invariants), NOT resolved values)
- **5.4 Mixed committed/uncommitted**: Committed data survives, uncommitted data undone
- **5.5 Multi-chunk crash recovery**: 50KB+ value (multi-chunk chain) survives crash

#### 6. MVCC Concurrency (3 tests)

- **6.1 UPDATE visibility**: Session 1 updates OOS (uncommitted), Session 2 reconstructs the old value via `prev_version_lsa` -> undo recdes -> `oos_read` (undo holds OOS inline stubs, not resolved values — see [recovery invariant 2](../../OOS-CONTEXT.md#recovery--replication-invariants))
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
- **9.2 Column eligibility floor**: Variable value ≤ 24B (`OR_OOS_INLINE_SIZE`) is never demoted, even when the record exceeds the target (demoting it would not shrink the record)
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

### Accepted-design coverage beyond the older catalogue

When testing UPDATE reuse, include unassigned-stub preservation, assigned-equal-value replacement, UPDATE→ROLLBACK→vacuum→read, committed notification recovery, and master/replica-local reference handling. This applies the canonical §3/§4 contract, not the old M1 chain-count expectation. The disabled rollback regression and its historical revision are recorded under [CBRD-27237](implementation-observations.md#cbrd-27237-rollback-and-vacuum).

For identity or reclaim tests, take the oracle from canonical §2/§4 and read the [identity](implementation-observations.md#cbrd-26950-identity-stamp-repair) or [reclaim](implementation-observations.md#cbrd-26786-empty-page-reclaim) evidence entry for revision-specific verification. Required CDC failures remain visible under [§5 release scope](../../OOS-CONTEXT.md#cdcflashback-deferred-from-the-115-merge); the test catalogue does not authorize masking them.
