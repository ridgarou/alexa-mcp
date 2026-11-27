# Alexa MCP Egress Proxy

**Status: experimental, not released.** This optional component is developed
independently of the current application release. Do not deploy it until CI
and supervised host acceptance have passed. It is not a shared proxy for agents.

## Architecture

```text
Trusted host launcher (root; exclusive session lock)
  | applies scoped host and container-namespace rules
  | starts inert containers, verifies policies, then launches programs
  v
Alexa MCP -- stdio (no published port, read-only tools)
  |
  | IPv4 TCP 3128 only; no direct DNS or Internet
  v
Squid -- exact-host HTTPS CONNECT allowlist, no TLS interception
  |
  | separate bridge; DNS to specified resolvers, TCP 443 via selected uplink
  v
Amazon endpoints
```

The proxy has no credential mount, Docker socket or published ports.
The application has only the existing credential directory, never the
proxy's outbound network. Both use a read-only root filesystem, dropped
capabilities, non-root users, no restart and bounded resources.

## Files

- `Dockerfile`: Debian-based Squid image, pinned base and security updates.
- `compose.yml`: complete independent project; no Compose override merging.
- `allowed-domains.txt`: exact initial allowlist for Spain.
- `squid.conf.template`: CONNECT-only policy, cache and access logs disabled.
- `policy.py`: generates dedicated host and namespace nftables rules.
- `run.py`: guarded launch, preflight, cleanup and session lock.
- `install.py` and `alexa-egress-manager`: fresh root-controlled installation and fixed command entrypoint.
- `readiness.mjs`, `probe.mjs`, `test_policy.py`: live negative probes and synthetic policy tests.
- `.env.example`: generic example; keep the actual .env local.
- [Threat model](THREAT_MODEL.md): trust boundaries and limitations.

## Prerequisites and trust

Linux amd64, rootful local Docker Engine 28+ (isolated bridge support),
Compose 2.33.1+ (gateway priority), Python 3, nftables, iproute2 and nsenter.
Node 22.21+ with native proxy support. The initial reviewed application baseline is the published 1.0.0 image
(Node 22), pinned to its immutable digest in .env.example.
The launcher requires root and must live in a root-owned directory whose
ancestors are not group/world writable. Never expose this script, Docker
socket, root SSH or arbitrary command execution to agents. Review all files
and image identities before running any privileged command. This component
does not change global firewall policies or enable nftables.service.

## Build and configure (only after the development PR is reviewed)

From a reviewed repository checkout:

```sh
docker build --pull -t local/alexa-egress:reviewed egress
docker image inspect --format '{{.Id}}' local/alexa-egress:reviewed
```

Review and scan this local image, including unfixed findings. The build uses
updated Debian packages, so it is not bit-for-bit reproducible. The proxy
is not yet published to GHCR. Pin the resulting local sha256 image ID;
do not use a mutable tag in the launcher configuration.

Pull and verify the exact published application image before using the launcher.
The launcher never pulls images or builds at runtime.

```sh
docker pull --platform linux/amd64 ghcr.io/ridgarou/alexa-mcp@sha256:52f989c09e95748e4c853c5db705a0ba6b3b642e7394078b68b979f7e7228862
docker image inspect --format 'Version={{index .Config.Labels "org.opencontainers.image.version"}} Revision={{index .Config.Labels "org.opencontainers.image.revision"}}' ghcr.io/ridgarou/alexa-mcp@sha256:52f989c09e95748e4c853c5db705a0ba6b3b642e7394078b68b979f7e7228862
```

Expect version 1.0.0 and revision `1b45d5dd20d2543eeb89a6968d1b19128d38fdf5`.
The normal stable installation remains independent and available for rollback.
The egress component is not included in the published 1.0.0 application image.

## Install the manager and Docker stack

The host manager is separate from the two Docker containers. Its fixed
installation layout is:

