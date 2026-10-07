---
name: docs-reconciliation
description: Use when documentation has drifted, completed work remains in backlogs, findings or decisions are scattered, dated plans have become stale, or durable content must be promoted before old documentation is pruned.
---

# Documentation reconciliation

Restore one current home for every durable fact, then prune obsolete artifacts.
Never delete first and reconstruct intent afterward.

**REQUIRED SUB-SKILL:** Use `docs-structure` for ownership and `traceability`
before declaring reconciliation complete.

## Reconciliation order

1. Inventory living requirements, specifications, architecture, security docs,
   open `backlog` issues, traceability, findings, and dated plans/specs.
2. Classify every unique statement:

| Content | Living owner |
|---|---|
| Outcome, constraint, acceptance criterion | `docs/requirements/` |
| Interface, schema, state transition, error, exact behavior | `docs/specifications/` |
| Current components, boundaries, dependencies, deployment | `docs/architecture/` |
| Threat, mitigation, assumption, residual risk, control | `docs/security/` |
| Unresolved work | GitHub issue labeled `backlog` (plus a severity label) |
| Deliberate decision future reviews must not reopen | Owning module page → `## Settled decisions — do not reopen` |
| Implementation or verification proof | `docs/requirements/traceability.md` |

3. Promote durable content into its owner. Merge duplicates without weakening
   normative wording. Preserve stable IDs and section numbers.
4. Reconcile tracked work:
   - close the `backlog` issues for completed work;
   - keep unresolved work as open `backlog` issues;
   - keep deliberate settled decisions in the owning module page's
     `Settled decisions — do not reopen` section;
   - do not create a completed-work archive or release-history substitute.
5. Update traceability. Completed work requires implementation evidence;
   verified work also requires verification evidence. External gates remain
   explicit when outstanding.
6. Validate that links resolve, no durable fact exists only in a deletion
   candidate, and no living documents contradict each other.
7. Delete an obsolete plan, finding, or stray document only after steps 1–6
   prove it contains no unique durable content or unresolved work.
8. Report moved content, removed completed entries, preserved open/settled
   items, deleted artifacts, and remaining blockers.

## Security stop condition

Do not prune a security artifact until every threat, mitigation, assumption,
control, and accepted residual risk has a stable living ID and traceability
link. Unverified mitigation claims remain blocked or implemented—not verified.

## Quick decisions

| Situation | Action |
|---|---|
| Completed `backlog` issue with evidence | Update traceability, then close it |
| Completed item without evidence | Reconstruct evidence or report blocked |
| Old plan contains open work | File it as a `backlog` issue before deletion |
| Old plan contains exact behavior | Promote it to a specification |
| Settled decision on a module page | Preserve it unless superseded with evidence |
| Duplicate current prose | Select one owner and replace other copies with links |

## Red flags

- “Git history is enough” before durable intent is promoted.
- Moving completed items to an archive instead of removing them.
- Treating a checked plan box as implementation or verification evidence.
- Deleting a plan while it remains the only threat, decision, or open-work record.
