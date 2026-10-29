---
name: traceability
description: Use when creating, auditing, or updating a requirements traceability matrix; reconciling requirement or threat states; or checking implementation and verification evidence before declaring work complete.
---

# Traceability

Maintain `docs/requirements/traceability.md` as the canonical evidence ledger.
Report uncertainty; never manufacture a link, result, or completed state.

## Canonical row

| Field | Required content |
|---|---|
| ID | One stable requirement or threat ID; unique in the matrix |
| Source | Existing owning requirement or threat-model link |
| State | Exactly one allowed state |
| Specification | Existing behavioral specification link, or `—` when genuinely inapplicable |
| Implementation evidence | Existing code, config, migration, or immutable change evidence |
| Verification evidence | Existing test, check, report, or explicitly named external gate |
| Notes | Concise blocker, rationale, residual risk, or retirement reason |

Allowed states are `proposed`, `accepted`, `implemented`, `verified`, `blocked`,
and `retired`. Do not invent synonyms or combine states.

## Workflow

1. Inventory stable IDs from requirements and `docs/security/threat-model.md`.
2. Parse the matrix and report missing rows, duplicates, unknown IDs, invalid
   states, contradictory rows, and links that do not resolve.
3. Reconcile to exactly one row per ID. Preserve an unknown row as a reported
   defect until its authoritative source is restored or its retirement is
   evidenced; do not silently delete it.
4. Check evidence before changing state:
   - `accepted` requires an authoritative source.
   - `implemented` requires implementation evidence.
   - `verified` requires implementation and verification evidence.
   - `blocked` names the blocker and the evidence still required.
   - `retired` names the superseding decision or retirement evidence.
5. Validate trace chains:
   `requirement -> specification -> implementation -> verification` and
   `THREAT-* -> SEC-* -> specification -> control/code -> verification`.
6. Update only claims supported by the repository or a durable external
   artifact. A statement that a check “probably passed” is not evidence.
7. Re-scan IDs, links, states, and evidence after editing. Report what is fully
   traced, what is incomplete, and what remains externally blocked.

## Quick decisions

| Finding | Action |
|---|---|
| Duplicate ID | Merge supported facts; report contradictions |
| Missing ID | Add a conservative row from its authoritative source |
| Missing source | Mark/report blocked; do not fabricate or silently remove |
| Missing implementation evidence | State cannot exceed `accepted` |
| Missing verification evidence | State cannot exceed `implemented` |
| Unperformed external gate | Keep it explicitly outstanding |

## Common mistakes

- Treating a PR description, plan checkbox, or prose claim as verification.
- Linking a directory when a precise file, test, check, or report exists.
- Marking an entire feature verified when only one layer was tested.
- Replacing the active matrix with the blank starter template.