| Path | Purpose |
| --- | --- |
| `/opt/alexa-egress-manager/` | Python manager and Node diagnostic probes |
| `/etc/alexa-egress-manager/` | Local .env and configuration example |
| `/opt/containers-data/AlexaEgress/` | Dockerfile, AlexaEgress.yml, Squid policy and documentation |
| `/usr/local/sbin/alexa-egress-manager` | Root-only administration command |
| `/run/alexa-egress-manager/` | Session lock and generated temporary configuration |

All three installation directories are root:root, mode 0700; all their
ancestors must be root-owned, non-symlink directories with no group/other
write permission. The local .env must be root-owned mode 0600. Do not mount
these paths writable into Codex, Hermes or another agent; container UID 0
or Docker API access can defeat ordinary filesystem permissions.

Before installation, inspect the existing parent with
`namei -l /opt/containers-data`. If it is not root controlled, stop.
A root-owned ancestor with setgid and no group/other write permission is
acceptable. New directories and files are explicitly normalized to root:root;
setgid is not inherited into the installed directories. The existing parent
is left unchanged. Do not recursively change ownership or permissions of
existing stacks.

From a reviewed, pinned checkout, prepare a new staging directory and copy
only reviewed files. Do not execute unreviewed code as root.

```sh
sudo test ! -e /opt/alexa-egress-staging
sudo install -d -m 0700 /opt/alexa-egress-staging
sudo cp -a egress/. /opt/alexa-egress-staging/
sudo chown -R root:root /opt/alexa-egress-staging
sudo chmod -R go-w /opt/alexa-egress-staging
sudo /usr/bin/python3 -I -B /opt/alexa-egress-staging/install.py
```

The installer refuses existing destinations, including the previous
experimental layout and runtime directory. It does not modify Docker,
the firewall, credentials, other stacks or existing configuration.
It installs only an explicit file list, never a local .env from source.
The command uses an isolated Python interpreter and fixed paths.
After successful installation remove the reviewed staging copy.

Create the configuration separately (fresh installation only):

```sh
sudo test ! -e /etc/alexa-egress-manager/.env
sudo install -m 0600 /etc/alexa-egress-manager/.env.example /etc/alexa-egress-manager/.env
sudoedit /etc/alexa-egress-manager/.env
```

Set the reviewed app digest (the example uses the published 1.0.0 image),
proxy image ID, selected physical uplink, auth directory and disjoint
IPv4 networks. Check existing Docker/Podman subnets and all host routes.
The launcher rejects overlaps. The Spain-specific locale and exact
allowlist are intentionally narrow. No credentials in .env or Git.
An installed Dockerfile can also be built with
`sudo docker build --pull -t local/alexa-egress:reviewed /opt/containers-data/AlexaEgress`;
scan the resulting image before configuring its immutable ID.

## Check without accessing the Amazon account

```sh
sudo /usr/local/sbin/alexa-egress-manager check
```

This uses an empty synthetic auth directory, not your actual session.
It builds/pulls nothing at runtime. It checks Compose, installs a new
host table, starts inert sleep placeholders, checks actual network
attachments/image IDs, installs namespace policy before executing any
application code, parses/starts Squid and runs negative connectivity
probes. On successful completion it removes its own containers, networks,
and firewall table. Output is diagnostic stderr only.

Optional positive test (one unauthenticated HTTPS request with verified TLS,
not an account login):

```sh
sudo /usr/local/sbin/alexa-egress-manager check --amazon
```

If the synthetic check fails during startup, repeat only after reviewing cleanup.
The optional `check --diagnostics` flag exposes bounded Squid startup diagnostics
and listener status on failure. It is rejected in real session mode; review
local network details before sharing output. No access logging is enabled.
Squid runs attached in the foreground so startup exit status is visible.
ICMP pinger and persistent network measurements are disabled.

Each isolation probe reports a fixed identifier, PASS/FAIL and a bounded
status code, including on failure. An explicit proxy denial must be HTTP 403;
a timeout or arbitrary error is not accepted as proof of that ACL. Direct
TCP tests distinguish timeout/no-route from connection refusal. DNS tests
combine a raw UDP query, resolver status and independent host evidence.
The embedded Docker DNS must increment its pre-DNAT drop counter. The
public resolver must increment its drop counter or be proven unreachable
by route lookup in the application namespace. A resolver ECONNREFUSED
alone is not sufficient. No DNS answers or raw upstream errors are logged.
The entire expected result sequence must pass before starting MCP.

