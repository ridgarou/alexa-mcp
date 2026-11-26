# Changelog

All notable changes in this hardened fork of Alexa MCP are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Dates use ISO 8601. The upstream application version and the fork's
container release versions are tracked separately.

## [Unreleased]

Initial hardening work, targeting candidate `0.7.0-hardened.1-rc.1`.
No candidate image or stable release has been published yet.

### Added

- Multi-stage Dockerfile with a minimal Debian 13 (Trixie) runtime, Node.js
  22 and a non-root UID/GID 1000; no npm, Yarn or Corepack in the runtime.
- Docker Compose configuration for on-demand stdio MCP execution, with
  write tools disabled, no published ports, read-only root filesystem,
  dropped Linux capabilities, resource limits and isolated bridge network.
- Separate authentication override exposing the temporary proxy only on
  host loopback for use through an SSH tunnel.
- Non-secret locale configuration example and restricted Docker build context.
- Offline MCP tests checking the exact inventory of 15 read tools, argument
  validation and missing credentials.
- Synthetic tests for atomic credential persistence, invalid JSON, file
  permissions and symlink handling, plus noninteractive authentication tests.
- Static read-only audit of the 15 tools, documenting read-only POST queries
  and the limitations of application-level access controls.
- Security and deployment documentation in [docs/SECURITY.md](docs/SECURITY.md),
  [docs/READ_ONLY_AUDIT.md](docs/READ_ONLY_AUDIT.md) and
  [docs/GHCR.md](docs/GHCR.md).
- Dependency migration helper; weekly Dependabot configuration targeting
  develop, limited to one open version-update PR per ecosystem.
- Shared CI validation and explicitly approved manual GHCR candidate
  publication from main, using a single linux/amd64 standard runner.
  Publication uses the tested image, unique versioned tags and digest
  reporting, without a latest tag or automatic deployment.
- This changelog for tracking future changes and releases.

### Changed

- Pin MCP SDK to 1.32.2, alexa-remote2 to 8.1.1 and Zod to 4.6.7.
- Pin alexa-cookie2 to 5.0.6, its cookie dependency to 0.7.2 and proxy-addr
  to 2.0.8 using npm overrides; commit the audited lockfile.
- Use npm ci with install scripts disabled for reproducible dependency
  installation instead of regenerating the lockfile during ordinary CI.
- Pin Docker base images by digest and apply available Debian security
  updates at build time.
- Consolidate automatic CI into one validation workflow; make the Node
  compatibility matrix manual, cancel superseded runs and retain Trivy
  reports for seven days.
- Pin external actions used by the main validation and publication workflows
  by commit SHA.
- Bound live device-state queries to 100 identifiers and validate and encode
  list IDs before URL interpolation.

### Fixed

- Honor ALEXA_MCP_PROXY_LANGUAGE and derive the proxy locale from the
  configured acceptance language when no override is supplied.
- Correct the Zod 4 record schema by specifying the string key type.
- Apply the exact proxy CSP compatibility patch from
  [upstream alexa-cookie PR #223](https://github.com/Apollon77/alexa-cookie/pull/223)
  to support the local HTTP login proxy.
- Make credential replacement atomic and recreate the file with restrictive
  permissions on each successful save.
- Reject malformed, empty or non-object stored registration data and
  prevent following credential symlinks on Linux.
- Correct the Trivy archive read-permission error without mounting the
  Docker socket or adding capabilities.

### Security

- Suppress sensitive authentication and refresh errors, dependency logging
  during initialization and device names in the authentication smoke test.
- Default proxy binding to loopback; block automatic generation of new
  sessions in noninteractive MCP mode when credentials are invalid or
  renewal fails.
- Keep explicit authentication available without passing real Amazon
  credentials to GitHub Actions.
- Exclude local credentials and environment files from Git and Docker
  context; preserve root-owned application files in the runtime.
- Audit npm dependencies and registry signatures/attestations; scan the
  runtime image with digest-pinned Trivy. Block critical and fixable high
  severity findings rather than suppressing them.
- Correct the previously reported fixable libzstd1 vulnerability through
  Debian security updates. The last successful validation reported no npm
  vulnerabilities, no critical or fixable high findings and 52 high findings
  without available fixes (13 unique advisories). This is a dated scan
  result, not a guarantee of security.
- No agent receives Docker socket access or credentials by design of the
  proposed deployment. Outbound network enforcement is still pending.

### Validation and release status

- Upstream starting point: snordquist/alexa-mcp at
  [a369d5f](https://github.com/snordquist/alexa-mcp/commit/a369d5f86858d8d43d4a982bedc5bffdaacccf0c),
  application version 0.7.0.
- Last successful validation before the shared CI refactor:
  [run 45764533808](https://github.com/ridgarou/alexa-mcp/actions/runs/45764533808),
  2026-11-26, commit 610a737: 18 unit tests passed and the 15-tool MCP
  inventory passed on the host and in Docker.
- The subsequent [run 45764958502](https://github.com/ridgarou/alexa-mcp/actions/runs/45764958502)
  stopped at npm provenance verification: eventsource-parser@3.1.0
  reported an invalid attestation. The security gate remains enabled;
  the shared workflow requires a successful revalidation before integration
  or publication. The failure is not evidence by itself of package tampering.
- Pending: real Amazon authentication/refresh testing, egress restrictions,
  GHCR publication verification, host deployment, Codex integration and
  JSON/CSV export. These are not completed features.

## Upstream baseline

This fork starts from upstream Alexa MCP 0.7.0, commit
`a369d5f86858d8d43d4a982bedc5bffdaacccf0c`. Earlier upstream history is
maintained in the [original repository](https://github.com/snordquist/alexa-mcp).
The original MIT license and attribution are retained.

## Maintaining this file

- Update Unreleased in the same PR as any notable functional, security,
  dependency, configuration or operational change.
- Use Added, Changed, Deprecated, Removed, Fixed and Security as needed.
  Describe user-visible behavior and meaningful technical changes, not every
  individual commit or internal iteration.
- Clearly distinguish implemented changes from validated or pending work.
  Include relevant advisory identifiers and migration notes when applicable.
- When a release candidate or stable version is actually published, move
  its changes into a versioned section with the release date and link to the
  corresponding tag or release. Keep an empty Unreleased section at the top.
- Do not record credentials, private host configuration or personal data.

[Unreleased]: https://github.com/ridgarou/alexa-mcp/compare/a369d5f86858d8d43d4a982bedc5bffdaacccf0c...feature/security-hardening
