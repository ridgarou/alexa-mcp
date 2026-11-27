# GHCR release publication

## Published releases and candidates

### 1.0.0 (current stable)

- Published 2026-11-27 (18:34 UTC), source commit [`1b45d5dd20d2543eeb89a6968d1b19128d38fdf5`](https://github.com/ridgarou/alexa-mcp/commit/1b45d5dd20d2543eeb89a6968d1b19128d38fdf5).
- [Manual publication workflow 46050387909](https://github.com/ridgarou/alexa-mcp/actions/runs/46050387909) passed.
- Tag: `ghcr.io/ridgarou/alexa-mcp:1.0.0`.
- Immutable image reference: `ghcr.io/ridgarou/alexa-mcp@sha256:52f989c09e95748e4c853c5db705a0ba6b3b642e7394078b68b979f7e7228862`.
- Linux amd64 child manifest: `sha256:171cebedd80558ee042d3f50e0328a3e595279c5665cc65dda011b4d3cf10602`.
- Fresh 1.0.0 build, 28 unit tests, both 15-tool offline MCP checks, zero npm vulnerabilities, 157 verified signatures and 18 verified attestations.
- Trivy: 52 unfixed high findings (13 distinct advisory IDs), zero critical and zero fixable findings. The current policy passed; this is not a vulnerability-free image.
- Registry push and authenticated manifest inspection passed. The maintainer subsequently confirmed anonymous stable-digest pull, image identity, offline MCP validation, stored-session reuse and nine basic live read-tool checks. Cold-cache transfer, post-test credential permissions and natural renewal on 1.0.0 have not yet been separately confirmed. See STABLE_ACCEPTANCE.md for scope.

### 1.0.0-rc.2 (rollback candidate)

- Published 2026-11-26, source commit `c61c23a`.
- [Successful publication workflow](https://github.com/ridgarou/alexa-mcp/actions/runs/45788085719).
- Tag: `ghcr.io/ridgarou/alexa-mcp:1.0.0-rc.2`.
- Image: `ghcr.io/ridgarou/alexa-mcp@sha256:a023d51612ab00a579e3fb2e7d2c9c4568d2131bf9912f5a3a06c12d1836a810`.
- All offline validation and the registry push passed, including authenticated manifest inspection.
- Host image identity, offline checks and 14/15 basic live checks passed. The state query returned a controlled timeout and a subsequent inventory call passed. Anonymous pull and natural RC.2 renewal were confirmed by the maintainer on 2026-11-27; successful state retrieval remains unverified. See [STABLE_ACCEPTANCE.md](STABLE_ACCEPTANCE.md) for scope and cache limitations.

### 1.0.0-rc.1 (previous candidate)

- Published 2026-11-26, source commit `3906b98`.
- [Successful publication workflow](https://github.com/ridgarou/alexa-mcp/actions/runs/45770005405).
- Tag: `ghcr.io/ridgarou/alexa-mcp:1.0.0-rc.1`.
- Image: `ghcr.io/ridgarou/alexa-mcp@sha256:bfb28bc6e411df717d45c2f1f595cec30e7b0b41ff71ef909128b1a7b7e7d80d`.
- All validation and the registry push passed, including authenticated manifest inspection.
- Image inspection and host offline tests passed. Stored-session reuse and 14/15 read tools passed basic live checks; device-state throttling led to RC.2. At publication, anonymous pull and real renewal were not yet confirmed; see subsequent RC.2 acceptance evidence.

### Historical candidate

- `0.7.0-hardened.1-rc.1` — 2026-11-26, source commit `360ad51`.
- [Successful publication workflow](https://github.com/ridgarou/alexa-mcp/actions/runs/45766872771).
- Tag: `0.7.0-hardened.1-rc.1-360ad516ead8-45766872771-1`.
- Image: `ghcr.io/ridgarou/alexa-mcp@sha256:3d2c5a935081324d58a9a63c51622a196a6ec6cdfeb7e7320d222a0cf061f3f5`.
- Registry push and authenticated inspection passed. The maintainer confirmed public package visibility;
  anonymous access still requires verification.

The manual workflow supports release candidates and stable versions. Stable publication requires reviewed live acceptance and explicit approval; RC.2 remains a release candidate and rollback image; 1.0.0 has been published after the separate acceptance and approval gates.
There is no push, PR, schedule, release or tag trigger for publication.

## Before publication

- Review and merge the changes through develop into main after CI passes.
- Confirm that GitHub-hosted standard runners and Container registry remain
  free for this use; check your account's billing and budget settings.
- Confirm that public distribution of this fork is intended. The image must
  contain no real account data, host-specific credentials or inventories.
- Do not add an Amazon credential, PAT or deployment secret to GitHub.
- Review the remaining unfixed OS findings and limitations in SECURITY.md.

## Publish once, manually

On GitHub, open Actions > Publish validated image (manual) > Run workflow.
Select main, enter the exact package version, and explicitly enable confirm_publish.
For stable versions also enable confirm_stable_acceptance only after the
version-specific [acceptance record](STABLE_ACCEPTANCE.md) has been reviewed
and merged with all required checks approved. The workflow blocks stable
publication unless docs/stable-acceptance.json matches the requested version
and its three approval fields are true. This workflow cannot publish from
a feature branch or a pull request.

The single standard amd64 runner executes the same local composite validation
as CI. It audits npm, builds the image, verifies the read-only MCP tool inventory
and scans the runtime with Trivy. Critical findings and fixable high findings
prevent publication. The validated local image is then pushed without rebuilding.
Only the publishing job receives packages:write and the temporary GitHub token
is passed to docker login over stdin only at the final step. No deployment occurs.

New tags use the exact independent SemVer version (e.g. 1.0.0 or
1.1.0-rc.1). The workflow rejects an existing tag and checks the version
against package.json. No latest tag is created. The workflow summary shows
the immutable registry digest. Use a new SemVer version for any replacement
build of an already published version; use the next RC number for another
candidate in the same release series.
Stable promotion requires the separate acceptance approval described above
and a fresh build with matching embedded version. No automatic promotion.

## First publication and visibility

A new GHCR package may be private initially even if the repository is public.
Review the package's settings after the first push, associate it with this
repository if necessary and change visibility to public only when intended.
Verify anonymous access before deploying. A pull using a temporary empty
Docker client configuration with cached layers satisfies the current RC.2
acceptance criterion; it does not prove a fresh transfer of every layer.
For the actual published stable digest, a clean disposable environment is
recommended for an additional cold-cache pull; keep existing rollback
images. Container registry storage and
bandwidth are currently free according to GitHub's billing documentation;
review the policy before publishing future versions. Public packages can be
pulled without a PAT.

## Deployment and post-publication acceptance

Use the exact digest from the successful workflow summary in the local .env:

    ALEXA_MCP_IMAGE=ghcr.io/ridgarou/alexa-mcp@sha256:<reviewed-digest>

Do not use latest or a mutable tag as the deployment identity. Keep the
previous deployed digest for rollback. Repeat supervised host smoke and
regression checks on the actual stable digest. Natural RC.2 renewal is
candidate evidence, not proof of the new image's behavior. Egress controls
and a restricted gateway are separate prerequisites for untrusted agents. No Watchtower update or automatic deployment is enabled.

Keep only useful published candidates and releases. Remove obsolete GHCR
versions manually after verifying that neither the current deployment nor
the rollback configuration uses their digests. Do not delete all untagged
manifests indiscriminately. The CI artifact is only a Trivy report, retained
for seven days; the image is not stored as an Actions artifact.
