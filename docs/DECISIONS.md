# Technical decision log

This record captures the project's durable decisions, their rationale,
consequences and review conditions. Read [AGENTS.md](../AGENTS.md) for
operational instructions. Accepted means the decision is agreed; it does
not imply that every implementation or test is complete.

## ADR-001 — Independent fork and SemVer

**Date:** 2026-11-26 · **Status:** Accepted

The project originates from snordquist/alexa-mcp 0.7.0, commit
a369d5f86858d8d43d4a982bedc5bffdaacccf0c. Keep MIT attribution, but use an
independent release lifecycle. The maintainer approved dropping the
hardened suffix and starting at 1.0.0-rc.1. Subsequent candidates use rc.2,
rc.3, etc.; stable 1.0.0 follows live acceptance. Use patch versions for
compatible fixes, minor versions for compatible features and major
versions for incompatible changes.

package.json is the application version authority; lockfile root metadata,
MCP handshake, OCI label and GHCR release tag must agree. The npm package
is private to prevent accidental npm publication. Keep old release names
and digests as historical facts, not rewritten aliases. No latest tag.

**Rationale:** avoid coupling the fork's roadmap and version numbers to
upstream while preserving provenance and avoiding version drift.

**Consequence:** 1.0.0-rc.1 requires a validated new build. Merely retagging
an older binary does not update its embedded version. For a stable
release whose embedded version changes, build and validate again.
If promoting an existing digest without rebuilding is ever desired,
document the embedded-version difference and obtain explicit approval
rather than violating the consistency rule.

## ADR-002 — Branching, documentation and controlled integration

**Date:** 2026-11-26 · **Status:** Accepted

Use feature/fix/docs branches from develop, PRs into develop (squash),
then reviewed promotion to main (merge preserving ancestry). Check the
exact head and successful CI. After each promotion verify the resulting
commit has both expected parents and the reviewed tree. If a previous
merge lost ancestry, reconcile only after verifying both trees and use
a non-force update; do not rewrite history. PR #10 restored ancestry and
its final merge had both expected parents. No automatic merge or direct unreviewed
promotion. Group related changes to limit redundant CI. Maintain an English
README, CHANGELOG (Keep a Changelog with Unreleased), and technical docs.
Add or supersede decisions here when changing a project-wide rule.

**Rationale:** maintain an auditable history, independent development and
release boundaries, and consistent instructions for future agents.

## ADR-003 — GitHub Free and efficient CI/CD

**Date:** 2026-11-26 · **Status:** Accepted

The maintainer uses GitHub Free. Keep the public repository and public
GHCR distribution; standard hosted Ubuntu runners only. Do not incur
paid charges or enable paid services without explicit permission.
Verify billing conditions before changing the architecture.
Use one automatic shared validation action, manual compatibility checks,
cancel superseded runs, timeouts and seven-day retention of compact
Trivy reports. No image archives as Actions artifacts. Avoid building
for publication on every commit. Dependabot checks weekly (npm, Docker,
Actions), with at most one open version-update PR per ecosystem toward
develop; no unattended merge.

**Rationale:** keep cost and maintenance overhead low without weakening
security checks. Public package visibility was confirmed by the maintainer;
anonymous download of RC.2 was subsequently confirmed by the maintainer.
The 2026-11-27 check used an empty Docker client configuration with cached
layers; cold-cache transfer is not a required acceptance gate.

## ADR-004 — Release gate and immutable deployment identity

**Date:** 2026-11-26 · **Status:** Accepted; candidate publishing implemented,
stable promotion procedure prepared; publication pending.

Only publish with deliberate workflow_dispatch from main and explicit
confirmation. Use the exact tested linux/amd64 image from the validation
job; packages:write only where needed. Pin reviewed action and base-image
digests. Use the version as the GHCR tag, block existing tags, and record
the digest. Never treat a mutable tag as deployment identity. Retain the
previous image/digest and configuration for rollback. No automatic
deployment, no Watchtower updates and no unnecessary republishing.

Release gates include locked dependencies, npm audit and provenance,
unit/offline MCP tests, strict proxy patch, Docker build, user and
permissions checks, Compose validation and Trivy. Block critical and
fixable high findings; review unfixed highs rather than suppressing them.
No real account data in CI. Investigate failed attestations; never disable
the check merely to continue. The earlier eventsource-parser attestation
failure did not recur in later runs; its root cause is unknown.

**Rationale:** publish only reviewed artifacts and preserve recoverability.
A successful registry push does not prove anonymous access or live
Amazon integration. Base digests plus npm locks improve repeatability;
Debian security updates and changing scanner databases mean builds are
not guaranteed bit-for-bit reproducible.

