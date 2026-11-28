---
name: cubrid-oos-context
description: Consult the authoritative CUBRID Out-of-row Overflow Storage specification only when an answer depends on required OOS behavior, accepted design, or implementation/test conformance. Routine CI status, scheduling, wording edits, and loader maintenance use their own task evidence.
---

# CUBRID OOS Context

This skill loads the authoritative **OOS (Out-of-row Overflow Storage)** specification for CUBRID tasks that need its requirements or design rationale.

$ARGUMENTS

## Step 0: Check scope

Identify the OOS requirement or design decision needed to answer the request. Continue to Step 1 when explaining required behavior or assessing design, implementation, defects, or test expectations against the specification.

Routine CI or PR status checks, scheduling, wording edits, and maintenance of this loader use task-specific evidence. Finish this workflow here for those requests; context loading, workspace validation, and OOS evidence reconciliation apply only after the scope check passes. Treat an OOS mention, branch name, PR title, or ticket label as a task identifier; select this workflow based on the question to answer.

If a routine request expands into a behavioral question, apply the scope check to that question.

## Step 1: Load or reuse the source of truth

Resolve the authoritative file and check its content fingerprint only after the scope check passes:

```bash
skill_dir="${CLAUDE_SKILL_DIR:-$HOME/.agents/skills/cubrid-oos-context}"
recorded_root="$(cat "$skill_dir/.repo-root" 2>/dev/null || true)"
git_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
context_file=""
for candidate in \
  "${CUBRID_OOS_CONTEXT_FILE:-}" \
  "${recorded_root:+$recorded_root/OOS-CONTEXT.md}" \
  "${git_root:+$git_root/OOS-CONTEXT.md}" \
  "$HOME/gh/cubrid-oos-context/OOS-CONTEXT.md"; do
  if [[ -n "$candidate" && -r "$candidate" ]]; then
    context_file="$(realpath -- "$candidate")"
    break
  fi
done
test -n "$context_file"
sha256sum -- "$context_file"
```

Reuse a previous complete read when its recorded resolved path and SHA-256 still match and the full contents remain available in the active session context. Otherwise read `$context_file` through EOF without truncation, confirm its fingerprint is unchanged across the read, and retain its resolved path and fingerprint for later turns. A changed file, a different resolved path, an unknown prior fingerprint, or a summary left by compaction requires a fresh complete read.

Resolve relative links such as `docs/adr/...` against the directory containing that file and read the linked document when its decision or rationale is relevant.

If the file is missing or unreadable, stop and report the resolved path. Do not substitute remembered OOS facts, the summary from a previous turn, or any deleted quick reference.

`OOS-CONTEXT.md` is the normative specification and single source of truth for OOS. This skill is only its loader and usage policy; it must not duplicate thresholds, layouts, invariants, ticket states, milestone dates, or implementation status.

## Step 2: Validate the workspace when needed

Run the bundled validation script when the request involves source inspection, implementation, debugging, building, or testing:

```bash
bash "${CLAUDE_SKILL_DIR:-$HOME/.agents/skills/cubrid-oos-context}/scripts/validate-env.sh" "$PWD"
```

Do not run it for a documentation-only or conceptual question unless the answer requires checking the current implementation. The script checks that:

- You're in a **git repository** (or worktree) — needed for code search, grep, and git features
- The directory is a **CUBRID source tree** (has `CMakeLists.txt` + `CMakePresets.json`)
- **OOS source files** exist (`oos_file.cpp` — indicates OOS sources are present on this branch)
- **PRESET_MODE** is set and a **build directory** exists (`build_preset_*`)
- **compile_commands.json** is present at the project root — this is essential for LSP features (hover, goto-definition, find-references via `clangd`)
- **clangd** and **just** are available

**If the script reports errors (exit code 1):**
- Warn the user about what's missing and how to fix it
- If `compile_commands.json` is missing, tell the user to run `just build` (which generates it via CMake's `CMAKE_EXPORT_COMPILE_COMMANDS=ON`) and then symlink it: `ln -sf build_preset_${PRESET_MODE}/compile_commands.json .`
- If not in a git repo, suggest switching to a CUBRID worktree
- Continue any safe work that does not depend on the missing capability, and state the limitation

**If the script reports only warnings (exit code 0):**
- Note the warnings but proceed normally — the environment is usable

## Step 3: Check freshness and reconcile evidence

Treat volatile statements in the context file—ticket status, branch status, line numbers, milestone dates, and labels such as proposed, pending, open, or merged—as dated observations, not timeless facts.

When the request depends on current state:

1. Note the context file's `Last updated` date.
2. Check the current worktree branch and relevant source/history.
3. For a named CBRD ticket or live ticket status, use `cubrid-jira` (if available) and consult any configured local JIRA notes repository as supporting context.
4. Consult any configured local OOS design-notes or documentation repository for newer OOS notes, reviews, and verification reports before searching the web.

Use this authority and reconciliation rule:

- The normative context file (`OOS-CONTEXT.md`) and accepted ADRs (`docs/adr/NNNN-*.md`) are the single Source of Truth (SoT) for required OOS behavior, terminology, layout, invariants, and accepted decisions.
- The official CBRD JIRA hub issue ([CBRD-28315](https://jira.cubrid.org/browse/CBRD-28315), Sub-task under `CBRD-26357`) is a one-way mirror of this SoT for colleagues. If the JIRA mirror differs from the SoT, treat the SoT as authoritative and report the sync drift.
- The checked-out source is evidence of what that exact revision currently implements; it does not override the specification.
- JIRA is authoritative for current ticket workflow state.
- Local reports and reviews are supporting evidence, not automatically accepted design.

If source and specification disagree, classify the difference as an implementation conformance gap unless the specification explicitly marks the behavior proposed, historical, or non-normative. State the conflict and identify the revision/date involved. Ask for clarification only when the specification itself is ambiguous or internally inconsistent.

## Step 4: Answer or act

- Distinguish current implementation, accepted design, proposed work, known defect, and historical behavior.
- Do not treat incomplete OOS implementations or temporary merge-readiness instrumentation as normative behavior.
- Use the terminology and writing conventions from the context file. When citing OOS ADRs in JIRA, PRs, or reviews, use the standard `OOS-ADR-NNNN` identifier (for example `OOS-ADR-0001` through `OOS-ADR-0011`), state `accepted` vs `proposed` and `last_updated`, and link [CBRD-28315](https://jira.cubrid.org/browse/CBRD-28315) when helpful for colleagues.
- Cite source functions, commits, tickets, or `OOS-ADR-NNNN` entries when they materially support a claim.
- Do not describe an experimental or feature branch implementation as merged into `develop` without verification.
- When asked to update OOS knowledge, edit the authoritative context repository (`cubrid-oos-context`) rather than adding facts to this loader or editing JIRA directly. After any Spec or ADR edit, follow `docs/maintenance/jira-sync.md` in `cubrid-oos-context`: run `scripts/check-jira-sync.py` and `scripts/render-jira-sync.py` to prepare JIRA sync dry-run payloads, and never run `cubrid-jira ... --yes` or `git push` without explicit user approval.
