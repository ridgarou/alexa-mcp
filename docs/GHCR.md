# GHCR candidate publication

This workflow distributes a release candidate, not a production-ready image.
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

On GitHub, open Actions > Publish validated candidate (manual) > Run workflow.
Select main, enter a candidate version such as 0.7.0-hardened.1-rc.1,
and explicitly enable confirm_publish. This workflow cannot publish from
a feature branch or a pull request.

The single standard amd64 runner executes the same local composite validation
as CI. It audits npm, builds the image, verifies the read-only MCP tool inventory
and scans the runtime with Trivy. Critical findings and fixable high findings
prevent publication. The validated local image is then pushed without rebuilding.
Only the publishing job receives packages:write and the temporary GitHub token
is passed to docker login over stdin only at the final step. No deployment occurs.

The tag includes the candidate version, commit prefix, workflow run ID and
attempt. No latest tag is created. The workflow summary shows the immutable
registry digest. Repeated runs create new tags; do not rerun unnecessarily.

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
