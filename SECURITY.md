# Security Policy

## Supported code

Security fixes target the current `main` branch.

## Report privately

Report privately through **Report a vulnerability** in this repository's
Security tab. Ordinary GitHub issues are public.

Include the affected commit, impact, and a minimal synthetic reproduction.
Do not send active credentials or real customer records. For exposed secrets,
revoke them through the owning service and describe the affected credential
type without sending its value. The maintainer will review the report and
coordinate a fix, mitigation, and any public disclosure with the reporter.

## Contributor responsibilities

- Keep credentials in local environment variables or a deployment secret store.
- Use synthetic examples in tests, issues, screenshots, and logs.
- Review dependencies and provenance before running downloaded code or artifacts.
- Keep sensitive reports out of public issue templates and pull request bodies.
- See [CONTRIBUTING.md](CONTRIBUTING.md) for project-specific validation.
