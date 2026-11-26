# Hardened fork — candidate status

This branch is not a production release. It is based on upstream commit
a369d5f86858d8d43d4a982bedc5bffdaacccf0c. Preserve upstream MIT notices.

## Build and review

Run `node scripts/resolve-hardened-dependencies.mjs` in a clean checkout with
Node 22 and npm 10, review the resulting package.json and package-lock.json,
and commit both together. The migration must pass the registry audit. Do not
use npm audit fix --force or bypass peer dependency checks. Then run:

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
findings, including Debian and the Node runtime. Pin reviewed base image
digests for releases. The runtime intentionally has no npm, Yarn or Corepack.
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
  --service-ports -T AlexaMCP sh -c 'umask 077; node dist/auth-cli.js >/dev/null 2>&1'
```

Open http://127.0.0.1:3456 in the client browser. Stop the container and close
the tunnel when done. Use a Docker release that correctly isolates loopback
published ports; verify from another LAN client. Do not expose this HTTP
login proxy through a reverse proxy or directly to the LAN. The proxy handles
sensitive login traffic; the dependency patch relaxes one CSP directive
for local HTTP compatibility. Do not treat it as a general security fix.

Do not force reauthentication while a valid session exists. Never share raw
auth logs. The normal server must not intentionally expose login ports.

## Outstanding work

- Validate the reconstructed lockfile, runtime image and proxy patch.
- Review all read-tool implementations, not just their names.
- Make credential persistence atomic and sanitize runtime errors.
- Verify that invalid stored credentials cannot start an interactive proxy.
- Enforce outbound network restrictions; a dedicated bridge alone is not
  an egress allowlist.
- Verify real Amazon access and token refresh on the host only.
- Add a controlled release pipeline and digest-pinned deployment.
- Do not give agents a Docker socket or access to credential files.

The read-only MCP setting is an application control, not an Amazon account
permission boundary. Offline tests do not prove absence of malicious code,
network exfiltration or changes made internally by authentication libraries.