If a check fails, investigate; do not broaden the allowlist or remove a
guard just to pass. CI does not need Amazon credentials.

## Supervised MCP session

Only after acceptance, with no other MCP/auth process accessing the same
credential directory:

```sh
sudo /usr/local/sbin/alexa-egress-manager run
```

This command is a stdio transport for a trusted MCP client, not an
interactive shell. Do not run compose up or exec manually to start the
application in protected mode. The launcher checks the auth directory's
ownership/mode and running bind mounts, and serializes its own sessions.
The ordinary deployment does not share the lock; stop all legacy sessions
first. Do not use any other writer or agent while this session is active.

The existing credential renewal path should use Node's native environment
proxy. Interactive first login/reauthentication is **not supported in this
guarded mode**. Do not expose a login proxy via Squid. If authentication
expires, close the guarded session and use the explicitly approved legacy
loopback SSH-tunnel authentication procedure only after reviewing the
temporary broader egress risk. Never overwrite valid credentials.

## Firewall, DNS and lifecycle

A dedicated transient `inet alexa_guard` host table is applied atomically.
Its INPUT/FORWARD hooks at priority -10 are after destination NAT and
before standard filter chains. It does not flush or change Docker,
iptables-nft or Netavark tables. Allowed packets still traverse normal
host rules. Namespace OUTPUT hooks at -150 are before Docker's DNS DNAT
at -100. No loopback DNS exception is present in the application policy.
The proxy uses explicit DNS resolvers (1.1.1.1, 1.0.0.1); private, reserved,
connected and explicitly routed IPv4 destinations are denied, with the
reviewed DNS routes excepted. IPv6 IP traffic is denied in both namespaces.
The proxy may still query arbitrary names if the trusted proxy itself is
compromised; this is not a guarantee of zero exfiltration.

A normal exit or interrupt removes the project before removing its host
guard. No persistent service is needed: the next session reapplies policy.
A hard kill, Docker failure or interrupted cleanup can leave resources.
A subsequent launch refuses to proceed when existing project resources or
the host table are present. Do not delete the guard while any project
container is running. Recovery is an explicit root operation:

```sh
sudo docker ps -a --filter label=com.docker.compose.project=alexa-egress
sudo docker network ls --filter label=com.docker.compose.project=alexa-egress
sudo nft list table inet alexa_guard
```

After reviewing the IDs, stop/remove **only** the identified project
containers, then remove its two empty networks, then delete only
`inet alexa_guard` with `sudo nft delete table inet alexa_guard`.
Do not use global prune, flush ruleset, or restart Docker. Inspect any
remaining session directories under /run/alexa-egress-manager; they contain generated
config and possibly synthetic auth, not a copy of the real credential file.
Do not delete the lock while a launcher is running.

## Acceptance checklist

- Static tests, anonymous pull and identity of the pinned stable application,
  CI proxy build, Squid parse/start, negative isolation probes, image
  vulnerability scan and verified cleanup. Shared application CI separately
  validates the current source build.
- Host checks with synthetic auth, including known live host/LAN services,
  DNS and direct IP/IPv6 paths, missing guard and concurrent launch.
- Positive verified TLS through native Node proxy, real supervised inventory
  and natural renewal; observe denied destinations without raw auth logs.
- Review proxy DNS resolution and TLS limitations; measure active and idle
  resource use. Review fresh image scan findings.
- Test interruption and recovery; verify existing unrelated services remain
  functional. No direct autonomous agent access until a restricted gateway
  and the operation-level controls have been reviewed.

A destination allowlist is not a method/path allowlist. CONNECT does not
inspect Amazon requests or guarantee a read-only Amazon account. See the
[threat model](THREAT_MODEL.md) before considering it a security boundary.
