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
import shutil

from supervisor import supervise

from policy import (TABLE, PRIVATE_BR, OUTBOUND_BR, BLOCKED, DNS,
                    host_policy, namespace_policy, validate_networks, validate_domains,
                    dns_denial_evidence)

ROOT = Path("/opt/alexa-egress-manager")
CONFIG = Path("/etc/alexa-egress-manager")
STACK = Path("/opt/containers-data/AlexaEgress")
PROJECT = "alexa-egress"
STATE = Path("/run/alexa-egress-manager")
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
cleaning = False
interrupted_signal = None

def note(message):
    print(message, file=sys.stderr, flush=True)

def cmd(args, *, data=None, capture=True, timeout=60, env=None, check=True):
    return subprocess.run(args, input=data, text=True,
                          stdin=subprocess.DEVNULL if data is None else None,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,
                          env=env or ENV, timeout=timeout, check=check)

def js(args):
    return json.loads(cmd(args).stdout)

def trusted_directory(path):
    for directory in (path, *path.parents):
        st = directory.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise RuntimeError("Untrusted directory or ancestor: " + str(directory))

def trusted_file(path, private=False):
    st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or (st.st_uid, st.st_gid) != (0, 0)
            or (stat.S_IMODE(st.st_mode) != 0o600 if private else st.st_mode & 0o022)):
        raise RuntimeError("Untrusted launcher/configuration file")

def load_env():
    trusted_file(CONFIG / ".env", private=True)
    env = {}
    for raw in (CONFIG / ".env").read_text().splitlines():
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
        "--env-file", str(CONFIG / ".env"), "-f", str(STACK / "AlexaEgress.yml")] + args,
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
        if net.prefixlen == 32 and str(net.network_address) in DNS and route.get("gateway"):
            # Ignore alternate routed DNS host entries as well; the actual
            # selected route must still use the configured uplink below.
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

def install_nft(policy, prefix=(), on_applied=None):
    cmd([*prefix, "nft", "-c", "-f", "-"], data=policy)
    cmd([*prefix, "nft", "-f", "-"], data=policy)
    if on_applied is not None:
        on_applied()
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

def dns_counters(pid):
    prefix = ["nsenter", "--target", str(pid), "--net"]
    result = {}
    for name in ("dns_docker_udp", "dns_public_udp"):
        data = js([*prefix, "nft", "-j", "list", "counter", "inet", TABLE, name])
        matches = [item["counter"] for item in data["nftables"]
                   if "counter" in item and item["counter"].get("name") == name
                   and item["counter"].get("table") == TABLE
                   and item["counter"].get("family") == "inet"]
        if len(matches) != 1 or type(matches[0].get("packets")) is not int:
            raise RuntimeError("DNS drop counter unavailable")
        result[name] = matches[0]["packets"]
    return result

def public_dns_has_no_route(pid):
    # Independently inspect route selection inside the application namespace.
    # An unexpected error is not proof of isolation.
    r = cmd(["nsenter", "--target", str(pid), "--net", "ip", "-j", "-4",
             "route", "get", DNS[0]], check=False)
    if r.returncode == 0:
        return False
    return r.returncode == 2 and r.stderr.strip() == "RTNETLINK answers: Network is unreachable"

