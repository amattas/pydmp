# Contributing

This repository is managed by [Aviato](https://github.com/amattas/aviato)
conventions; CI, releases, and protections are automated.

- **Commits follow [Conventional Commits](https://www.conventionalcommits.org/)**
  (`feat:`, `fix:`, `chore:`, …; mark breaking changes with `!` or a
  `BREAKING CHANGE:` footer). Release versions are derived from them.
- **Changes land via pull request** into the default branch. The verify gates
  (lint, format, type-check, tests, security baseline) must be green and the
  branch up to date before merge.
- **Releases are tag-only and automated.** Do not hand-edit version files or push
  release tags — merging the automated `chore(release): X.Y.Z` PR cuts the
  release and runs the deploys in the same run.
- Files carrying an `aviato:managed` marker are re-rendered by automation; edit
  the corresponding Aviato template instead of the file itself.
