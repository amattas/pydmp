---
name: docs-structure
description: Use when creating, organizing, splitting, or reconciling project requirements, specifications, architecture, security documentation, findings, backlogs, traceability, or dated design artifacts.
---

# Project docs structure

Use one living home for each kind of project truth:

```text
docs/
├─ requirements/
│  ├─ README.md
│  ├─ traceability.md
│  ├─ core/
│  └─ modules/<module>/<topic>.md
├─ specifications/
│  ├─ README.md
│  ├─ core/
│  └─ modules/<module>/<topic>.md
├─ architecture/{overview.md,infrastructure.md,data-flow.md,data-schema.md,security.md}
├─ security/{threat-model.md,controls.md}
└─ superpowers/{specs,plans}/
```

Adapt module names and omit architecture files that do not apply.

## Ownership

| Location | Owns |
|---|---|
| `requirements/` | What must be true and why: stable IDs, scope, constraints, acceptance criteria |
| `specifications/` | Precise testable behavior: interfaces, schemas, workflows, state transitions, errors, compatibility |
| `architecture/` | Current components, boundaries, dependencies, deployment, and data flow |
| `security/` | Threats, assets, actors, trust boundaries, mitigations, controls, assumptions, residual risks |
| GitHub issues labeled `backlog` | Unresolved work — one issue per item, plus a severity label |
| module page `Settled decisions — do not reopen` section | Deliberate decisions future reviews must not reopen |
| `requirements/traceability.md` | Requirement/threat to specification, implementation, and verification evidence |
| `superpowers/` | Temporary dated design/execution artifacts, never the system of record |

Do not invent parallel names such as `contracts/`, a root `BACKLOG.md`, or a
completed-work archive. Put API contracts in specifications, security risks in
the threat model, and open work in GitHub issues labeled `backlog`.

## Rules

1. A module is one cohesive capability. Keep topic files small and
   single-purpose. Families become subdirectories under their module.
2. Open work lives in GitHub issues labeled `backlog`, never in docs files.
   Deliberate decisions reviews must not reopen live in a `## Settled
   decisions — do not reopen` section on the owning module page. Close
   issues when work completes; Git history and traceability preserve evidence.
3. Give requirements and threats stable IDs. Maintain the chain
   `THREAT-* -> SEC-* -> specification -> control/code -> verification` and
   the equivalent requirement-first chain for non-security work.
4. Before pruning a plan or stray document, promote every durable requirement,
   behavior, decision, threat, mitigation, assumption, accepted risk, and open
   item into its living owner; update traceability; verify links; then delete.
5. Put diagrams in Mermaid fenced blocks in Markdown. Do not commit diagram
   images or ASCII art. Keep code/config examples in ordinary fences.
6. When splitting a document cited by code, preserve section numbering
   verbatim, never split one numbered subsection, maintain the number-to-file
   index in `docs/requirements/README.md`, leave a pointer stub at the old path,
   and test that every citation resolves.

## Common mistakes

- Requirements containing request schemas or algorithms: move those details to specifications.
- Architecture used as a future-work list: file unresolved work as `backlog` issues.
- `SECURITY.md` as the only threat record: keep public reporting policy there and living analysis under `docs/security/`.
- Deleting dated plans because implementation landed: promote durable content and update traceability first.
