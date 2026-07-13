---
status: accepted
---

# OOS record expansion is opt-in for raw-byte consumers

## Context and Decision

The visible-version heap fetchers (`heap_get_visible_version`, `heap_scan_get_visible_version`,
`heap_get_last_version`) do not Expand OOS inline stubs by default. Expanding every OOS-backed
attribute on every fetch would re-read the values OOS is designed to keep out of the hot path.

**Decision:** OOS Expand is opt-in. Only `heap_get_visible_version_expand_oos` sets
`HEAP_GET_CONTEXT.expand_oos = true`, the flag checked by `heap_record_replace_oos_oids`.

Choose the fetch variant according to how the resulting `RECDES` is consumed:

- **Expand — record-level, eager, whole-record.** Use `heap_get_visible_version_expand_oos` only
  when the `RECDES` is consumed as raw bytes: shipped in a client `LC_COPYAREA`, re-inserted into
  another heap, byte-compared, or parsed through an `OR_BUF`. These consumers cannot tolerate OOS
  inline stubs.
- **Resolve — attribute-level, lazy.** Use the cheap `heap_get_visible_version` when the `RECDES`
  is read through the attribute layer (`heap_attrinfo_read_dbvalues` →
  `heap_attrvalue_read_oos_inline` → `oos_read`), or when only fixed/header/CHN data or existence is
  needed. The attribute layer Resolves only the accessed attributes.

In short: a path needs Expand only if it consumes raw `RECDES` bytes; otherwise the attribute
layer Resolves individual OOS-backed attributes.

## Considered Options

- **Always Expand.** Rejected because it nullifies OOS I/O savings on hot paths such as SP-code
  fetch, UPDATE old-version reads, and join scans.
- **Opt-in Expand (chosen).** The default fetch stays cheap; raw-byte consumers explicitly Expand.

## Consequences

1. The CBRD-26847 census identified five raw-byte consumers that require Expand:
   `xlocator_lock_and_fetch_all`, `redistribute_partition_data`, `catcls_delete_instance`,
   `catcls_update_instance`, and `catcls_update_class_stats`.
2. The mirror-image hazard is a raw-byte path that forgets to Expand and leaks OOS inline stubs to
   an OOS-unaware consumer. `xlocator_fetch_all` → unloaddb/compactdb is the known example.
3. New callers must justify the selected contract. The `_expand_oos` function suffix signals that
   the resulting `RECDES` may leave the attribute layer.
