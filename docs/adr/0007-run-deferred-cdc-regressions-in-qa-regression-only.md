---
status: accepted
---

# Run the deferred-CDC regressions in QA regression only, not develop CI

> **Partially supersedes [ADR-0005](0005-defer-oos-history-from-the-11-5-merge.md)'s test policy.** ADR-0005's deferral of CBRD-26939 and its other decisions are unchanged.

Accepted with the user on 2026-10-27 for PR #7990 and CBRD-26939, answering item 5 of [review 5662427700](https://github.com/CUBRID/cubrid/pull/7990#pullrequestreview-5662427700). The reviewer asked for a team decision on merging with the CDC regressions quarantined. ADR-0005 kept `cbrd_27064` and `cbrd_27075` enabled and visibly failing in PR #7990's CI to document the deferred gap. After the merge, that policy would put the same two known failures into the gha-ci `test_shell` result of every `develop` pull request.

## Decision

The author agreed with the QA team:

- `cbrd_27064` and `cbrd_27075` are disabled on `develop` CI. [Private-ex PR #4210](https://github.com/CUBRID/cubrid-testcases-private-ex/pull/4210) moves them to `shell/_25_unstable/_37_elderberry/cbrd_23842_cdc/bug/`, which gha-ci `test_shell` excludes.
- Both cases keep running in the QA regression, where their failures stay visible. Their expectations are not rewritten and their failures are not masked.
- OOS + CDC support is implemented separately in CBRD-26939. The cases document that gap until then.

This replaces ADR-0005's "keep them enabled and visibly failing" test policy and its expectation that full PR CI shows the two CDC failures. Full PR CI no longer runs these cases; their results come from the QA regression.

## Consequences

1. Until CBRD-26939 lands, `develop` carries the known CDC gap for rows with OOS-backed attributes. The reviewer reported it as a CDC extraction error (`rc=-10`) on UPDATE/DELETE.
2. A gha-ci pass does not cover these two cases. CDC regressions for OOS are judged from the QA regression.
3. The `_25_unstable` readme moves a case back to its original place after it passes 5 runs in a row.

## Evidence

Private-ex PR #4210 (branch `tc/pr-7990`, open on 2026-10-27, head `75a02020e`) contains the move. Engine `.github/workflows/gha-ci.yml` at PR #7990 head `dcbf09e` sets `"exclude": "_25_unstable"` for `test_shell`. The QA agreement is recorded from the author's statement of 2026-10-27; the review workspace held no separate written record of it.
