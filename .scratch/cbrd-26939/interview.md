# CBRD-26939 design interview

## Design tree

- Historical-value lifetime: durable supplemental images (Q1 accepted).
  - Supplemental image failure: originating write fails through normal rollback (Q4 accepted).
  - Image encoding: new subtype is viable; final detail follows reader contract.
  - Upgraded engines/readers required before new-format writes; downgrade unsupported, enforcement required (Q6 accepted).
    - Existing disk-compatibility startup check can fence old engines; independent HA readers require coordinated upgrade. Migration/activation policy is Q7 frontier.
- Historical coverage: guarantee new history, explicitly fail unreconstructible legacy OOS history (Q2 accepted).
  - Legacy OOS references with no trustworthy identity: reject unresolved legacy OOS images instead of live-storage best effort (Q5 accepted).
- PR success scope: both current failures; separate bug_bts_4633 diagnosis (Q3 accepted).
- After frontier settles: reconcile complete contract with user, then specification and implementation tickets.

## Round 1

User answered “yes recommended” to Q1–Q3. Accepted decisions are in docs/adr/0004-durable-oos-supplemental-images.md. Implementation follows full-contract shared-understanding confirmation under the grilling flow; the user has authorized the overall repair objective.

## Factual investigation

Read-only agent cdc_format_facts checked source at 2940b1c. Existing supplemental raw images lack an explicit expanded-image guarantee. DML metadata stores image LSAs, so a new image subtype can preserve existing DML layouts. Undo accepts supplemental data; redo needs an equivalent case. CDC and flashback share cdc_get_recdes. Unknown types are not an automatic old-reader safety gate: the old undo reader ignores subtype, the redo reader lacks support, and event dispatch can default-skip unknown types. Supplemental append currently returns void and can return early on allocation failure; its callers can still report success. Correctness requires checked failure propagation.

Source anchors: log_record.hpp:422; log_manager.c:4889,4944,4999,9893,11075,11488,11688; flashback.c:947,990,1050; log_recovery.c:3983.

## Round 2

User answered “as recommended” to Q4–Q6. ADR-0004 updated. New supplemental images must be checked writes; unresolved legacy OOS images fail explicitly; upgraded readers are required and downgrade after new-format writes is unsupported. Compatibility enforcement is being investigated before final contract confirmation.

## Verification contract to carry into specification

- Supported INSERT/UPDATE/DELETE before/after values are byte-correct after confirmed vacuum and delayed consumption, including later changes to an initially inserted row.
- Shared CDC/flashback decoding; all_in_cond=0/1; multiple OOS attributes and chunks; 4KB/8KB/16KB pages.
- Rollback, failure injection during image construction/publication, restart/recovery, archive rollover, compression on/off, trigger/relocation/partition paths where applicable.
- Supplemental logging disabled retains existing write behavior. Existing schema-change/archive-unavailability contracts remain applicable; historical images do not promise unavailable schema or external LOB payload retention.
- Legacy non-OOS history remains readable; unresolved legacy OOS history reports a checked error. Verify old-reader restriction at the identified enforcement seam.
- Original cbrd_27064 and cbrd_27075 regression coverage, then fresh-commit CI. Track bug_bts_4633 independently.
- Measure WAL and serialization overhead; no numeric performance threshold has been invented.

## Compatibility fact result and round 3 frontier

Old engines enforce disk compatibility before recovery (log_manager.c:1274–1286), but a release/log-version change is not a strict fence. A global disk-level bump without upgrade rules would reject ordinary 11.5 databases too. Old HA copied-log readers do not validate the same field (log_applier.c:2663–2705), and archive headers lack such a field (log_storage.hpp:230–247). Therefore engine-open enforcement and coordinated reader rollout are both needed.

Q7 pending: support explicit one-way in-place activation for existing databases enabling durable OOS history, or require a separate recreation/migration path? Recommend explicit feature-scoped in-place activation, preserving existing non-OOS history and enforcing upgraded engine/readers; do not globally change ordinary databases. Concrete marker, persistent ordering, startup and backup/restore validation belong to specification after agreement.

## Round 3

User answered “yes” to Q7: explicit one-way feature-scoped in-place activation, preserving existing data and readable non-OOS history, upgraded engines/readers before activation, compatibility restriction persisted before new images, ordinary inactive DBs unchanged. ADR-0004 updated.

New frontier: Q8 offline versus online activation; Q9 new-database format initialization. These are operational choices, not a request for exact marker values or implementation APIs. CDC testcase setup creates new databases after setting supplemental_log=1, so a fresh-database policy must make supported test behavior explicit.

## Round 4 and final confirmation

User answered “yex” (yes) to the recommended Q8–Q9 policies. Existing database activation requires clean shutdown and an offline transition; fresh databases use current format immediately, with supplemental logging controlling image emission and old-engine opening unsupported even before first OOS use. ADR updated. All Q1–Q9 decisions are settled. Final consolidated-contract confirmation is pending under grilling; specification and implementation tickets follow that confirmation.

Consequences to state in final contract: an existing inactive database may not write new-format images; an operation requiring durable OOS supplemental history must receive an activation-required error until activation, rather than silently emit unsupported history. Compatibility enforcement covers engine opening and coordinated reader rollout; the disk header guard alone does not fence old independent log readers.

## Proceeding confirmation

The user answered “yes” after the round-4 acceptance and transition announcement. Treat Q1–Q9 as confirmed and proceed to the concrete specification/ticket breakdown; do not request another architecture confirmation. Next review is the actual proposed test seams and ticket granularity required by to-spec/to-tickets, not reopening accepted architecture.
