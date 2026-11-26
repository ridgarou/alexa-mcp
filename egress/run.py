#!/usr/bin/env python3
"""Root-only, on-demand guarded stdio launcher. No Docker socket in either container."""
import argparse
import contextlib
import fcntl
import ipaddress
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time

from policy import (TABLE, PRIVATE_BR, OUTBOUND_BR, BLOCKED, DNS,
                    host_policy, namespace_policy, validate_networks, validate_domains)

ROOT = Path(__file__).resolve().parent
PROJECT = "alexa-egress"
STATE = Path("/run/alexa-egress")
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin:/usr/local/bin",
       "HOME": "/root", "LANG": "C.UTF-8"}
KEYS = set("""
ALEXA_MCP_IMAGE ALEXA_EGRESS_IMAGE ALEXA_MCP_AUTH_DIR
ALEXA_MCP_AMAZON_PAGE ALEXA_MCP_ACCEPT_LANGUAGE ALEXA_MCP_PROXY_LANGUAGE
ALEXA_PRIVATE_SUBNET ALEXA_MCP_PRIVATE_IP ALEXA_PROXY_PRIVATE_IP
ALEXA_EGRESS_SUBNET ALEXA_PROXY_EGRESS_IP ALEXA_EGRESS_GATEWAY
ALEXA_EGRESS_UPLINK
""".split())
IMAGE = re.compile(r"(?:sha256:[0-9a-f]{64}|[a-z0-9./:_-]+@sha256:[0-9a-f]{64})\Z")

def note(message):
    print(message, file=sys.stderr, flush=True)

def cmd(args, *, data=None, capture=True, timeout=60, env=None, check=True):
    return subprocess.run(args, input=data, text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          env=env or ENV, timeout=timeout, check=check)

def js(args):
    return json.loads(cmd(args).stdout)

def trusted_file(path, private=False):
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & (0o077 if private else 0o022):
        raise RuntimeError("Untrusted launcher/configuration file")

def load_env():
    trusted_file(ROOT / ".env", private=True)
    env = {}
    for raw in (ROOT / ".env").read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep or key not in KEYS or key in env or not value or any(c.isspace() for c in value) or any(c in value for c in "$'\"\\`"):
            raise ValueError("Invalid .env entry")
        env[key] = value
    if set(env) != KEYS:
        raise ValueError("Missing .env settings")
    for key in ("ALEXA_MCP_IMAGE", "ALEXA_EGRESS_IMAGE"):
        if not IMAGE.fullmatch(env[key]):
            raise ValueError("Use immutable image digest or exact local image ID")
    if (env["ALEXA_MCP_AMAZON_PAGE"], env["ALEXA_MCP_ACCEPT_LANGUAGE"],
        env["ALEXA_MCP_PROXY_LANGUAGE"]) != ("amazon.es", "es-ES", "es_ES"):
        raise ValueError("Initial reviewed policy supports Spain only")
    return env

def addresses(env):
    return validate_networks(dict(
        private=env["ALEXA_PRIVATE_SUBNET"], outbound=env["ALEXA_EGRESS_SUBNET"],
        app=env["ALEXA_MCP_PRIVATE_IP"], proxy=env["ALEXA_PROXY_PRIVATE_IP"],
        ext=env["ALEXA_PROXY_EGRESS_IP"], gateway=env["ALEXA_EGRESS_GATEWAY"],
        uplink=env["ALEXA_EGRESS_UPLINK"]))

def compose(env, args, **kw):
    return cmd(DOCKER + ["compose", "--project-name", PROJECT,
        "--env-file", str(ROOT / ".env"), "-f", str(ROOT / "compose.yml")] + args,
        env={**ENV, **env}, **kw)

def project_containers():
    return cmd(DOCKER + ["ps", "-aq", "--filter",
        "label=com.docker.compose.project=" + PROJECT]).stdout.split()

def project_networks():
    return cmd(DOCKER + ["network", "ls", "-q", "--filter",
        "label=com.docker.compose.project=" + PROJECT]).stdout.split()

def nft_tables():
    return {(x["table"]["family"], x["table"]["name"])
            for x in js(["nft", "-j", "list", "tables"])["nftables"] if "table" in x}

