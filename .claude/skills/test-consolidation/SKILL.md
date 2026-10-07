---
name: test-consolidation
description: Use when a project's test suite has accumulated redundant or near-duplicate tests, when the suite has grown slow or repetitive, when many tests share copy-pasted setup, or when the user asks to consolidate, dedupe, prune, or clean up tests.
---

# Test Consolidation

## Overview

Evaluate an existing test suite for redundancy and consolidate it without losing behavioral coverage. The goal is fewer, stronger tests: every surviving test asserts a distinct behavior, and the suite's failure-detection power is unchanged or better.

**Core principle: consolidation must never reduce what the suite can catch — only how much code it takes to catch it.**

## When NOT to use

- Suite is small and already tight — don't churn it for cosmetics.
- Tests are failing — fix the suite first; never consolidate a red suite.
- "Duplicates" are actually distinct behaviors that share wording (e.g., same endpoint, different auth states). When in doubt, keep both.

## Process

1. **Baseline.** Run the full suite; record exact pass count and runtime. Record coverage if tooling exists (`pytest --cov`, `swift test --enable-code-coverage`, `nyc`/`c8`). All consolidation is judged against this baseline.
2. **Inventory.** Map the suite: files, test counts, shared fixtures/helpers. For large suites, delegate the scan to subagents per module and have each return a table of `test → code path exercised → distinct assertion`.
3. **Find consolidation candidates.** Parameterization is the first-choice move — check whether the project's framework supports it natively before reaching for anything else (`pytest.mark.parametrize`, Swift Testing `@Test(arguments:)`, Jest/Vitest `test.each`, Go table-driven tests, JUnit `@ParameterizedTest`; XCTest lacks native support — loop over a case table inside one test). Flag:
   - Same code path, different literals → one parameterized test.
   - Copy-pasted arrange/act blocks with different asserts → merge into one test or extract shared fixtures/builders.
   - Subsumed tests: a test that can only fail when another test also fails → fold or delete.
   - Over-mocked tests asserting mock wiring rather than behavior → replace with one behavioral test.
   - Redundant pyramid layers: an e2e test re-proving what a unit test already proves, with no integration value added.
4. **Consolidate in small batches.** One module or duplication cluster at a time. For each batch: make the change, run the affected tests, then the full suite.
5. **Verify no coverage loss.** Full suite green; coverage equal or better than baseline. If a deleted test covered a line/branch nothing else covers, it wasn't redundant — restore it or extend the surviving test to cover it.
6. **Report.** Before/after test counts, runtime, coverage delta, and a list of merged/deleted tests with one-line justifications. Commit per batch.

## Quick reference

| Smell | Consolidation move |
|---|---|
| N tests differing only in input/expected values | One parameterized test |
| Repeated setup blocks | Shared fixture / factory / builder |
| Test fails only when another fails | Delete or fold into the stronger test |
| Asserts mock call counts, not outcomes | Rewrite as one behavior assertion |
| e2e duplicating a unit assertion | Keep the unit test; keep e2e only for the integration seam |
| Vague names (`test_works_2`) hiding duplicates | Rename by behavior first — duplicates become visible |

## Hard rules

- Never delete a test because it's inconvenient, slow, or flaky — slow/flaky tests get fixed or quarantined explicitly, not "consolidated" away.
- A merged test must preserve every distinct assertion from its sources.
- Deleting or weakening tests is a destructive action: present one candidate list for the whole run — every deletion, merge that reduces test count, and assertion removal, each with a one-line rationale — and get approval once before executing. Pure additive changes (extracting fixtures, renaming) need no approval.
- Hard rules beat deadlines. If a runtime or count target can't be met without violating a rule (e.g., deleting a flaky test with unique coverage), report that the target is unreachable by consolidation alone and what it would actually take — don't quietly bend the rule.
- Mutation testing (`mutmut`, Stryker, `muter`) is the strongest redundancy check where available; coverage parity is the minimum bar.

## Common mistakes

- **Mega-tests.** Merging unrelated behaviors into one test destroys failure locality. Parameterize variants of *one* behavior; never fuse different behaviors.
- **Trusting names over bodies.** Two tests with similar names may cover different branches; read the bodies and the code path before merging.
- **Coverage-only verification.** Coverage parity misses lost *assertions* (same lines executed, weaker checks). Diff the assertion set, not just the line coverage.
- **Consolidating during feature work.** Do it as its own change with its own commits, never mixed into a feature diff.
