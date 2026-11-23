# OOS Spec/ADR Official JIRA Sync Workflow

This document defines the one-way synchronization procedure between this repository (the authoritative Source of Truth, `main` at `https://github.com/vimkim/cubrid-oos-context`) and the official company JIRA hub issue [CBRD-28315](https://jira.cubrid.org/browse/CBRD-28315) (Sub-task under [CBRD-26357](https://jira.cubrid.org/browse/CBRD-26357), related to [CBRD-26978](https://jira.cubrid.org/browse/CBRD-26978)).

## Ownership and Naming Rules

1. **GitHub SoT first:** Never edit JIRA ahead of this repository. Every Spec or ADR change is authored, reviewed, and committed here first.
2. **Standard ADR identifier:** Refer to ADRs in JIRA, PRs, and reviews as `OOS-ADR-NNNN` (for example `OOS-ADR-0001` through `OOS-ADR-0011`).
3. **ADR frontmatter:** Every file under `docs/adr/` begins with YAML frontmatter containing:
   - `id`: `OOS-ADR-NNNN`
   - `status`: `accepted` or `proposed` (or `superseded` if retired)
   - `last_updated`: `YYYY-MM-DD` (substantive decision/document date)
   - `jira_issues`: list of related CBRD keys
4. **JIRA layout:**
   - The **description** of `CBRD-28315` mirrors `docs/maintenance/jira-ko/hub-description.md` (SoT metadata, `OOS-CONTEXT.md` + `CONTEXT.md` summary, `OOS-ADR-0001`~`NNNN` master index table with `Last updated`, and non-normative reference index).
   - Each ADR has a **1:1 comment** (`OOS-ADR-NNNN`) on `CBRD-28315` backed by `docs/maintenance/jira-ko/OOS-ADR-NNNN.md`. Updates modify the existing comment in place via `cubrid-jira comment-update --id <comment_id>`.
5. **Public hygiene:** No personal filesystem paths (`/home/...`, `~/...`), personal viewer hosts, scratch directories (`temp/`), or internal tracker IDs (`WorkNNN`) may appear in synchronized documents or Korean JIRA drafts.

## Manifest Schema (`docs/maintenance/jira-sync-manifest.json`)

- `hub_issue`: Target CBRD key (`CBRD-28315`), URL, `parent_epic` (`CBRD-26357`), `relates_epic` (`CBRD-26978`), `source_repo`, and `synced_commit`.
- `hub_description`: `source_files` (`OOS-CONTEXT.md`, `CONTEXT.md`) with `source_sha256` map, `ko_file` (`docs/maintenance/jira-ko/hub-description.md`), and `ko_sha256`.
- `adrs`: Ordered array of entries with `id`, `source_file`, `status`, `last_updated`, `source_sha256`, `ko_file`, `ko_sha256`, `comment_id` (`null` until created on JIRA), and `jira_issues`.

## Update Procedure (When Adding or Modifying Spec/ADR)

1. **Edit SoT and Korean JIRA draft:**
   - Update `OOS-CONTEXT.md`, `CONTEXT.md`, or `docs/adr/NNNN-*.md` (update `last_updated` on substantive ADR edits or add a new ADR file and frontmatter).
   - Update `docs/maintenance/jira-ko/hub-description.md` (sync commit note, Spec summary if affected, master ADR table) and `docs/maintenance/jira-ko/OOS-ADR-NNNN.md`.
2. **Detect drift locally:**
   ```bash
   python3 scripts/check-jira-sync.py
   ```
3. **Validate and render dry-run commands:**
   ```bash
   python3 scripts/render-jira-sync.py --drifted
   ```
   Verify that BMP, public-hygiene, shared-link, and `cubrid-jira lint` checks pass.
4. **Push SoT first:** Commit and push this repository to `origin main` so all GitHub links in JIRA point to committed content.
5. **Apply JIRA updates after explicit approval:** Run the printed `cubrid-jira` dry-run commands first, obtain explicit human approval, then run them with `--yes` (`update` for hub description, `comment` for new ADRs, `comment-update --id <comment_id>` for modified ADRs).
6. **Record synced state:** Update `synced_commit`, `source_sha256`, `ko_sha256`, and any new `comment_id` in `docs/maintenance/jira-sync-manifest.json`, rerun `python3 scripts/check-jira-sync.py` (expect exit `0`), and commit the updated manifest.
