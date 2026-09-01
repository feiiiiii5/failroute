# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.8.x | Yes |
| < 0.8 | No |

## Reporting a vulnerability

failroute is a static analysis tool and does not execute scanned code, so the
attack surface is narrow but not empty. Relevant classes of issues include:

- Findings being silently dropped or corrupted in JSON/SARIF output (a
  detection tool that can be made to under-report is itself a security bug).
- Path traversal or resource exhaustion via crafted file trees (symlinks,
  deep nesting) when scanning untrusted checkouts.
- Configuration injection via a malicious `[tool.failroute]` table.

Please report privately via GitHub
[Security Advisories](https://github.com/feiiiiii5/failroute/security/advisories/new)
("Report a vulnerability"). Do not open a public issue for a security report.

We aim to acknowledge reports within 7 days and will credit reporters unless
asked otherwise.