def probe(cid, v, amazon=False):
    source = (ROOT / "probe.mjs").read_text()
    r = cmd(DOCKER + ["exec", "-i", cid, "node", "--input-type=module", "-",
          v["proxy"], v["gateway"], "amazon" if amazon else "offline"], data=source,
          timeout=90, check=False)
    # Strictly filter output, including failed probes. Never print raw stderr.
    # Require the full ordered result list, not just a successful exit code.
    ids = ("PROXY_UNKNOWN", "PROXY_PUBLIC_IP", "PROXY_GATEWAY_IP", "PROXY_LOOPBACK",
           "PROXY_WRONG_PORT", "PROXY_SUFFIX_TRICK", "PROXY_IPV6_LITERAL",
           "PROXY_PLAIN_HTTP", "DIRECT_PUBLIC", "DIRECT_GATEWAY",
           "DIRECT_DOCKER_DNS_TCP", "DIRECT_PUBLIC_DNS_TCP", "DIRECT_IPV6",
           "DIRECT_DOCKER_DNS_UDP", "DIRECT_PUBLIC_DNS_UDP")
    results = []
    summaries = []
    for line in r.stdout.splitlines():
        match = re.fullmatch(r"PROBE ([A-Z0-9_]+) (PASS|FAIL) ([A-Z0-9_]{1,64})", line)
        if match and match[1] in (*ids, "AMAZON_TLS"):
            results.append((match[1], match[2]))
            note(line)
        elif re.fullmatch(r"PROBE_SUMMARY (?:PASS|FAIL) [0-9]{1,3}", line):
            summaries.append(line)
            note(line)
    expected = (*ids, "AMAZON_TLS") if amazon else ids
    if (r.returncode or tuple(i for i, status in results) != expected
            or any(status != "PASS" for i, status in results)
            or summaries != ["PROBE_SUMMARY PASS 0"]):
        raise RuntimeError("Isolation probes failed or incomplete")


def verify_project_absent():
    if project_containers() or project_networks():
        raise RuntimeError("Project cleanup incomplete")
    if any(x["ifname"] in (PRIVATE_BR, OUTBOUND_BR)
           for x in js(["ip", "-j", "link", "show"])):
        raise RuntimeError("Project bridge cleanup incomplete")


def stop_project(env):
    try:
        compose(env, ["down", "--timeout", "5"], timeout=45)
        verify_project_absent()
    except Exception:
        # Best effort to stop only this project's remaining containers.
        # Do not delete the guard or pretend cleanup succeeded on failure.
        try:
            remaining = project_containers()
            if remaining:
                cmd(DOCKER + ["stop", "--time", "5", *remaining], timeout=30)
        except Exception:
            pass
        raise RuntimeError("Project cleanup incomplete; guard retained; inspect manually") from None


