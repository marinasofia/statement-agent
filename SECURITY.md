# Security Policy

## Supported code

Security fixes target the current `main` branch. Older commits and forks do not
have a separate maintenance commitment. Repository availability is not a
production support or security certification.

## Report privately

Email the maintainer using the email address on the [portfolio contact page](https://marinasofia.github.io/#s06) with subject
`statement-agent security`. If GitHub's Security tab offers **Report a vulnerability**,
that private channel may also be used. Ordinary GitHub issues are public.

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
