# Stable release acceptance

## 1.0.0 — published; basic host regression passed

Candidate: 1.0.0-rc.2, source commit
`c61c23a4faa6b3508e28f97cb1a0f33a4622e7b9`, GHCR digest
`sha256:a023d51612ab00a579e3fb2e7d2c9c4568d2131bf9912f5a3a06c12d1836a810`.
Evidence below is maintainer-reported supervised host testing, not CI or
an independent network trace. No private inventory or credentials are recorded.

| Check | Result |
|---|---|
| Image identity and local offline MCP checks | Passed |
| RC.2 stored-session reuse | Passed |
| Fourteen distinct read tools | Basic live checks passed |
| Device-state query | Controlled STATE_TIMEOUT at 25.014 s; MCP isError true |
| Subsequent device inventory call | Passed in 168 ms |
| Real state retrieval | Not verified; RC.1 observed upstream throttling |
| Credential persistence and permissions | File replacement observed; mode 0600 and expected owner preserved |
| Natural renewal | RC.1 updated access token and cookies, retained refresh token; RC.2 reused session |
| Natural renewal specifically in RC.2 | Passed, maintainer-reported 2026-11-27; successful inventory in 3525 ms, exit 0 |
| Anonymous registry pull | Passed, confirmed 2026-11-26 and repeated 2026-11-27 using temporary empty Docker client configuration; digest verified, layers cached |
| Host startup and basic performance | Passed short initial trial; not long-term testing |

The supervised performance trial measured 199 ms MCP startup (excluding
initial authentication), 2.751 s for four inventory queries, 57.73 MiB
cgroup memory peak, 7.20% of one CPU core during queries, and 2.28% of one
core over ten seconds idle. The latter exceeds the indicative 1% target;
on-demand execution avoids persistent idle work. Measurements include the
test client and server, not power draw. Keep the existing 384 MiB limit.

## Additional supervised evidence — 2026-11-27

- RC.2 ran using the immutable digest above. The maintainer reported
  `alexa_list_devices` PASS in 3525 ms, process exit 0, and a newer
  tokenDate (advance of approximately 33 h 43 min). The credential file
  retained mode 0600 and UID:GID 1000:1000. No forced authentication,
  manual credential changes, secret disclosure or renewal interval
  modifications were reported. Exact session timestamps and private host
  identity are intentionally omitted.
- Existing RC.2 reuse was verified in the prior supervised regression.
  The renewal check establishes successful inventory during the renewal
  session; a separate post-renewal restart was not reported.
- The anonymous pull used a temporary empty DOCKER_CONFIG and verified
  the reviewed digest. Layers were already in the local cache. This
  confirms the maintainer-reported anonymous pull, not a cold-cache
  end-to-end layer transfer. The existing acceptance criteria do not
  require removing cached layers or using a fresh daemon. A cold pull on
  a clean disposable environment is recommended for the published stable
  digest, without deleting local rollback images.

## Acceptance and remaining release gates

- [x] Natural RC.2 renewal, successful read and preserved permissions confirmed
  on 2026-11-27; prior stored-session reuse verified. No forced login.
- [x] Anonymous pull of the reviewed RC.2 digest confirmed by the maintainer.
- [x] Maintainer explicitly accepted the six documented limitations on 2026-11-26:
  supervised local read-only inventory scope,
  unavailable live device state, short-duration performance evidence,
  unofficial API risk, remaining unfixed high-severity findings, and no
  autonomous agent access before egress controls and a restricted gateway.
- [x] Record completed evidence and update stable-acceptance.json for 1.0.0.
  The maintainer's explicit residual-risk acceptance and reported checks
  satisfy the live acceptance gate; this record is not merge or publish consent.
- [x] Required CI passed; maintainer authorized PR #13 squash into develop and
  PR #15 conventional merge into main; exact reviewed tree and both parents verified.
- [x] Explicit manual approval, fresh build, scan, registry push and
  authenticated manifest verification completed on 2026-11-27.
- [x] Maintainer confirmed anonymous stable-digest pull, image identity,
  pre-session credential permission and concurrent-session checks, and offline MCP validation.
- [x] Supervised stable-image inventory and nine basic read-tool regression
  checks passed using existing credentials.
