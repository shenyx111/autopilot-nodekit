# Security

Autopilot NodeKit is local automation software. Treat it as a workflow control tool, not as a security boundary.

Do not put API keys, credentials, private datasets, model weights, Slurm outputs, real run logs, or local database files in public issues, pull requests, or commits.

For sensitive reports, use GitHub's private vulnerability reporting or private security advisories if available. If you open a public issue, remove secrets and share only the smallest reproduction needed.

For normal bugs, include:

- what command or workflow you ran;
- what you expected to happen;
- what happened instead;
- your OS and Python version;
- redacted logs or a minimal sample project.
