# Maintainer guide

## Branch protection

As checked on September 4, 2026, `main` was unprotected and the repository had
no rulesets. This document recommends settings; it does not enable them.

After the relevant checks exist and pass, configure a rule for `main`:

1. Require pull requests and resolution of review conversations.
2. Require validation against the latest base before merge. Use a merge queue
   only after workflows support its events.
3. Block force pushes and deletion of `main`.
4. Require one independent approval when another maintainer is available.
   A sole maintainer cannot approve their own PR; use an explicit documented
   exception or recruit a reviewer rather than creating an impossible gate.
5. Keep any emergency bypass narrow and document its use in the affected PR.
6. Prefer squash merges for focused changes. Delete merged topic branches only
   after confirming they contain no independent work.

Current check inventory: `test` from the `ci` workflow. It runs pytest and offline replay evaluations. It does not currently enforce lint, static types, coverage, security scanning, or wheel usability.

Check names can change. Select them from a recent run in GitHub, then confirm
that a failing check prevents merging. Do not advertise a coverage or security
gate until it is enforced. External publishing should depend on validation.

## Change and release review

Use the commands in [CONTRIBUTING.md](../CONTRIBUTING.md). Review the final diff,
including generated output and licenses. Keep related tests and documentation
in the same change. Do not rewrite published history to tidy the changelog.

For a versioned package, use semantic versioning, reconcile the package version
with the changelog, and test the built distribution outside its checkout before
tagging. A successful wheel build alone is not a runtime check. For a website
or profile, record the deployed commit and use dated changelog entries; a
package release workflow is not necessary.

## Remaining work

TODO: complete the scoped acceptance criteria in the [engineering follow-up](https://github.com/marinasofia/statement-agent/issues/8).
This issue is the implementation backlog, not a claim that its checks exist.
Handle vulnerability details through [SECURITY.md](../SECURITY.md).
