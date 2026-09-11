# OOS Historical Change Values

Vocabulary for the CDC and flashback design. Existing OOS storage terms are defined in [OOS-CONTEXT.md](OOS-CONTEXT.md).

## Language

**Before image**:
The logical row values immediately before a recorded change.

**After image**:
The logical row values immediately after a recorded change.

**Supported OOS history**:
Recorded OOS changes for which the engine guarantees reconstruction of the required before/after images while their historical logs remain available.

**Legacy OOS history**:
OOS changes recorded before durable supplemental image support, whose historical values may depend on OOS chains already reclaimed.
