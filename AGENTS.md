# CLAUDE.md

## Repository Purpose

This documentation repository is the authoritative agent context for CUBRID OOS (Out-of-row Overflow Storage). [OOS-CONTEXT.md](OOS-CONTEXT.md) holds all normative requirements. [CONTEXT.md](CONTEXT.md) defines CDC/flashback vocabulary; `docs/adr/` holds accepted decisions and rationale. Focused references hold dated implementation observations, history, and test recipes.

## Loading Context

**Specification dependency:** consult the `cubrid-oos-context` skill loader when an answer depends on required behavior, accepted design, or implementation/test conformance. Use its load-or-reuse policy and `CUBRID_OOS_CONTEXT_FILE` override; it owns the detailed complete-read and fingerprint rules.

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

Earlier supporting notes (`cubrid-oos-vault`, historical) are retained as non-normative background. Their original source list is retained in [design history](docs/reference/design-history.md#original-source-material).

For review of the October 8 reorganization, read the [coverage and validation record](docs/maintenance/2026-10-08-context-review.md).

## Official JIRA Mirror & Sync Policy

- **Single Source of Truth (SoT) and JIRA mirror:** This repository (`main` at `https://github.com/vimkim/cubrid-oos-context`) is the authoritative Source of Truth. The official company JIRA mirror is [CBRD-28315](https://jira.cubrid.org/browse/CBRD-28315) (Sub-task under [CBRD-26357](https://jira.cubrid.org/browse/CBRD-26357), related to [CBRD-26978](https://jira.cubrid.org/browse/CBRD-26978)). Never edit JIRA ahead of this repository; all Spec/ADR updates flow one way from GitHub SoT to JIRA.
- **Standard ADR naming and dates:** Refer to ADRs in JIRA, PRs, and reviews as `OOS-ADR-NNNN` (for example `OOS-ADR-0001` through `OOS-ADR-0011`). Maintain `id`, `status`, `last_updated` (`YYYY-MM-DD`), and `jira_issues` in each ADR's YAML frontmatter; keep `last_updated` aligned with the ADR's substantive decision date rather than mechanical metadata sweeps.
- **Sync workflow on Spec/ADR changes:** Whenever `OOS-CONTEXT.md`, `CONTEXT.md`, or `docs/adr/NNNN-*.md` is added or modified:
  1. Update the authoritative English document and its Korean JIRA summary under `docs/maintenance/jira-ko/`, then update `docs/maintenance/jira-sync-manifest.json` after review.
  2. Run `python3 scripts/check-jira-sync.py` to detect any drift between SoT files and the JIRA manifest.
  3. Commit and push the SoT changes to GitHub `main` first so links resolve against the pushed revision.
  4. Run `python3 scripts/render-jira-sync.py --drifted` (or `--all`) to validate links/BMP/lint and generate dry-run `cubrid-jira` commands, then execute `--yes` updates only after explicit human confirmation and record the resulting `comment_id`, `source_sha256`, `ko_sha256`, and `synced_commit` in `docs/maintenance/jira-sync-manifest.json`.
  See [JIRA sync workflow](docs/maintenance/jira-sync.md) for the full procedure and manifest schema.
- **Public hygiene:** Do not embed personal filesystem paths (`/home/...`, `~/...`), personal viewer URLs, private scratch paths (`temp/`), or internal tracker IDs (`WorkNNN`) in `AGENTS.md`, `OOS-CONTEXT.md`, `CONTEXT.md`, `docs/adr/`, `docs/reference/`, or `docs/maintenance/jira-ko/`. Use public GitHub/JIRA URLs or concise inline summaries.
