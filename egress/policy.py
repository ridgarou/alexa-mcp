"""Pure policy generation for the guarded Linux deployment."""
import ipaddress
import re

TABLE = "alexa_guard"
PRIVATE_BR = "br-alexa-priv"
OUTBOUND_BR = "br-alexa-egress"
DNS = ("1.1.1.1", "1.0.0.1")
# Deliberately conservative; public globally routed IPv4 only.
BLOCKED = (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8",
    "169.254.0.0/16", "172.16.0.0/12", "192.0.0.0/24",
    "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
    "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24",
    "224.0.0.0/4", "240.0.0.0/4",
)
DOMAIN = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+\Z")
IFACE = re.compile(r"[a-zA-Z0-9_.-]{1,15}\Z")

def validate_networks(values):
    private = ipaddress.IPv4Network(values["private"])
    outbound = ipaddress.IPv4Network(values["outbound"])
    if private.overlaps(outbound) or any(
        not any(n.subnet_of(ipaddress.IPv4Network(r)) for r in
                ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
        for n in (private, outbound)
    ):
        raise ValueError("Networks must be disjoint RFC1918 IPv4 subnets")
    app, proxy, ext, gw = [ipaddress.IPv4Address(values[k])
                           for k in ("app", "proxy", "ext", "gateway")]
    if len({app, proxy, ext, gw}) != 4:
        raise ValueError("Duplicate address")
    for addr, net in ((app, private), (proxy, private), (ext, outbound), (gw, outbound)):
        if addr not in net or addr in (net.network_address, net.broadcast_address):
            raise ValueError("Invalid container address")
    if not IFACE.fullmatch(values["uplink"]) or values["uplink"] in (
        PRIVATE_BR, OUTBOUND_BR, "lo"
    ):
        raise ValueError("Invalid uplink")
    return {**values, "private": str(private), "outbound": str(outbound),
            "app": str(app), "proxy": str(proxy), "ext": str(ext), "gateway": str(gw)}

def validate_domains(text):
    domains = text.splitlines()
    if not domains or len(set(domains)) != len(domains):
        raise ValueError("Empty or duplicate domain allowlist")
    for domain in domains:
        if len(domain) > 253 or not DOMAIN.fullmatch(domain) or not any(
            domain.endswith(suffix) for suffix in (".amazon.es", ".amazon.com", ".amazonalexa.com")
        ):
            raise ValueError("Only exact approved Amazon hostnames are supported")
    return domains

def blocked_set(extra=()):
    nets = [ipaddress.IPv4Network(n) for n in (*BLOCKED, *extra)]
    return ", ".join(str(n) for n in ipaddress.collapse_addresses(nets))

def host_policy(v, extra=()):
    v = validate_networks(v)
    a, p, e, u = (v[k] for k in ("app", "proxy", "ext", "uplink"))
    blocked = blocked_set(extra)
    dns = ", ".join(DNS)
    return f"""create table inet {TABLE}
add set inet {TABLE} blocked4 {{ type ipv4_addr; flags interval; elements = {{ {blocked} }}; }}
add chain inet {TABLE} input {{ type filter hook input priority -10; policy accept; }}
add rule inet {TABLE} input iifname {{ "{PRIVATE_BR}", "{OUTBOUND_BR}" }} counter drop
add chain inet {TABLE} forward {{ type filter hook forward priority -10; policy accept; }}
add rule inet {TABLE} forward iifname "{PRIVATE_BR}" oifname "{PRIVATE_BR}" ip saddr {a} ip daddr {p} tcp dport 3128 return
add rule inet {TABLE} forward iifname "{PRIVATE_BR}" oifname "{PRIVATE_BR}" ip saddr {p} ip daddr {a} tcp sport 3128 ct state established return
add rule inet {TABLE} forward iifname "{PRIVATE_BR}" counter drop
add rule inet {TABLE} forward oifname "{PRIVATE_BR}" counter drop
add rule inet {TABLE} forward iifname "{OUTBOUND_BR}" ip daddr @blocked4 counter drop
add rule inet {TABLE} forward iifname "{OUTBOUND_BR}" oifname "{u}" ip saddr {e} ip daddr {{ {dns} }} udp dport 53 return
add rule inet {TABLE} forward iifname "{OUTBOUND_BR}" oifname "{u}" ip saddr {e} ip daddr {{ {dns} }} tcp dport 53 return
add rule inet {TABLE} forward iifname "{OUTBOUND_BR}" oifname "{u}" ip saddr {e} tcp dport 443 return
add rule inet {TABLE} forward iifname "{OUTBOUND_BR}" counter drop
add rule inet {TABLE} forward iifname "{u}" oifname "{OUTBOUND_BR}" ip daddr {e} ct state established,related return
add rule inet {TABLE} forward oifname "{OUTBOUND_BR}" counter drop
"""

def namespace_policy(v, proxy=False, extra=()):
    v = validate_networks(v)
    a, p, e = (v[k] for k in ("app", "proxy", "ext"))
    # Before Docker's loopback DNS DNAT at -100; no loopback exception.
    lines = [
        f"create table inet {TABLE}",
        f"add chain inet {TABLE} output {{ type filter hook output priority -150; policy drop; }}",
        f"add chain inet {TABLE} input {{ type filter hook input priority -150; policy drop; }}",
        f"add chain inet {TABLE} forward {{ type filter hook forward priority -150; policy drop; }}",
    ]
    if not proxy:
        lines += [
            f"add rule inet {TABLE} output ip saddr {a} ip daddr {p} tcp dport 3128 accept",
            f"add rule inet {TABLE} input ip saddr {p} ip daddr {a} tcp sport 3128 ct state established accept",
        ]
    else:
        blocked = blocked_set(extra)
        dns = ", ".join(DNS)
        lines += [
            f"add set inet {TABLE} blocked4 {{ type ipv4_addr; flags interval; elements = {{ {blocked} }}; }}",
            f"add rule inet {TABLE} input ip saddr {a} ip daddr {p} tcp dport 3128 accept",
            f"add rule inet {TABLE} output ip saddr {p} ip daddr {a} tcp sport 3128 ct state established accept",
            f"add rule inet {TABLE} output ip daddr @blocked4 drop",
            f"add rule inet {TABLE} output ip saddr {e} ip daddr {{ {dns} }} udp dport 53 accept",
            f"add rule inet {TABLE} output ip saddr {e} ip daddr {{ {dns} }} tcp dport 53 accept",
            f"add rule inet {TABLE} output ip saddr {e} tcp dport 443 accept",
            f"add rule inet {TABLE} input ip daddr {e} ct state established,related accept",
        ]
    lines += [f"add rule inet {TABLE} output counter drop", f"add rule inet {TABLE} input counter drop"]
    return "\n".join(lines) + "\n"
