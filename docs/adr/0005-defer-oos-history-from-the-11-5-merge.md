---
status: accepted
---

# Defer OOS historical images from the 11.5 merge

Accepted with the user on 2026-09-22 for CBRD-26939 and PR #7990. Defer the complete CDC/flashback OOS-history change from the CUBRID 11.5 OOS merge: durable supplemental images, reader behavior, compatibility changes, activation machinery, new CDC error handling, and the associated CCI update. PR #7990 must retain disk compatibility 11.5.

## Release and compatibility model

CUBRID 11.5 is unreleased and OOS is still under active feature-branch development. Databases and logs produced by those pre-release feature branches have no compatibility guarantee across revisions; recreate them when the storage or log format changes. Do not manufacture a CUBRID 11.6 disk-compatibility level or a one-way database activation state to preserve compatibility between those artifacts.

This supersedes ADR-0004's activation and compatibility contract for the 11.5 merge. The durable-supplemental-image approach remains useful research and a candidate direction, but it is not an accepted implementation contract until its encoding and compatibility model are redesigned.

## Test and pull-request policy

Keep the CDC regression cases `cbrd_27064` and `cbrd_27075` enabled and visibly failing. Do not exclude, mask, or rewrite them to make PR #7990 green. Their failures document the deferred CBRD-26939 gap and will be remedied by later work.

Close engine PR #7897 and CCI PR #112 without rewriting their history. Their implementation depended on the rejected 11.6 activation design. Preserve the branches and research as evidence for the redesign. Retain the public and private testcase PRs associated with PR #7990 because they correct independent, non-CDC expectation drift.

The unrelated intermittent `issue_11202_temp_volume_create` failure is outside this decision and remains untouched.

## Consequences

The PR #7990 correction is an additive revert, published by ordinary fast-forward commits only. No force-push, amend, rebase, or history rewrite is permitted. After local verification and review, run the full PR CI and distinguish the two expected CDC failures from unrelated failures.

Future CBRD-26939 work must reconsider the supplemental-image encoding, publication ordering, reader failure behavior, and compatibility enforcement in the actual release model. ADR-0004's durability analysis may inform that work but does not pre-approve its implementation.