## ADR-005 — Docker-first minimal runtime and low resource usage

**Date:** 2026-11-26 · **Status:** Accepted and implemented in candidate.

Target a headless Linux amd64 home server with Docker Compose v2.
Build with Node 22; run on Debian 13 with only the runtime and production
dependencies, no npm/Yarn/Corepack. Use UID/GID 1000, root-owned code,
read-only root filesystem, no privileges, cap_drop ALL, bounded memory
and processes, a dedicated bridge and a narrow writable auth mount.
Use on-demand stdio rather than an always-on HTTP server. Preserve
service name AlexaMCP and keep explicit auth configuration separate.

**Rationale:** small attack surface, low idle consumption, portability and
limited effects on other home-server workloads.

**Review:** additional services or changes to resource limits require
a concrete need and measurement where practical. The bridge alone does
not enforce outbound restrictions.

## ADR-006 — Read-only auditing and agent boundaries

**Date:** 2026-11-26 · **Status:** Accepted; static and offline validation
complete for the original 15 read tools; supervised basic live checks
passed for 14, with controlled device-state timeout accepted.

The immediate goal is inventory before cleanup: Alexa devices, routines,
groups, scenes, broken references and source clues. Existing upstream
write tools are retained in code but not registered in the supplied
read-only Compose configuration. Do not execute routines, delete devices,
modify groups or change Amazon account state at an agent's discretion.
Any write workflow requires a separate authorized design. Read-only
application controls do not limit Amazon credentials; read queries can
use POST and authentication/renewal may change account metadata.

Codex or any other agent must not receive a Docker socket, host-level
control, auth file access or unrelated application access. An isolated
agent needs a separately reviewed narrow gateway; the host-side trusted
stdio launcher is not a secure gateway for untrusted agents.
Treat returned data as private and untrusted, not as executable prompts.

**Rationale:** prevent autonomous changes to the home environment and
avoid lateral movement or disclosure. Source/manufacturer data is not a
guaranteed complete inventory of installed Alexa skills.

## ADR-007 — Private authentication and persistent credentials

**Date:** 2026-11-26 · **Status:** Accepted; implementation tested offline,
natural RC.2 renewal verified by the maintainer on 2026-11-27;
real expired-session fallback testing remains pending.

Credentials stay only on the deployment host, outside the repository and
Docker build context. Default private auth directory mode 0700 and
credential file mode 0600; correct ownership for the container UID/GID.
Reuse a valid session; no forced login during upgrades. Atomic file
replacement, reject malformed data and symlink reads, suppress sensitive
errors and raw logs. Use one credential writer at a time; atomic writes
are not interprocess locking or full power-loss durability.

Normal MCP does not open a login port. Only explicit CLI authentication
uses a temporary proxy bound on host loopback, reached via SSH tunnel for
remote hosts. Do not expose via LAN, Internet or reverse proxy. Close the
session when done. If renewal fails, block fallback proxy generation;
require explicit reauthentication. Preserve valid credentials and plan
revocation safely. Deleting a file alone does not revoke a session.

**Rationale:** protect long-lived account credentials and prevent
unintended network exposure. The unofficial proxy handles sensitive
traffic; its CSP compatibility patch relaxes one directive for local
HTTP only and must remain narrowly scoped and version-reviewed.

## ADR-008 — Dependency maintenance and vulnerability policy

**Date:** 2026-11-26 · **Status:** Accepted.

Pin the reviewed MCP SDK, alexa-remote2, Zod and dependency overrides in
the committed lockfile. Use npm ci --ignore-scripts, review integrity
and provenance, and strictly apply the proxy patch to the reviewed
alexa-cookie2 version. Re-audit upstream auth fallback, read methods,
patch compatibility and tool schemas on updates. Never use forced
audit fixes or skip checks merely to pass CI.

Review remaining vulnerabilities individually as needed; keep evidence
and do not imply zero risk from a green gate. The last published legacy
candidate's audit reported 0 npm vulnerabilities, 0 critical image
findings, 0 fixable highs and 52 unfixed high findings (13 distinct
advisory IDs). This is historical evidence, not a permanent guarantee.
New builds require a new scan.

## ADR-009 — Local acceptance and future development sequence

**Date:** 2026-11-26 · **Status:** Accepted plan; not all tasks implemented.