- [ ] Confirm post-test credential ownership/mode and temporary container cleanup.
- [ ] Observe natural renewal on 1.0.0 without forcing login or changing
  the renewal interval. Keep RC.2 for rollback. A clean-environment cold
  pull remains an additional recommended check.

Stable publication uses the existing manual workflow with both explicit
approval inputs and the reviewed acceptance record. The workflow verifies
the record, not the actual remote account or host. CI must remain secret-free.
A fresh image with embedded 1.0.0 was built and validated; RC.2 was not retagged.

## Published stable artifact — 2026-11-27

- Published 2026-11-27 (18:34 UTC), source commit [`1b45d5dd20d2543eeb89a6968d1b19128d38fdf5`](https://github.com/ridgarou/alexa-mcp/commit/1b45d5dd20d2543eeb89a6968d1b19128d38fdf5).
- [Manual publication workflow 46050387909](https://github.com/ridgarou/alexa-mcp/actions/runs/46050387909) passed.
- Tag: `ghcr.io/ridgarou/alexa-mcp:1.0.0`.
- Immutable image reference: `ghcr.io/ridgarou/alexa-mcp@sha256:52f989c09e95748e4c853c5db705a0ba6b3b642e7394078b68b979f7e7228862`.
- Linux amd64 child manifest: `sha256:171cebedd80558ee042d3f50e0328a3e595279c5665cc65dda011b4d3cf10602`.
- Fresh 1.0.0 build, 28 unit tests, both 15-tool offline MCP checks, zero npm vulnerabilities, 157 verified signatures and 18 verified attestations.
- Trivy: 52 unfixed high findings (13 distinct advisory IDs), zero critical and zero fixable findings. The current policy passed; this is not a vulnerability-free image.
- Registry push and authenticated manifest inspection passed. The maintainer subsequently confirmed anonymous stable-digest pull, image identity, offline MCP validation, stored-session reuse and nine basic live read-tool checks. Cold-cache transfer, post-test credential permissions and natural renewal on 1.0.0 have not yet been separately confirmed. See STABLE_ACCEPTANCE.md for scope.

## Supervised stable-image host regression

The maintainer confirmed the anonymous pull and identity checks, pre-session
credential permissions and absence of concurrent sessions; exact command
outputs for those preliminary checks were not supplied. The offline test
reported PASS for the exact 15-tool inventory, schemas, invalid arguments
and missing authentication. The stable live smoke reported embedded version
1.0.0, 15 registered tools, a successful nonempty device inventory in
1719 ms, and process exit 0. Existing credentials were reused.

A subsequent single-session regression reported the following sanitized
results (milliseconds per tool):

| Tool | Result | Duration (ms) |
|---|---|---:|
| alexa_list_devices | PASS | 1617 |
| alexa_list_routines | PASS | 199 |
| alexa_list_scenes | PASS | 606 |
| alexa_list_smarthome_devices | PASS | 1555 |
| alexa_list_groups | PASS | 106 |
| alexa_get_volumes | PASS | 112 |
| alexa_get_do_not_disturb | PASS | 140 |
| alexa_list_lists | PASS | 267 |
| alexa_audit_broken_references | PASS | 727 |

Nine passed, zero failed, STABLE_REGRESSION PASS, exit 0.
These are maintainer-reported basic successful response checks, not
exhaustive semantic validation, packet traces or a long-duration benchmark.
Six other registered tools were not called during this regression, including
the live device-state query, which was deliberately omitted to avoid
unnecessary upstream throttling. Prior RC.2 coverage is not attributed to
the new stable image. No private device counts, names, identifiers or raw
credential data are recorded.

Confirm post-test credential metadata and that the transient container has
been removed. Natural renewal specifically on 1.0.0 is not yet demonstrated;
observe it when normally due. Authentication code and dependency versions
are unchanged from RC.2, whose natural renewal passed. This pending
observation need not delay independent Egress Proxy development, but must
not be marked passed. Keep the existing rollback configuration and image.

Stable means a supervised read-only inventory application, not a guarantee
of all upstream endpoints, zero vulnerabilities, verified long-term
availability, or safe autonomous agent access. Outbound restrictions and
a reviewed restricted gateway remain prerequisites for untrusted agent access.
