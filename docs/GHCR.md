# GHCR release publication

## Published candidates

### 1.0.0-rc.2 (current candidate)

- Published 2026-11-26, source commit `c61c23a`.
- [Successful publication workflow](https://github.com/ridgarou/alexa-mcp/actions/runs/45788085719).
- Tag: `ghcr.io/ridgarou/alexa-mcp:1.0.0-rc.2`.
- Image: `ghcr.io/ridgarou/alexa-mcp@sha256:a023d51612ab00a579e3fb2e7d2c9c4568d2131bf9912f5a3a06c12d1836a810`.
- All offline validation and the registry push passed, including authenticated manifest inspection.
- Host image identity, offline checks and 14/15 basic live checks passed. The state query returned a controlled timeout and a subsequent inventory call passed. Anonymous pull, natural renewal in RC.2 and successful state retrieval remain unverified.

### 1.0.0-rc.1 (previous candidate)

- Published 2026-11-26, source commit `3906b98`.
- [Successful publication workflow](https://github.com/ridgarou/alexa-mcp/actions/runs/45770005405).
- Tag: `ghcr.io/ridgarou/alexa-mcp:1.0.0-rc.1`.
- Image: `ghcr.io/ridgarou/alexa-mcp@sha256:bfb28bc6e411df717d45c2f1f595cec30e7b0b41ff71ef909128b1a7b7e7d80d`.
- All validation and the registry push passed, including authenticated manifest inspection.
- Image inspection and host offline tests passed. Stored-session reuse and 14/15 read tools passed basic live checks; device-state throttling led to RC.2. Anonymous pull was not independently confirmed; real renewal remains pending.

### Historical candidate

- `0.7.0-hardened.1-rc.1` — 2026-11-26, source commit `360ad51`.
- [Successful publication workflow](https://github.com/ridgarou/alexa-mcp/actions/runs/45766872771).
- Tag: `0.7.0-hardened.1-rc.1-360ad516ead8-45766872771-1`.
- Image: `ghcr.io/ridgarou/alexa-mcp@sha256:3d2c5a935081324d58a9a63c51622a196a6ec6cdfeb7e7320d222a0cf061f3f5`.
- Registry push and authenticated inspection passed. The maintainer confirmed public package visibility;
  anonymous access still requires verification.

The manual workflow supports release candidates and stable versions. Stable publication requires reviewed live acceptance and explicit approval; current published RC.2 is not stable.
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
the immutable registry digest. Use the next RC number for a new build.
Stable promotion requires the separate acceptance approval described above
and a fresh build with matching embedded version. No automatic promotion.

## First publication and visibility

A new GHCR package may be private initially even if the repository is public.
Review the package's settings after the first push, associate it with this
repository if necessary and change visibility to public only when intended.
Verify anonymous access before deploying. Container registry storage and
bandwidth are currently free according to GitHub's billing documentation;
review the policy before publishing future versions. Public packages can be
pulled without a PAT.

## Deployment (later)

Use the exact digest from the successful workflow summary in the local .env:

    ALEXA_MCP_IMAGE=ghcr.io/ridgarou/alexa-mcp@sha256:<reviewed-digest>

Do not use latest or a mutable tag as the deployment identity. Keep the
previous deployed digest for rollback. Validate with the actual host,
credentials, refresh behavior and egress controls before treating this
candidate as stable. No Watchtower update or automatic deployment is enabled.

Keep only useful published candidates and releases. Remove obsolete GHCR
versions manually after verifying that neither the current deployment nor
the rollback configuration uses their digests. Do not delete all untagged
manifests indiscriminately. The CI artifact is only a Trivy report, retained
for seven days; the image is not stored as an Actions artifact.