1. Independent versioning validation and promotion completed (PR #6).
2. Manual publication of 1.0.0-rc.1 and 1.0.0-rc.2 completed; see
   [GHCR.md](GHCR.md) and [CHANGELOG.md](../CHANGELOG.md) for evidence.
   RC.1 passed 14/15 basic live checks and exposed a device-state error
   handling defect. RC.2 live regression verified all other tools and controlled state
   timeout. Natural RC.2 renewal and anonymous pull confirmed on 2026-11-27.
3. Anonymous pull, image identity, independent candidate configuration,
   rollback preservation and stored-session reuse completed for RC.2.
4. Supervised RC.2 read-only inventory, controlled error handling, reuse
   and natural renewal verified; sanitized evidence in STABLE_ACCEPTANCE.md.
   Explicit reauthentication and live expired-session failure tests remain
   separate checks when needed.
5. Maintainer accepted residual risks on 2026-11-26 and reported completed
   live acceptance on 2026-11-27. Stable review, authorized promotion,
   publication and post-publication validation remain pending.
6. Implement and verify outbound network restrictions with narrowly scoped
   Amazon destinations and request semantics. Do not present the bridge
   as an allowlist; do not blindly block all POST requests.
7. Design a constrained Codex integration without granting the agent
   Docker access or credentials. Review permissions and threat model
   before any deployment.
8. Implement local JSON/CSV inventory export: on demand and optionally
   weekly, preserve last successful snapshot, keep history and distinguish
   unknown source/skill data from confirmed data. No credentials in
   exports. Store and restrict sensitive inventory locally.

The exporter, agent gateway and additional egress controls are distinct
features, not required for the first stable application version if its
live acceptance criteria are met and limitations are disclosed. Egress
restrictions and the restricted gateway must be reviewed before granting
an untrusted agent live account access. Any schedule is a future proposal,
not an active task or deployed service.

## ADR-010 — Bound live device-state requests and report errors explicitly

**Date:** 2026-11-26 · **Status:** Accepted; implementation published in RC.2;
controlled timeout and subsequent inventory verified live, state retrieval pending.

RC.1 live acceptance passed basic checks for 14 of 15 read tools. The
state endpoint returned a JSON message matching throttling patterns,
which the MCP handler incorrectly reported as success. The HTTP status
was not captured. The API remains unofficial; no guarantee of a
successful state response is possible.

For state queries, require nonempty deviceStates and an empty errors array,
otherwise return a sanitized MCP error with a stable code. Treat partial
results as errors rather than silently implying complete success. Keep
valid response shape unchanged. Use a 25-second application response
deadline after authentication, explicit 15-second upstream timeout and
60-second process-local cooldown on throttling or timeout. Permit one
outstanding state query per MCP process; retain the slot until the callback
settles, even after the deadline. Do not add retries or reset processes to
evade Amazon's limits. Other read tools are not gated by this state-query
guard. A never-settling callback can leave state queries blocked for the
session; close it normally after use. No cross-process rate limiter or
upstream cancellation is implemented.

**Rationale:** distinguish unavailable state from successful inventory,
avoid amplifying throttling, and bound waiting without exposing upstream
messages or weakening existing authentication/security controls.

**Acceptance:** synthetic regression checks; then a limited real query
after a normal quiet interval, confirming either valid state or an
explicit error within the response deadline. Record actual successful
state retrieval separately. No retries to bypass a rate limit.

## ADR-011 — Stable publication acceptance gate

**Date:** 2026-11-26 · **Status:** Accepted; live acceptance recorded, review and publication pending.

Reuse the single manual GHCR publication workflow for RC and stable
SemVer, with the same build, security and immutable-tag gates. Stable
versions additionally require explicit workflow approval and a
version-specific reviewed acceptance record in docs/stable-acceptance.json.
All acceptance fields start false; never mark them true without evidence
and maintainer approval. See [STABLE_ACCEPTANCE.md](STABLE_ACCEPTANCE.md).
Do not publish stable before natural RC.2 renewal, anonymous pull and
acceptance of the documented residual risks. This is a human evidence
gate, not a CI live account test. No secrets or paid services are added.
The version-specific record must be updated for future stable releases.

**2026-11-27 acceptance clarification:** the current criteria require an
anonymous pull of the reviewed digest, not a forced cold-cache layer
transfer. The maintainer reported a successful pull with an empty
DOCKER_CONFIG and cached layers, and successful natural RC.2 renewal.
Record that scope without claiming a fresh transfer or independent live
verification. Recommend a cold-cache pull of the published stable digest
in a disposable environment. All acceptance fields for 1.0.0 are now
recorded; review and explicit merge/publication authorization remain
separate requirements.

## How to update this record

Use the next ADR number. Include date, status, context, decision, rationale,
consequences and validation/review conditions. Mark an obsolete ADR
Superseded by the new ADR, retaining history. Distinguish maintainer-approved
requirements, engineering choices, and unimplemented proposals. Never
include actual credentials, private host addresses, device inventories
or account data in this public repository.
