# CLAUDE.md

## Repository Purpose

This documentation repository is the authoritative agent context for CUBRID OOS (Out-of-row Overflow Storage). [OOS-CONTEXT.md](OOS-CONTEXT.md) holds all normative requirements. [CONTEXT.md](CONTEXT.md) defines CDC/flashback vocabulary; `docs/adr/` holds accepted decisions and rationale. Focused references hold dated implementation observations, history, and test recipes.

## Loading Context

**Specification dependency:** consult the [cubrid-oos-context loader](/home/vimkim/.agents/skills/cubrid-oos-context/SKILL.md) when an answer depends on required behavior, accepted design, or implementation/test conformance. Use its load-or-reuse policy and `CUBRID_OOS_CONTEXT_FILE` override; it owns the detailed complete-read and fingerprint rules.

Routine CI/PR status, scheduling, wording edits, and loader maintenance use their task evidence. When such a task expands into a behavioral question, apply the specification-dependency check to that question.

**CDC/flashback:** read [CONTEXT.md](CONTEXT.md) for historical-value terms and the specification's release-scope section for which ADR decisions apply.

**Implementation or progress:** read [implementation observations](docs/reference/implementation-observations.md), then verify the relevant revision/live state if the answer needs current facts.

**Earlier decisions or proposals:** read [design history](docs/reference/design-history.md) and the relevant ADR.

**Regression preparation:** read [test recipes](docs/reference/test-recipes.md) and derive expected behavior from the canonical specification.

## Maintaining the Documents

Authorized updates belong in this repository. Keep required behavior together in `OOS-CONTEXT.md`; move only non-normative evidence, history, recipes, or rationale behind explicit reading conditions. Aim for roughly 20–30 KB in the canonical file while retaining every requirement.

- Update `Last updated` for document modifications. Give implementation observations their own verification date and exact revision; a document edit does not refresh those facts.
- Maintain one observation entry per issue in `docs/reference/implementation-observations.md`; link to it from other documents. Preserve earlier evidence dates/heads when recording a successor. Label missing dates or revisions explicitly.
- Separate accepted requirements, implementation conformance gaps, proposals, and superseded history. Acceptance, a resolved ticket, and a passing experimental branch each establish different facts.
- Apply each ADR's scope and supersession notice. Preserve decision history; documentation maintenance does not authorize new OOS design decisions.
- Check local links, relocated relative links, and supporting evidence paths, then review the semantic diff and run `git diff --check`.

The human-readable `~/gh/cubrid-oos-vault/` is supporting material. Its original source list is retained in [design history](docs/reference/design-history.md#original-source-material).

For review of the October 8 reorganization, read the [coverage and validation record](docs/maintenance/2026-10-08-context-review.md).
