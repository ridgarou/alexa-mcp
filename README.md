# alexa-mcp — hardened Docker fork

[![Hardened validation](https://github.com/ridgarou/alexa-mcp/actions/workflows/hardening-candidate.yml/badge.svg?branch=main)](https://github.com/ridgarou/alexa-mcp/actions/workflows/hardening-candidate.yml)

An [MCP](https://modelcontextprotocol.io) server for auditing Amazon Alexa
routines, smart-home devices, scenes, groups and broken references.
It uses the unofficial Alexa cloud API through
[alexa-remote2](https://github.com/Apollon77/alexa-remote).

This fork of [snordquist/alexa-mcp](https://github.com/snordquist/alexa-mcp)
adds a hardened Docker deployment for Linux home servers. The supplied
Compose configuration is read-only at the MCP tool level. Upstream write
tools remain available in the source but are not exposed by the supplied
Docker configuration.

> **Versioning:** this fork follows independent [Semantic Versioning](https://semver.org/),
> starting at `1.0.0-rc.1`, now published to GHCR. The previous
> `0.7.0-hardened.1-rc.1` image remains available under its historical name.
> This is not a stable release. The maintainer confirmed public package visibility; anonymous pulls must
> still be verified before use; live Amazon authentication, refresh and host-specific
> network controls still require validation. Do not replace a working production
> deployment yet. See [CHANGELOG.md](CHANGELOG.md).
>
> This project is not affiliated with or supported by Amazon. It uses
> undocumented APIs that can change without notice, and its use may be
> subject to Amazon's terms. Use only with your own authorized account.
> The temporary login proxy handles sensitive authentication traffic.
> Keep it private.

## Project governance

- [AGENTS.md](AGENTS.md): repository-wide instructions for maintainers and AI agents.
- [Technical decision log](docs/DECISIONS.md): architecture, versioning, security,
  GitHub Free constraints, release criteria and future roadmap.
- [CHANGELOG.md](CHANGELOG.md): release history and unreleased changes.

## Contents

- [Docker quick start](#docker-quick-start)
- [First-time authentication](#first-time-authentication)
- [Connect an MCP client](#connect-an-mcp-client)
- [Updates and rollback](#updates-and-rollback)
- [Troubleshooting](#troubleshooting)
- [Native installation](#native-installation)
- [Tools](#tools)
- [Configuration](#configuration-environment-variables)
- [Security and privacy](#security--privacy)
- [Changelog](CHANGELOG.md)

## Docker quick start

### Requirements

- Linux host with Docker Engine and Docker Compose v2, Git and SSH.
  The CI and planned GHCR distribution target `linux/amd64`.
- A browser and an Amazon account authorized for use, including any
  authentication factors Amazon requires.
- Docker access for the operator who launches the MCP process. Docker
  access is highly privileged on a rootful host; do not grant it to an
  untrusted agent. No host installation of Node.js or npm is needed.
- Outbound connectivity to the required Amazon endpoints. Building locally
  also needs access to the container, Debian and npm registries.

### 1. Obtain the Compose files and build the candidate

For development and review, obtain the fork's main branch and check out
the source commit used to publish the current candidate:

```bash
git clone https://github.com/ridgarou/alexa-mcp.git
cd alexa-mcp
git checkout --detach 3906b98bca312c719d4e3668f72623604cd83414
cp .env.example .env
docker compose version
```

Review the selected commit, changelog and CI result before building.
For a later release, use the matching reviewed release checkout rather
than a moving feature branch.

```bash
git rev-parse HEAD
docker build --pull --platform linux/amd64 \
  -t local/alexa-mcp:hardened-candidate .
```

The Dockerfile builds TypeScript with Node 22, installs from the committed
lockfile with lifecycle scripts disabled, applies the version-specific
proxy patch and produces a Debian 13 runtime without npm, Yarn or Corepack.

### 2. Configure the region and credential directory

Edit `.env`. Example for Spain (other Amazon regions may differ):

```dotenv
ALEXA_MCP_IMAGE=local/alexa-mcp:hardened-candidate
ALEXA_MCP_AUTH_DIR=/var/lib/alexa-mcp/auth
ALEXA_MCP_AMAZON_PAGE=amazon.es
ALEXA_MCP_ACCEPT_LANGUAGE=es-ES
ALEXA_MCP_PROXY_LANGUAGE=es_ES
```

Do not put passwords, cookies or tokens in `.env`.

For a **new installation on a rootful Linux Docker host** using the example
path, create the private directory outside the Git checkout:

```bash
sudo install -d -m 0700 -o root -g root /var/lib/alexa-mcp
sudo install -d -m 0700 -o 1000 -g 1000 /var/lib/alexa-mcp/auth
```

If migrating an existing installation, inspect the existing directories
and ownership first; do not overwrite or delete existing credentials.
The container runs as UID/GID 1000. Rootless Docker and user-namespace
remapping may require different host-side ownership.

The writable bind mount is necessary for token renewal. The container
root filesystem remains read-only. The credential file is
`/app/.auth/alexa.json` inside the container and
`/var/lib/alexa-mcp/auth/alexa.json` on the host with this example.

### 3. Validate configuration

```bash
docker compose -f compose.yml config
docker compose -f compose.yml -f compose.auth.yml config
```

Normal MCP mode must have no published ports. Only the explicit
authentication override publishes TCP 3456 on host address 127.0.0.1.

The normal service is named `AlexaMCP` (case-sensitive). It uses MCP over
**stdio**, not HTTP. It does not need a reverse proxy, a web dashboard or
an always-running background container.

### Using GHCR instead of a local build

Version `1.0.0-rc.1` was published on 2026-11-26 in
[workflow run 45770005405](https://github.com/ridgarou/alexa-mcp/actions/runs/45770005405).
The public package was previously confirmed by the maintainer; verify anonymous
access before deployment. Use this immutable image reference:

```dotenv
ALEXA_MCP_IMAGE=ghcr.io/ridgarou/alexa-mcp@sha256:bfb28bc6e411df717d45c2f1f595cec30e7b0b41ff71ef909128b1a7b7e7d80d
```

Use the corresponding Compose files from source commit 3906b98.
Public packages can be pulled without a PAT after their public visibility
has been verified. If the pull returns an authorization error, check
package visibility rather than embedding credentials in Compose.

```bash
docker compose -f compose.yml pull AlexaMCP
```

See [GHCR.md](docs/GHCR.md) for publication details. There is no `latest`
tag or automatic deployment.

## First-time authentication

Skip this step if you already have a valid registration file compatible
with the fork. Keep that file in the private bind mount, and stop other
MCP or authentication sessions before testing.

### 1. Open an SSH tunnel for a remote server

On the computer running the browser (not on the Docker server), use
OpenSSH to forward a loopback port:

```bash
ssh -N -T -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:3456:127.0.0.1:3456 user@your-docker-host
```

Leave this session open. If the browser is on the Docker host itself,
no SSH tunnel is needed. Do not publish the proxy directly to the LAN,
the Internet or through Traefik. Use a Docker version that correctly
isolates loopback-published ports and verify this from another LAN host.

### 2. Start the temporary authentication container

On the Docker host, in the checkout:

```bash
docker compose -f compose.yml -f compose.auth.yml run \
  --rm --no-deps --service-ports -T --name alexa-auth-session \
  AlexaMCP sh -ec '
    umask 077
    test ! -e /app/.auth/alexa.json
    test ! -L /app/.auth/alexa.json
    node dist/auth-cli.js >/dev/null 2>&1
    test -s /app/.auth/alexa.json
    chmod 600 /app/.auth/alexa.json
  '
```

The command intentionally refuses to overwrite an existing file and
suppresses authentication output because it may include sensitive data.
It is normal for it to wait without displaying logs.

Open **http://127.0.0.1:3456/** in the browser and complete Amazon sign-in
and any required 2FA. Keep the browser on that exact address so the
proxy's redirect URL matches. If Amazon redirects into the Alexa app,
try a browser on a device without the app.

After authentication, the CLI performs a device-list smoke request and
the temporary container should exit. The command verifies that a
nonempty credential file exists; this alone does not prove that all
Alexa requests work.

### 3. Verify the file and close authentication

For the example host path, verify metadata only:

```bash
sudo stat -c '%a %u:%g %s bytes' /var/lib/alexa-mcp/auth/alexa.json
```

Expect mode 600, ownership 1000:1000 and a nonzero size. Never print
the contents. If the authentication container is still running after
you finish, stop it:

```bash
docker stop alexa-auth-session
```

Close the SSH tunnel. The normal MCP command must not include
`compose.auth.yml` or `--service-ports`.

Stored credentials are reused and may be refreshed by the dependency
while the MCP process is running (default interval: four days).
An invalid or nonrenewable session returns an error in MCP mode rather
than starting a login proxy automatically. Perform explicit manual
reauthentication only when required.

## Connect an MCP client

### Launch command

Run the server on demand:

```bash
docker compose -f compose.yml run --rm --no-deps -T AlexaMCP
```

This starts a stdio MCP server, not an interactive shell. The client
sends MCP JSON-RPC requests on stdin and reads responses from stdout.
An idle terminal waiting for input is not evidence of a failure.
Do not use detached mode, a TTY, or ordinary HTTP health checks.
The client owns the lifetime of the subprocess.

### Generic stdio client configuration

For a **trusted MCP launcher running on the Docker host**, a typical
`mcpServers` configuration is shown below. Replace all example paths
with absolute local paths. The exact configuration file and schema
depend on the MCP client.

```json
{
  "mcpServers": {
    "alexa": {
      "command": "docker",
      "args": [
        "compose",
        "--project-directory", "/absolute/path/alexa-mcp",
        "--env-file", "/absolute/path/alexa-mcp/.env",
        "-f", "/absolute/path/alexa-mcp/compose.yml",
        "run", "--rm", "--no-deps", "-T", "AlexaMCP"
      ]
    }
  }
}
```

### Codex stdio configuration

For a trusted Codex process on the same Docker host, an equivalent
`config.toml` example is:

```toml
[mcp_servers.alexa]
command = "docker"
args = ["compose", "--project-directory", "/absolute/path/alexa-mcp", "--env-file", "/absolute/path/alexa-mcp/.env", "-f", "/absolute/path/alexa-mcp/compose.yml", "run", "--rm", "--no-deps", "-T", "AlexaMCP"]
```

These examples require a trusted launcher with Docker permissions.
They do **not** provide a safe integration for an agent that itself runs
inside an isolated container or on a remote machine. In those cases,
use a separately reviewed, restricted stdio gateway or host-side
launcher. Do not mount `/var/run/docker.sock` or the credential
directory into an agent container. A restricted remote Codex bridge
is not included yet.

The supplied Compose configuration explicitly sets
`ALEXA_MCP_ALLOW_WRITE: "0"`. Start with inventory-only requests such
as `alexa_list_devices`, `alexa_list_routines` or
`alexa_list_smarthome_devices`. The server exposes 15 read tools;
the source field is not a complete inventory of installed Alexa skills.

### Offline smoke test

With the candidate image built, run the same synthetic MCP check used by
CI from the repository root. It does not mount the credential directory
or allow network access:

```bash
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges:true -i \
  local/alexa-mcp:hardened-candidate node --input-type=module \
  < tests/security/mcp-readonly.mjs
```

This checks the tool inventory, schemas, invalid arguments and missing
authentication behavior. It does not test real Amazon access.

## Updates and rollback

Use a reviewed release or candidate digest and the matching Compose
configuration when available. Do not deploy automatically from GitHub
or enable Watchtower updates for this service.

1. Stop active MCP clients and any authentication session.
2. Record the current image digest and keep the matching Compose files.
3. Protect a local backup of existing credentials with restrictive
   permissions; never upload that backup to GitHub.
4. Set `ALEXA_MCP_IMAGE` in `.env` to the new reviewed digest and
   run `docker compose -f compose.yml pull AlexaMCP`.
5. Validate the Compose configuration, start the MCP client and
   check read operations and real session renewal.
6. If a regression occurs, stop the client and restore the previous
   image digest and matching configuration. Credential changes may
   not be reversible; do not blindly restore an expired token.

For a locally built candidate, retain a separate reviewed image tag or
ID before rebuilding. Do not remove the previous image until the new
version has been verified. Do not delete or reinitialize the auth
directory as part of a routine update.

## Troubleshooting

| Symptom | What to check |
|---|---|
| No web interface on the normal container | Expected: this is a stdio MCP service. |
| `No Alexa auth found` | Check the configured bind mount, ownership and registration file without printing it. |
| Re-login required | Stop active sessions and follow the explicit authentication procedure. Preserve existing credentials until revocation/renewal is planned. |
| Authentication page unreachable | Verify SSH forwarding, temporary container and loopback publication; do not expose a LAN port. |
| Existing session prevents login | The guard is intentional. Review revocation and local credential handling before attempting a fresh login. |
| Permission denied writing credentials | Check the mounted directory is writable by the container UID/GID and has the expected private permissions. |
| Image not found | Build the local image first, or use the reviewed GHCR digest once access has been verified. |
| Client cannot launch Docker | Check local launcher permissions and absolute paths. Do not solve this by giving an untrusted agent a Docker socket. |
| No logs from authentication | Output is intentionally suppressed. Use only sanitized diagnostics. |

For a failed session that must be replaced, first stop all clients,
review and revoke the relevant Amazon session/device as appropriate,
then securely move the old file out of the active auth path before
running authentication again. Deleting a local file alone does not
revoke Amazon credentials. Do not assume an old backup can be reused.

## Native installation

Docker is the recommended deployment for this fork. Native use is an
alternative for development, and does not provide the container security
controls.

Use Node 22, npm, Git and the `patch` utility on Linux:

```bash
npm ci --ignore-scripts
npm audit --include=dev --audit-level=low
npm audit signatures
(
  cd node_modules/alexa-cookie2
  patch --dry-run --batch --forward --fuzz=0 -p1 < ../../patches/alexa-cookie-proxy.patch
  patch --batch --forward --fuzz=0 -p1 < ../../patches/alexa-cookie-proxy.patch
  node --check lib/proxy.js
)
npm test
```

For a new native session only, run `umask 077` and `npm run auth` with
the default loopback bind, on a private terminal. Use an SSH tunnel for
a remote host. Avoid raw authentication logs. With a valid token,
`npm start` runs the stdio server. A native MCP client can invoke
`node /absolute/path/alexa-mcp/dist/index.js` with an appropriate
working directory or explicit `ALEXA_MCP_AUTH_PATH`.

Write tools are retained for upstream compatibility but are not recommended
for automated agents. They require deliberate native opt-in via
`ALEXA_MCP_ALLOW_WRITE=1`. Review individual tool semantics and do not
assume a confirmation argument provides a security boundary.

## Tools

| Tool | Purpose | Writes |
|---|---|---|
| `alexa_list_devices` | Registered Echos / apps / Fire TVs | no |
| `alexa_list_routines` | All routines: id, name, status, triggers | no |
| `alexa_get_routine` | One routine as raw JSON (incl. action sequence) | no |
| `alexa_list_scenes` | Smart-home entities incl. scenes | no |
| `alexa_get_activity` | Activity history (customer-history-records) | no |
| `alexa_list_smarthome_devices` | Smart-home devices with source (skill/Matter) + entity id — find orphans | no |
| `alexa_audit_broken_references` | Find routines whose action targets a device/scene/group that no longer exists | no |
| `alexa_get_volumes` | Current speaker volume of every device | no |
| `alexa_get_do_not_disturb` | Do-Not-Disturb status per device | no |
| `alexa_query_device` | Live state of smart-home devices/groups by applianceId | no |
| `alexa_list_groups` | Smart-home groups (rooms/spaces) with members | no |
| `alexa_list_lists` | Shopping / to-do / custom lists | no |
| `alexa_get_list_items` | Items of a list by id | no |
| `alexa_get_player_info` | Now-playing / media player state of a device | no |
| `alexa_list_notifications` | Reminders / alarms / timers (id, time, label, status) | no |
| `alexa_create_routine` | Create a routine (voice- or time-triggered) with one or more actions | **yes** |
| `alexa_update_routine` | Update a routine in place (full re-spec) | **yes** |
| `alexa_set_routine_enabled` | Enable/disable a routine by id (rebuilds + PUTs with flipped status) | **yes** |
| `alexa_trigger_routine` | Execute a routine now | **yes** |
| `alexa_delete_routine` | Delete a routine + verify | **yes** |
| `alexa_delete_smarthome_device` | Delete a smart-home device (orphan cleanup) — refuses if referenced by a routine/group unless `force`, and verifies removal | **yes** |
| `alexa_speak` | Make a device speak / announce (`speak` \| `announcement` \| `ssml`) | **yes** |
| `alexa_text_command` | Run a typed command as if spoken to a device | **yes** |
| `alexa_set_volume` | Set an Echo's speaker volume (0–100) | **yes** |
| `alexa_set_do_not_disturb` | Enable/disable Do-Not-Disturb on a device | **yes** |
| `alexa_media_control` | Media transport: play/pause/next/previous/forward/rewind/shuffle/repeat | **yes** |
| `alexa_add_list_item` | Add an item to a list | **yes** |
| `alexa_update_list_item` | Edit a list item's text / mark complete | **yes** |
| `alexa_delete_list_item` | Remove a list item | **yes** |
| `alexa_create_group` | Create a smart-home group (room/space) | **yes** |
| `alexa_update_group` | Rename a group / set members (read-modify-write) | **yes** |
| `alexa_delete_group` | Delete a smart-home group (members untouched) | **yes** |
| `alexa_set_smarthome_enablement` | Enable/disable a smart-home device | **yes** |
| `alexa_create_reminder` | Create a reminder on a device | **yes** |
| `alexa_create_alarm` | Create an alarm (< 1 year out; it rings) | **yes** |
| `alexa_delete_notification` | Delete a reminder / alarm / timer by id | **yes** |

The supplied Docker Compose configuration exposes only the 15 read tools above.
The write tools below are retained from upstream for explicitly configured native use;
they have not been tested against a live account in this fork.

Most write tools also accept `dryRun: true` to preview the request/plan without executing.

Routine **create/update** were reverse-engineered from the Alexa app and reported as tested by upstream; see
[ARCHITECTURE.md](./ARCHITECTURE.md) for the exact write-API (the trigger `payload` is
double-encoded and the action `operationPayload` must be `/operation/validate`-normalized — the
tools handle both). Example create:

```json
{ "name": "Gute Nacht Ansage", "triggerUtterance": "gute nacht",
  "actions": [ { "type": "Alexa.TextCommand", "operationPayload": { "text": "schlaf gut" } } ],
  "confirm": true }
```

Write tools are only registered when `ALEXA_MCP_ALLOW_WRITE=1`, and each destructive call also
requires an explicit `confirm: true` argument.


## Configuration (environment variables)

| Variable | Default in supplied Docker configuration | Purpose |
|---|---|---|
| `ALEXA_MCP_IMAGE` | `local/alexa-mcp:hardened-candidate` | Compose image reference; use a reviewed digest for GHCR. |
| `ALEXA_MCP_AUTH_DIR` | `/var/lib/alexa-mcp/auth` | Existing host credential directory. |
| `ALEXA_MCP_AMAZON_PAGE` | `amazon.de` | Amazon region; example .env uses amazon.es. |
| `ALEXA_MCP_ACCEPT_LANGUAGE` | `de-DE` | Accept-Language header; example uses es-ES. |
| `ALEXA_MCP_PROXY_LANGUAGE` | Derived from acceptance language | Proxy locale; example uses es_ES. |
| `ALEXA_MCP_ALLOW_WRITE` | `0` | Write tools disabled in Compose. |
| `ALEXA_MCP_AUTH_PATH` | `/app/.auth/alexa.json` | Credential file inside container. |
| `ALEXA_MCP_PROXY_IP` | `127.0.0.1` | Browser URL host for explicit authentication. |
| `ALEXA_MCP_PROXY_PORT` | `3456` | Login proxy port. |
| `ALEXA_MCP_PROXY_BIND` | `127.0.0.1` | Normal mode; auth override uses 0.0.0.0 inside container with loopback-only host publication. |
| `ALEXA_MCP_WS_MQTT` | `false` | Push connection disabled. |
| `ALEXA_MCP_REFRESH_MS` | Application default 345600000 (4 days) | Native/application setting; requires explicit Compose environment mapping to override in Docker. |

The first five variables above are configurable through the example
`.env` file. Other values are explicit in Compose or application
defaults; adding arbitrary variables to `.env` does not automatically
pass them into the container. Keep the supplied read-only and proxy
settings unchanged for normal operation.

## Security & privacy

- No published ports in normal mode, no privileged container, no Docker
  socket, no host networking, dropped capabilities, non-root UID/GID
  1000, read-only root filesystem, limited processes and 384 MiB memory.
- Credentials are persisted in a private writable directory with atomic
  replacement and restricted file mode. Use only one authentication/MCP
  writer at a time. Local credential access and session refresh still
  carry account-level privileges.
- A dedicated bridge is **not** an outbound allowlist. Egress enforcement,
  real account validation and a restricted agent gateway are pending.
- Read-only MCP tools do not make the Amazon credential itself read-only.
  Some read queries use POST. See [READ_ONLY_AUDIT.md](docs/READ_ONLY_AUDIT.md).
- Responses may contain private device information, voice history,
  routines and untrusted text. Do not treat returned content as instructions.
- The candidate uses pinned dependencies and image bases, npm signatures
  and vulnerability scanning. A successful audit does not establish
  absence of vulnerabilities. See [SECURITY.md](docs/SECURITY.md).
- Authentication logs are suppressed and the Compose logging driver is
  disabled; no real account data belongs in GitHub Actions or issue reports.

## Known limitations

- **Unofficial API** — can break whenever Amazon changes it.
- **Routine deletion endpoint is unverified.** `alexa_delete_routine` attempts
  `DELETE /api/behaviors/v2/automations/{id}`, which is not documented or confirmed. Verify the
  real request via browser DevTools before relying on it.
- **Device deletion may not be permanent** if the underlying source still advertises the device:
  a skill that is still linked (and whose backend responds) or a Matter bridge will re-add it on
  the next discovery. Orphans whose backend is gone (unlinked skill, removed integration) stay
  deleted.
- **Matter duplicate devices** (the same device appearing once per Alexa Echo/hub that acts as a
  Matter controller) are an Alexa-side artifact, not a bridge misconfiguration. Deleting the
  redundant copies works, but new ones can reappear if the Matter bridge is re-commissioned.

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the auth flow, endpoint reference, and
implementation notes.

## License

[MIT](./LICENSE) © Sascha Nordquist