def collect_networks(v):
    existing = []
    # All connected networks and explicitly routed IPv4 destinations.
    for route in js(["ip", "-j", "-4", "route", "show", "table", "all"]):
        dst = route.get("dst", "default")
        if dst == "default":
            continue
        net = ipaddress.IPv4Network(dst, strict=False)
        if net.prefixlen == 32 and str(net.network_address) in DNS and route.get("gateway") and route.get("dev") == v["uplink"]:
            continue
        existing.append(net)
    ids = cmd(DOCKER + ["network", "ls", "-q"]).stdout.split()
    if ids:
        for network in js(DOCKER + ["network", "inspect", *ids]):
            for config in (network.get("IPAM", {}).get("Config") or []):
                subnet = config.get("Subnet")
                if subnet and ipaddress.ip_network(subnet).version == 4:
                    existing.append(ipaddress.IPv4Network(subnet))
    for key in ("private", "outbound"):
        if any(ipaddress.IPv4Network(v[key]).overlaps(n) for n in existing):
            raise RuntimeError("Proposed subnet overlaps an existing network/route")
    for server in DNS:
        route = js(["ip", "-j", "-4", "route", "get", server])[0]
        if route.get("dev") != v["uplink"] or not route.get("gateway"):
            raise RuntimeError("DNS route does not use selected uplink")
        if any(ipaddress.IPv4Address(server) in net for net in existing):
            raise RuntimeError("DNS destination conflicts with blocked route")
    return tuple(str(n) for n in ipaddress.collapse_addresses(existing))

def check_auth(path):
    if not path.is_absolute() or path.resolve() != path:
        raise RuntimeError("Auth directory must be absolute and not a symlink")
    s = path.stat()
    if not stat.S_ISDIR(s.st_mode) or (s.st_uid, s.st_gid) != (1000, 1000) or s.st_mode & 0o077:
        raise RuntimeError("Unsafe credential directory ownership or permissions")
    for ancestor in path.parents:
        a = ancestor.stat()
        if a.st_uid != 0 or a.st_mode & 0o022:
            raise RuntimeError("Credential parent directory is not root controlled")
    f = (path / "alexa.json").lstat()
    if not stat.S_ISREG(f.st_mode) or (f.st_uid, f.st_gid) != (1000, 1000) or stat.S_IMODE(f.st_mode) != 0o600 or f.st_size == 0:
        raise RuntimeError("Stored authentication missing or unsafe")
    ids = cmd(DOCKER + ["ps", "-q"]).stdout.split()
    if ids:
        for container in js(DOCKER + ["inspect", *ids]):
            for mount in container.get("Mounts", []):
                if mount.get("Type") != "bind" or not mount.get("Source"):
                    continue
                other = Path(mount["Source"]).resolve()
                if other == path or other in path.parents or path in other.parents:
                    raise RuntimeError("Another running container may access credentials")

def install_nft(policy, prefix=()):
    cmd([*prefix, "nft", "-c", "-f", "-"], data=policy)
    cmd([*prefix, "nft", "-f", "-"], data=policy)
    # Verify both base chains and their installed rule count.
    result = js([*prefix, "nft", "-j", "list", "table", "inet", TABLE])
    actual = [x for x in result["nftables"] if "rule" in x]
    if len(actual) != sum(x.startswith("add rule ") for x in policy.splitlines()):
        raise RuntimeError("Unexpected installed firewall rule count")

def inspect_container(cid, expected, image_id, proxy=False):
    info = js(DOCKER + ["inspect", cid])[0]
    h, c, n = info["HostConfig"], info["Config"], info["NetworkSettings"]["Networks"]
    if (info["Image"] != image_id or not info["State"]["Running"] or not h["ReadonlyRootfs"]
            or h["Privileged"] or h.get("CapAdd") or "ALL" not in h.get("CapDrop", [])
            or "no-new-privileges:true" not in h.get("SecurityOpt", [])
            or h["RestartPolicy"]["Name"] != "no" or h.get("PortBindings")
            or h.get("PidMode") == "host" or h.get("IpcMode") == "host"
            or c["Entrypoint"] != ["/bin/sleep", "infinity"]
            or c["User"] != ("proxy" if proxy else "1000:1000")
            or {k: x["IPAddress"] for k, x in n.items()} != expected):
        raise RuntimeError("Container does not match guarded configuration")
    mounts = {m["Destination"]: m for m in info.get("Mounts", []) if m["Type"] == "bind"}
    if set(mounts) != {"/etc/alexa-egress" if proxy else "/app/.auth"}:
        raise RuntimeError("Unexpected bind mounts")
    if proxy and mounts["/etc/alexa-egress"]["RW"]:
        raise RuntimeError("Proxy configuration must be read only")
    pid = info["State"]["Pid"]
    if pid <= 1 or os.stat(f"/proc/{pid}/ns/net").st_ino == os.stat("/proc/self/ns/net").st_ino:
        raise RuntimeError("Invalid container network namespace")
    return pid

