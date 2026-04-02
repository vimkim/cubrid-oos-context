# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Repository Is

This is **not** a code repository. It is the **single source of truth for AI agent context** about the CUBRID OOS (Out-of-row Overflow Storage) project.

The sole artifact is `OOS-CONTEXT.md` — a curated, AI-optimized knowledge base compiled from multiple sources (vault docs, JIRA tickets, design discussions). It exists so that any Claude Code session working on CUBRID OOS can load comprehensive project context by reading one file.

## How It's Used

The `/cubrid-oos-context` skill (defined in `~/.agents/skills/cubrid-oos-context/SKILL.md`) auto-triggers when OOS-related code or topics come up in a CUBRID worktree. That skill reads `OOS-CONTEXT.md` from this directory to prime the agent with architecture, CRUD flows, known bugs, test patterns, and design decisions.

**This file is loaded at the start of OOS work sessions, not edited programmatically.** The user manually updates it when the OOS project evolves (new bugs found, features completed, design decisions made).

## Editing OOS-CONTEXT.md

When updating this file:

- Keep it **AI-optimized**: structured for fast comprehension, no web/HTML formatting, no Marp slide markers
- **Update the "Last updated" date** in the header when making changes
- Mark completed limitations/bugs with ~~strikethrough~~ and note the resolution (e.g., `**DONE** (CBRD-XXXXX)`)
- Add new JIRA tickets to the Quick Reference table when they become relevant
- Keep total size reasonable (~20-30KB) — this gets loaded into context every OOS session
- The companion human-readable vault lives at `~/gh/cubrid-oos-vault/` but is NOT the source of truth for AI context

## Source Material

OOS-CONTEXT.md was compiled from:
- `~/gh/cubrid-oos-vault/content/CLAUDE.md` — core knowledge base
- `~/gh/cubrid-oos-vault/AGENTS.md` — OOS architecture deep reference
- `~/gh/cubrid-oos-vault/content/oos-todo.md` — bugs and optimization ideas
- `~/gh/cubrid-oos-vault/content/OOS-Presentation.md` — design rationale, DB comparisons
- `~/gh/cubrid-oos-vault/content/OOS-Test-Scenarios.md` — test patterns

These are reference material, not dependencies. OOS-CONTEXT.md is the living document.
