# OOS context reorganization review

Document date: 2026-10-08. Baseline: context repository `0eab7df`.

Read when reviewing this reorganization or checking where baseline material moved. This records documentation verification, not new engine, GitHub, or JIRA verification.

The canonical [OOS-CONTEXT.md](../../OOS-CONTEXT.md) decreased from **60,044 bytes / 627 lines** to **29,627 bytes / 295 lines**. It meets the approximate 20–30 KB target. All required behavior stays in that file, including requirements previously embedded in status notes or accepted ADR consequences. The loader path is unchanged; its context-file override and complete-read/reuse policy remain authoritative in the existing skill.

| Baseline material | Maintained destination and manual review |
|---|---|
| Trigger, physical target, eligibility, inline preference, bigone guard | Canonical §1; preserves the formula, unfill independence, 24B profitability floor, preference grouping, stop/exhaustion behavior, estimate caveat, and pre-insert rejection |
| Layout, chunk chain, identity policies | Canonical §2; preserves sizes/flags, reverse insertion/forward read, per-chunk pre-insert stamp, logged recovery preservation, no-logging exception, field bounds, stale-reference handling, eager diagnostics |
| Bestspace and accepted enumeration | Canonical §2; preserves hints/cache/latches, direct fit check, bitmap enumeration, read-only deallocation tolerance, insert-path strictness, skipped-page observability |
| CRUD and accepted ownership | Canonical §3; replaces contradictory M1 prescriptions with accepted CBRD-27230 reuse, newest-version ownership, borrowed undo references, commit-conditional notification ordering, identity prerequisite, and replica markers |
| Recovery, replication, vacuum, reclaim | Canonical §4; retains all six invariant topics, replica-local references, cleanup atomicity, eventual page reclaim, LSA horizon/deferral, fast-path batch ordering, growth cursor/counter/boot rule, with the old legacy-file skip retained as an implementation observation |
| Completed security/lifecycle obligations and release decisions | Canonical §5; retains DROP cleanup, TDE before VFID publication, LOB lifecycle separation, complete CDC/flashback deferral, disk 11.5, visible CDC failures, and ADR-0005's PR-specific history/CI policy |
| Ownership writing convention | Points to accepted §3; exclusive-version ownership is labelled historical |
| Repeated implementation narratives and bug/limitation status | [Implementation observations](../reference/implementation-observations.md), one entry per issue; dated heads retained and unpinned claims labelled |
| M1 flow, comparisons, old reuse proposal, discussions/milestones | [Design history](../reference/design-history.md); older reuse deferral/sharing-check proposal explicitly superseded |
| SQL examples and scenario catalogue | [Test recipes](../reference/test-recipes.md); UPDATE 2.2 uses accepted reuse, and below-gate examples distinguish INSERT from retained UPDATE stubs |

Each moved reference has conditional entry points in the specification and [CLAUDE.md](../../CLAUDE.md). CDC/flashback vocabulary is discoverable through those same routes. Existing `CONTEXT.md`, five ADRs, and the scratch interview remain byte-for-byte unchanged; ADR-0004's supersession and ADR-0005's release scope remain intact.

## Loading-policy walkthrough

This was a **manual wording review** against the completed loader and the revised pointers. Automatic skill selection was not run.

| Request/session condition | Expected path verified in the wording |
|---|---|
| Review OOS behavior or implementation against accepted requirements | Select the loader and read the complete specification |
| Routine OOS PR/CI status | Use PR/CI evidence; specification loading is not triggered by the OOS label |
| Loader maintenance | Use loader/task evidence; specification loading is not required for that maintenance |
| Continue the same review with complete active context and unchanged resolved path/SHA-256 | Reuse under the loader's policy |
| Changed content/path, unknown fingerprint, or only a compaction summary | Fresh complete read under the loader's policy |

The task specification was read through EOF using `CUBRID_OOS_CONTEXT_FILE` with matching fingerprints before/after. Local Markdown targets, heading fragments, relocated relative paths, and supporting cross-repository evidence paths were checked. `git diff --check` and the full semantic diff review complete the documentation checks; no engine tests were run for this change.

## Evidence limits and remaining pointer

Identity progress is reconciled using the completed-repair report updated **2026-09-11**, head `eaf1165bb` over `f4299ac0c`; the earlier `c09d6c6d9` snapshot and September 9 context label are preserved in its maintained entry. No repair-completion claim is promoted to a merge claim. Unpinned PR-absence, experimental-branch, milestone, and ticket observations remain historical evidence requiring verification for current answers.

The separate legacy Claude memory at `/home/vimkim/.claude/projects/-home-vimkim-gh-cb-cbrd-26609-oos-delete/memory/reference_oos_knowledge_base.md` still requires fetching the vault for any OOS mention; its sibling `MEMORY.md` repeats that pointer. Those files remain outside this repository task. Local integration requires the user's rebase/fast-forward merge approval; pushing requires a separate request.
