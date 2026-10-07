# Contributing

- **Commits follow [Conventional Commits](https://www.conventionalcommits.org/)**
  (`feat:`, `fix:`, `chore:`, …; mark breaking changes with `!` or a
  `BREAKING CHANGE:` footer).
- **Changes land via pull request** into `main`. The CI gates (ruff lint and
  format, mypy strict, tests, build, CodeQL) must be green and the branch up to
  date before merge.
- **Releases are tag-driven.** Bump `[project].version` in `pyproject.toml`
  and merge it to `main`, then push a matching tag:

  ```bash
  git tag 1.2.3 && git push origin 1.2.3
  ```

  Pre-releases use `X.Y.Z-alphaN` / `X.Y.Z-betaN`. The release workflow
  verifies the tag is on `main` and matches the built version, publishes to
  PyPI (trusted publishing, gated by the `pypi` environment), creates the
  GitHub release, and then deploys the versioned docs.
