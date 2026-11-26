# Hardened fork — candidate status

This branch is not a production release. It is based on upstream commit
a369d5f86858d8d43d4a982bedc5bffdaacccf0c. Preserve upstream MIT notices.

## Build and review

Use the checked-in audited lockfile with Node 22. Do not regenerate it during
ordinary builds. Review dependency changes in a separate PR, and never use
npm audit fix --force or bypass peer dependency checks. Run:

```sh
npm ci --ignore-scripts
npm test
npm audit --include=dev
npm audit signatures
docker build -t local/alexa-mcp:hardened-candidate .
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true -i \
  local/alexa-mcp:hardened-candidate node --input-type=module \
  < tests/security/mcp-readonly.mjs
```

Scan the resulting runtime image with Trivy; review all HIGH/CRITICAL
findings, including Debian and the Node runtime. The default base images are digest-pinned; Debian security packages are
updated at build time, so this is not a bit-for-bit reproducible image. The runtime intentionally has no npm, Yarn or Corepack.
The builder still uses npm, so build-time auditing remains necessary.

## Local deployment

Keep credentials exclusively on the deployment host. Never commit or upload
tokens, cookies, private keys, logs, actual device inventories or private
network settings. The bind-mounted auth directory must be created in advance
and owned by UID/GID 1000 with mode 0700; credential files must be mode 0600.
Prefer a root-owned 0700 parent directory on a rootful Docker host.

Copy .env.example to .env and adjust only non-secret values. Ordinary MCP
runs on stdio, with no published port and write tools disabled:

```sh
docker compose -f compose.yml run --rm --no-deps -T AlexaMCP
```

Authentication is a separate, explicitly selected mode. Open an SSH tunnel
from the client to the Docker host, forwarding local 127.0.0.1:3456 to
127.0.0.1:3456 on the host. Only then run:

```sh
docker compose -f compose.yml -f compose.auth.yml run --rm --no-deps \
  --service-ports -T AlexaMCP sh -ec 'umask 077; test ! -e /app/.auth/alexa.json; test ! -L /app/.auth/alexa.json; node dist/auth-cli.js >/dev/null 2>&1; test -s /app/.auth/alexa.json; chmod 600 /app/.auth/alexa.json'
```

Open http://127.0.0.1:3456 in the client browser. Stop the container and close
the tunnel when done. Use a Docker release that correctly isolates loopback
published ports; verify from another LAN client. Do not expose this HTTP
login proxy through a reverse proxy or directly to the LAN. The proxy handles
sensitive login traffic; the dependency patch relaxes one CSP directive
for local HTTP compatibility. Do not treat it as a general security fix.

The authentication command refuses to overwrite an existing session. Stop
other MCP/auth processes before authentication or renewal testing. Atomic
replacement does not provide a multi-process lock or guarantee durability
across power loss. Do not force reauthentication while a valid session exists. Never share raw
auth logs. The normal server must not intentionally expose login ports.

## Outstanding work

- Review the static [read-only audit](READ_ONLY_AUDIT.md) and validate
  actual requests and returned data on the deployment host.
- Validate atomic credential replacement with a real token refresh and review
  other potentially sensitive errors in the runtime.
- Validate the noninteractive authentication guard against actual expired
  sessions on the deployment host; offline tests cover simulated failure.
- Enforce outbound network restrictions; a dedicated bridge alone is not
  an egress allowlist.
- Verify real Amazon access and token refresh on the host only.
- Validate manual GHCR candidate publication and deploy only by a reviewed
  digest after real integration checks.
- Do not give agents a Docker socket or access to credential files.

The read-only MCP setting is an application control, not an Amazon account
permission boundary. Offline tests do not prove absence of malicious code,
network exfiltration or changes made internally by authentication libraries.

## CI and GitHub Free

Automatic validation uses a standard Ubuntu runner with Node 22. The optional
compatibility matrix is manual; overlapping runs for the same ref are cancelled.
Trivy JSON reports are retained for seven days. Dependabot configuration limits
version-update PRs to one per ecosystem and checks weekly. It becomes active
when available on the default branch; base digests and the pinned dependency
patch still need review. No automatic deployment, automatic image publishing, paid runner or auto-merge
is enabled. Candidate publication uses a separate manual workflow on main only.
See [GHCR publication](GHCR.md).
