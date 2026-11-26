# Stable release acceptance

## 1.0.0 preparation — not yet approved or published

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
| Natural renewal specifically in RC.2 | Pending |
| Anonymous registry pull | Not independently confirmed |
| Host startup and basic performance | Passed short initial trial; not long-term testing |

The supervised performance trial measured 199 ms MCP startup (excluding
initial authentication), 2.751 s for four inventory queries, 57.73 MiB
cgroup memory peak, 7.20% of one CPU core during queries, and 2.28% of one
core over ten seconds idle. The latter exceeds the indicative 1% target;
on-demand execution avoids persistent idle work. Measurements include the
test client and server, not power draw. Keep the existing 384 MiB limit.

## Remaining approval gates

- [ ] Confirm natural renewal in RC.2 (do not edit tokenDate or force login).
  Verify newer tokenDate, successful read, preserved permissions and
  safe session reuse; record only sanitized results.
- [ ] Verify anonymous pull of the reviewed RC.2 digest.
- [ ] Maintainer explicitly accepts supervised local inventory scope,
  unavailable live device state, short-duration performance evidence,
  unofficial API risk, and remaining unfixed high-severity findings.
- [ ] Record completed evidence and update stable-acceptance.json:
  approvedVersion exactly matches package.json, all three booleans true.
  Review and merge through the normal PR process. Do not mark checks true
  before evidence and approval exist.

Stable publication uses the existing manual workflow with both explicit
approval inputs and the reviewed acceptance record. The workflow verifies
the record, not the actual remote account or host. CI must remain secret-free.
Build and validate a fresh image with embedded 1.0.0; never retag RC.2.
Record the resulting digest, then repeat host smoke and regression checks
on the actual stable image. Keep RC.2 for rollback.

Stable means a supervised read-only inventory application, not a guarantee
of all upstream endpoints, zero vulnerabilities, verified long-term
availability, or safe autonomous agent access. Outbound restrictions and
a reviewed restricted gateway remain prerequisites for untrusted agent access.