def validate_runtime_networks(v):
    for suffix, subnet, bridge, internal in (
        ("private", v["private"], PRIVATE_BR, True),
        ("outbound", v["outbound"], OUTBOUND_BR, False),
    ):
        network = js(DOCKER + ["network", "inspect", f"{PROJECT}_{suffix}"])[0]
        if (network["Driver"] != "bridge" or network["Internal"] != internal
            or network["EnableIPv6"] or network["Options"].get("com.docker.network.bridge.name") != bridge
            or (internal and network["Options"].get("com.docker.network.bridge.gateway_mode_ipv4") != "isolated")
            or {c.get("Subnet") for c in network["IPAM"]["Config"]} != {subnet}
            or len(network.get("Containers", {})) != (2 if internal else 1)):
            raise RuntimeError("Unexpected runtime network")

def probe(cid, v, amazon=False):
    source = (ROOT / "probe.mjs").read_text()
    r = cmd(DOCKER + ["exec", "-i", cid, "node", "--input-type=module", "-",
          v["proxy"], v["gateway"], "amazon" if amazon else "offline"], data=source,
          timeout=90)
    # Probe emits only fixed labels and timings; never forward raw upstream errors.
    note(r.stdout.strip())

def stop_project(env):
    compose(env, ["down", "--timeout", "5"], timeout=45)
    if project_containers() or project_networks():
        raise RuntimeError("Project cleanup incomplete")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run", "check"))
    parser.add_argument("--amazon", action="store_true",
                        help="also test unauthenticated HTTPS to one allowed Amazon host")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError("Run as root on the trusted Docker host")
    for name in ("run.py", "policy.py", "compose.yml", "squid.conf.template",
                 "allowed-domains.txt", "probe.mjs"):
        trusted_file(ROOT / name)
    STATE.mkdir(mode=0o700, exist_ok=True)
    if STATE.is_symlink() or STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o077:
        raise RuntimeError("Unsafe runtime state directory")
    with contextlib.ExitStack() as stack:
        fd = os.open(STATE / "session.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        stack.callback(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        env = load_env()
        v = addresses(env)
        if project_containers() or project_networks() or ("inet", TABLE) in nft_tables():
            raise RuntimeError("Existing egress resources: inspect and recover before starting")
        if any(x["ifname"] in (PRIVATE_BR, OUTBOUND_BR) for x in js(["ip", "-j", "link", "show"])):
            raise RuntimeError("Bridge name already in use")
        extra = collect_networks(v)
        image_ids = {k: cmd(DOCKER + ["image", "inspect", "--format", "{{.Id}}", env[k]]).stdout.strip()
                     for k in ("ALEXA_MCP_IMAGE", "ALEXA_EGRESS_IMAGE")}
        if any(not re.fullmatch(r"sha256:[a-f0-9]{64}", i) for i in image_ids.values()):
            raise RuntimeError("Image identity unavailable")
        temp = Path(tempfile.mkdtemp(prefix="session-", dir=STATE))
        # Config files are readable only inside the explicit read-only mount.
        config = temp / "config"
        config.mkdir(mode=0o755)
        domains = validate_domains((ROOT / "allowed-domains.txt").read_text())
        (config / "allowed-domains.txt").write_text("\n".join(domains) + "\n")
        squid = (ROOT / "squid.conf.template").read_text()
        squid = squid.replace("@CLIENT_IP@", v["app"]).replace("@PROXY_IP@", v["proxy"])
        squid = squid.replace("@BLOCKED_IPV4@", " ".join((*BLOCKED, *extra)))
        if "@" in squid:
            raise RuntimeError("Unresolved Squid configuration")
        (config / "squid.conf").write_text(squid)
        for f in config.iterdir():
            f.chmod(0o644)
        env["ALEXA_EGRESS_CONFIG_DIR"] = str(config)
        if args.mode == "check":
            auth = temp / "synthetic-auth"
            auth.mkdir(mode=0o700)
            os.chown(auth, 1000, 1000)
            env["ALEXA_MCP_AUTH_DIR"] = str(auth)
        else:
            check_auth(Path(env["ALEXA_MCP_AUTH_DIR"]))
        host_installed = False
        attempted_up = False
        try:
            # Parse before creating any resources; no override/autoloaded Compose.
            compose(env, ["config", "--quiet"])
            install_nft(host_policy(v, extra))
            host_installed = True
            attempted_up = True
            compose(env, ["up", "-d", "--no-build", "--pull", "never"], timeout=90)
            validate_runtime_networks(v)
            app = compose(env, ["ps", "-q", "AlexaMCP"]).stdout.strip()
            proxy = compose(env, ["ps", "-q", "AlexaEgress"]).stdout.strip()
            if not app or not proxy or app == proxy or len(project_containers()) != 2:
                raise RuntimeError("Missing guarded containers")
            app_pid = inspect_container(app, {PROJECT + "_private": v["app"]},
                                        image_ids["ALEXA_MCP_IMAGE"])
            proxy_pid = inspect_container(proxy, {PROJECT + "_private": v["proxy"],
                              PROJECT + "_outbound": v["ext"]}, image_ids["ALEXA_EGRESS_IMAGE"], True)
            if os.stat(f"/proc/{app_pid}/ns/net").st_ino == os.stat(f"/proc/{proxy_pid}/ns/net").st_ino:
                raise RuntimeError("Shared network namespace")
            for pid, is_proxy in ((app_pid, False), (proxy_pid, True)):
                install_nft(namespace_policy(v, is_proxy, extra),
                            ["nsenter", "--target", str(pid), "--net"])
            # Parse and start Squid only after all guard rules have been installed.
            squid_cmd = ["/usr/sbin/squid", "-f", "/etc/alexa-egress/squid.conf"]
            cmd(DOCKER + ["exec", proxy, *squid_cmd, "-k", "parse"])
            cmd(DOCKER + ["exec", "-d", proxy, *squid_cmd, "-N"])
            # Readiness is an actual client-side denial response, not an open port.
            for attempt in range(20):
                try:
                    cmd(DOCKER + ["exec", app, "node", "-e",
                        "const s=require('net').connect(3128,process.argv[1],()=>s.write('CONNECT example.invalid:443 HTTP/1.1\\r\\nHost: example.invalid:443\\r\\n\\r\\n'));s.setTimeout(800,()=>process.exit(1));s.once('error',()=>process.exit(1));s.once('data',d=>process.exit(/^HTTP\\/1\\.[01] 403\\b/.test(d.toString())?0:1))",
                        v["proxy"]], timeout=3)
                    break
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                    time.sleep(0.25)
            else:
                raise RuntimeError("Proxy readiness/deny probe failed")
            probe(app, v, args.amazon)
            if args.mode == "run":
                check = cmd(DOCKER + ["exec", app, "node", "-p",
                    "process.versions.node"]).stdout.strip()
                if tuple(map(int, check.split(".")[:2])) < (22, 21):
                    raise RuntimeError("Node lacks native environment proxy support")
                note("Guarded MCP session started; stdout reserved for MCP.")
                result = cmd(DOCKER + ["exec", "-i", app, "node", "dist/index.js"],
                             capture=False, timeout=None, check=False)
                if result.returncode:
                    raise RuntimeError("MCP process failed")
            note("GUARDED_SESSION: PASS")
        finally:
            # Keep firewall on any uncertain cleanup; never remove a preexisting table.
            if attempted_up:
                stop_project(env)
            if host_installed:
                cmd(["nft", "delete", "table", "inet", TABLE])
            import shutil
            shutil.rmtree(temp)

if __name__ == "__main__":
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except KeyboardInterrupt:
        note("Guarded session interrupted; inspect cleanup if necessary.")
        sys.exit(130)
    except Exception as exc:
        # Never output subprocess stderr, config values or credential details.
        note("GUARDED_SESSION: FAIL (" + type(exc).__name__ + ")")
        if isinstance(exc, (ValueError, RuntimeError)):
            note(str(exc))
        sys.exit(1)