def reap_client(process):
    if process is None:
        return
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def main():
    global cleaning
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run", "check"))
    parser.add_argument("--amazon", action="store_true",
                        help="also test unauthenticated HTTPS to one allowed Amazon host")
    parser.add_argument("--diagnostics", action="store_true",
                        help="synthetic check only: show bounded startup diagnostics on failure")
    parser.add_argument("--lifecycle", choices=("mcp", "stuck"),
                        help="synthetic check only: run stdio lifecycle acceptance")
    args = parser.parse_args()
    if args.lifecycle and (args.mode != "check" or args.amazon):
        parser.error("--lifecycle is restricted to synthetic offline check mode")
    if args.diagnostics and args.mode != "check":
        parser.error("--diagnostics is restricted to synthetic check mode")
    if os.geteuid() != 0:
        raise RuntimeError("Run as root on the trusted Docker host")
    for directory in (ROOT, CONFIG, STACK):
        trusted_directory(directory)
        st = directory.stat()
        if st.st_gid != 0 or stat.S_IMODE(st.st_mode) != 0o700:
            raise RuntimeError("Manager, configuration and stack directories must be root:root mode 0700")
    for name in ("run.py", "policy.py", "supervisor.py", "probe.mjs", "readiness.mjs"):
        trusted_file(ROOT / name)
    for name in ("AlexaEgress.yml", "squid.conf.template", "allowed-domains.txt"):
        trusted_file(STACK / name)
    trusted_file(CONFIG / ".env", private=True)
    trusted_directory(STATE.parent)
    STATE.mkdir(mode=0o700, exist_ok=True)
    trusted_directory(STATE)
    if STATE.stat().st_gid != 0 or stat.S_IMODE(STATE.stat().st_mode) != 0o700:
        raise RuntimeError("Unsafe runtime state directory")
    with contextlib.ExitStack() as stack:
        fd = os.open(STATE / "session.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        stack.callback(os.close, fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("EGRESS_SESSION_BUSY") from None
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
        host_installed = False
        attempted_up = False
        squid_process = None
        mcp_process = None
        startup_log = stack.enter_context(tempfile.TemporaryFile(mode="w+b")) if args.diagnostics else None

        def mark_host_applied():
            nonlocal host_installed
            host_installed = True

        try:
            # Config files are readable only inside the explicit read-only mount.
            config = temp / "config"
            config.mkdir(mode=0o755)
            domains = validate_domains((STACK / "allowed-domains.txt").read_text())
            (config / "allowed-domains.txt").write_text("\n".join(domains) + "\n")
            squid = (STACK / "squid.conf.template").read_text()
            squid = squid.replace("@CLIENT_IP@", v["app"]).replace("@PROXY_IP@", v["proxy"])
            squid = squid.replace("@BLOCKED_IPV4@", " ".join(str(n) for n in ipaddress.collapse_addresses(ipaddress.IPv4Network(x) for x in (*BLOCKED, *extra))))
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
            # Parse before creating any resources; no override/autoloaded Compose.
            note("STAGE: validate Compose and install host policy")
            compose(env, ["config", "--quiet"])
            install_nft(host_policy(v, extra), on_applied=mark_host_applied)
            attempted_up = True
            compose(env, ["up", "-d", "--no-build", "--pull", "never"], timeout=90)
            note("STAGE: inspect inert containers and networks")
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
            note("STAGE: install namespace policies")
            for pid, is_proxy in ((app_pid, False), (proxy_pid, True)):
                install_nft(namespace_policy(v, is_proxy, extra),
                            ["nsenter", "--target", str(pid), "--net"])
            # Parse and start Squid only after all guard rules have been installed.
            note("STAGE: parse and launch Squid")
            squid_cmd = ["/usr/sbin/squid", "-f", "/etc/alexa-egress/squid.conf"]
            cmd(DOCKER + ["exec", proxy, *squid_cmd, "-k", "parse"])
            # Keep the exec client attached to the foreground Squid process.
            # Detached exec previously hid startup exit status entirely.
            squid_process = subprocess.Popen(
                DOCKER + ["exec", proxy, *squid_cmd, "-N", "-d", "1"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=startup_log if startup_log is not None else subprocess.DEVNULL,
                env=ENV)
            readiness = (ROOT / "readiness.mjs").read_text()
            last = "NOT_TESTED"
            try:
                for attempt in range(20):
                    if squid_process.poll() is not None:
                        raise RuntimeError("Squid exited before readiness")
                    try:
                        result = cmd(DOCKER + ["exec", "-i", app, "node", "--input-type=module", "-", v["proxy"]],
                                     data=readiness, timeout=4, check=False)
                        value = result.stdout.strip()
                        last = value if re.fullmatch(r"(?:HTTP_[1-5][0-9]{2}|SOCKET_[A-Z0-9_]+|TIMEOUT|CLOSED|INVALID)", value) else "PROBE_EXEC_ERROR"
                        if result.returncode == 0 and last == "HTTP_403":
                            note("PASS: proxy readiness denied unknown destination")
                            break
                        # Any positive or unexpected HTTP response is a policy failure,
                        # not an invitation to retry or loosen the ACL.
                        if last.startswith("HTTP_"):
                            raise RuntimeError("Unexpected readiness response: " + last)
                    except subprocess.TimeoutExpired:
                        last = "EXEC_TIMEOUT"
                    time.sleep(0.25)
                else:
                    raise RuntimeError("Proxy readiness failed: " + last)
            except RuntimeError:
                note("READINESS_LAST: " + last)
                note("SQUID_EXEC_EXIT: " + str(squid_process.poll()))
                if args.diagnostics:
                    listeners = cmd(["nsenter", "--target", str(proxy_pid), "--net", "ss", "-H", "-ltn"], check=False)
                    note("SQUID_LISTENER_3128: " + ("YES" if re.search(r":3128\b", listeners.stdout) else "NO"))
                    startup_log.seek(0, os.SEEK_END)
                    startup_log.seek(max(0, startup_log.tell() - 8192))
                    note("=== SYNTHETIC SQUID STARTUP DIAGNOSTICS ===")
                    note(startup_log.read(8192).decode("utf-8", errors="replace"))
                    note("=== END DIAGNOSTICS ===")
                raise
            note("STAGE: isolation probes")
            before_dns = dns_counters(app_pid)
            probe(app, v, args.amazon)
            after_dns = dns_counters(app_pid)
            no_route = public_dns_has_no_route(app_pid)
            evidence = dns_denial_evidence(before_dns, after_dns, no_route)
            for name, passed in evidence.items():
                note(name + (": PASS" if passed else ": FAIL"))
            note("DNS_DOCKER_DROPS: " + str(after_dns["dns_docker_udp"] - before_dns["dns_docker_udp"]))
            note("DNS_PUBLIC_DROPS: " + str(after_dns["dns_public_udp"] - before_dns["dns_public_udp"]))
            note("DNS_PUBLIC_NO_ROUTE: " + ("YES" if no_route else "NO"))
            if not all(evidence.values()):
                raise RuntimeError("DNS guard evidence missing")
            if args.mode == "run" or args.lifecycle:
                check = cmd(DOCKER + ["exec", app, "node", "-p",
                    "process.versions.node"]).stdout.strip()
                if tuple(map(int, check.split(".")[:2])) < (22, 21):
                    raise RuntimeError("Node lacks native environment proxy support")
                if squid_process.poll() is not None:
                    raise RuntimeError("EGRESS_PROXY_EXITED")
                command = ["node", "dist/index.js"]
                if args.lifecycle == "stuck":
                    # Fixed offline fixture: consume stdin but intentionally
                    # stay alive after EOF. Never load a real auth directory.
                    command = ["node", "-e",
                        "process.stdin.resume(); setInterval(() => {}, 1000);"]
                mcp_process = subprocess.Popen(
                    DOCKER + ["exec", "-i", app, *command],
                    stdin=subprocess.PIPE, stdout=None, stderr=subprocess.DEVNULL,
                    bufsize=0, env=ENV)
                note("Guarded MCP session started; stdout reserved for MCP.")
                supervise(mcp_process, squid_process)
        finally:
            # Defer repeated termination signals during bounded cleanup.
            # Remove the host guard only after verified project removal.
            cleaning = True
            try:
                try:
                    if attempted_up:
                        stop_project(env)
                    elif host_installed:
                        verify_project_absent()
                finally:
                    try:
                        reap_client(mcp_process)
                    finally:
                        reap_client(squid_process)
                if host_installed:
                    cmd(["nft", "delete", "table", "inet", TABLE])
                    if ("inet", TABLE) in nft_tables():
                        raise RuntimeError("Guard table cleanup incomplete")
                elif ("inet", TABLE) in nft_tables():
                    raise RuntimeError("Uncertain guard ownership; inspect manually")
                shutil.rmtree(temp)
                note("EGRESS_CLEANUP: PASS")
            finally:
                cleaning = False
        if interrupted_signal is not None:
            raise KeyboardInterrupt
        note("GUARDED_SESSION: PASS")

if __name__ == "__main__":
    def interrupted(signum, frame):
        global interrupted_signal
        if interrupted_signal is None:
            interrupted_signal = signum
        if not cleaning:
            raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        main()
    except KeyboardInterrupt:
        note("Guarded session interrupted; inspect cleanup if necessary.")
        sys.exit(128 + (interrupted_signal or signal.SIGINT))
    except Exception as exc:
        # Never output subprocess stderr, config values or credential details.
        note("GUARDED_SESSION: FAIL (" + type(exc).__name__ + ")")
        if isinstance(exc, (ValueError, RuntimeError)):
            note(str(exc))
        sys.exit(1)
