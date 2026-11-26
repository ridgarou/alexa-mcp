# Egress threat model (initial implementation)

## Goal and scope

Protect the local supervised Alexa MCP session from accidental or malicious
direct network access to arbitrary Internet or home-network destinations.
The initial policy supports Spain only. The existing app's 15 read tools
remain the application-level boundary, not Amazon-scoped credentials.

## Trusted components

The Linux host/kernel, Docker daemon, root operator, reviewed launcher,
Squid image/config, DNS resolvers and Amazon endpoints are trusted.
A hostile root, Docker administrator, mutable root code, kernel escape or
compromised proxy is outside the isolation guarantee. Do not grant the
launcher or Docker socket to agents. Keep the actual host topology private.

## Controls

- Dedicated isolated bridge and separate proxy outbound bridge; no ports.
- Two inert placeholders until all guards have been installed and inspected.
- Exact domain ACL before DNS-dependent private/reserved destination checks.
  No suffix wildcard, direct IP target, non-CONNECT or non-443 request.
- Host scoped input/forward deny rules and default-deny network namespace
  input/output/forward rules; app can only reach the proxy TCP port.
- Namespace output filter runs before embedded DNS DNAT. Proxy DNS is
  explicit, IPv4 only. No TLS interception, no disabling certificate checks.
- No persistent process, no automatic restart; stop project before removing
  firewall. Session locking only covers this launcher; legacy launches are
  a separate operational risk.
- No account data in tests, CI, logs or proxy configuration.

## Remaining limitations and tests

CONNECT tunnels encrypt the HTTP path, method and body. A compromised client
can send arbitrary bytes to an allowed IP/port, including a different TLS
virtual host on shared infrastructure, and can misuse permitted Amazon
operations. No SNI enforcement or granular HTTP action policy is implemented.
A compromised Squid can use public IPv4 TCP 443 and the permitted DNS
resolvers. The host cannot independently validate Amazon domain identity
from these encrypted connections. DNS poisoning, public-address hairpin NAT
on an external router, changes to host routes during a session and other
privileged changes need separate consideration. Private and explicit host
route blocking reduces but does not eliminate all such risks.

The allowlist is provisional, derived from prior static review and observed
normal/renewal destinations. Discovery responses do not prove an endpoint
is required. Add exact hosts only after reviewing a failed operation and
the dependency source, not via a broad wildcard. Interactive login is not
part of this mode. A different locale requires review.

No claim of zero DNS leakage or verified hostile-client containment until
the tests pass on the target host. Synthetic negative probes alone do not
prove all bypasses impossible. Add host-specific positive control listeners,
DNS observation and fault injection before stable acceptance.
