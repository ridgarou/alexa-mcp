"""Root-only integration harness for the disposable CI runner.

No account data. Never run this fault-injection harness against live sessions.
"""
import json
import os
import select
import signal
import subprocess
import tempfile
import time

MANAGER = "/usr/local/sbin/alexa-egress-manager"
DOCKER = ["docker", "--host", "unix:///var/run/docker.sock"]
PROJECT = "label=com.docker.compose.project=alexa-egress"


def command(args):
    return subprocess.check_output(args, text=True, timeout=15).strip()


def clean():
    assert not command(DOCKER + ["ps", "-aq", "--filter", PROJECT])
    assert not command(DOCKER + ["network", "ls", "-q", "--filter", PROJECT])
    tables = json.loads(command(["nft", "-j", "list", "tables"]))["nftables"]
    assert not any(t.get("table", {}).get("family") == "inet" and
                   t["table"]["name"] == "alexa_guard" for t in tables)
    links = json.loads(command(["ip", "-j", "link", "show"]))
    assert not any(x["ifname"] in ("br-alexa-priv", "br-alexa-egress") for x in links)


def trial(mode, action, expected, marker=None):
    clean()
    with tempfile.TemporaryFile() as logs:
        proc = subprocess.Popen([MANAGER, "check", "--lifecycle", mode],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=logs, bufsize=0)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                # Read a separate file descriptor position using pread.
                data = os.pread(logs.fileno(), 65536, 0)
                if b"Guarded MCP session started" in data:
                    break
                if proc.poll() is not None:
                    raise RuntimeError("Synthetic manager exited during setup")
                time.sleep(0.1)
            else:
                raise RuntimeError("Synthetic startup timeout")

            if action == "handshake":
                msg = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                  "clientInfo": {"name": "offline-lifecycle", "version": "1"}}}
                proc.stdin.write(json.dumps(msg).encode() + b"\n")
                # Bound line read without allowing an unbounded partial line.
                response = bytearray()
                deadline = time.monotonic() + 15
                while b"\n" not in response:
                    wait = deadline - time.monotonic()
                    if wait <= 0 or not select.select([proc.stdout], [], [], wait)[0]:
                        raise RuntimeError("Synthetic MCP handshake timeout")
                    chunk = os.read(proc.stdout.fileno(), 8192)
                    if not chunk or len(response) + len(chunk) > 65536:
                        raise RuntimeError("Invalid synthetic MCP response")
                    response.extend(chunk)
                reply = json.loads(response.split(b"\n", 1)[0])
                assert reply["id"] == 1
                assert reply["result"]["serverInfo"]["version"] == "1.0.1-rc.1"
            elif action == "proxy":
                cid = command(DOCKER + ["ps", "-q", "--filter", PROJECT,
                    "--filter", "label=com.docker.compose.service=AlexaEgress"])
                assert len(cid.splitlines()) == 1 and cid
                command(DOCKER + ["stop", "--time", "2", cid])
            elif action == "signal":
                second = subprocess.run([MANAGER, "check"], stdin=subprocess.DEVNULL,
                    capture_output=True, timeout=15)
                assert second.returncode != 0 and b"EGRESS_SESSION_BUSY" in second.stderr
                proc.send_signal(signal.SIGTERM)
            if action not in ("proxy", "signal"):
                proc.stdin.close()
            assert proc.wait(timeout=65) == expected
            data = os.pread(logs.fileno(), 65536, 0)
            assert b"EGRESS_CLEANUP: PASS" in data
            if marker:
                assert marker.encode() in data
            assert (b"GUARDED_SESSION: PASS" in data) == (expected == 0)
            clean()
            print("LIFECYCLE_" + action.upper() + ": PASS", flush=True)
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=65)
                except subprocess.TimeoutExpired:
                    raise RuntimeError("Manual cleanup required; refusing further tests")
            if not proc.stdin.closed:
                proc.stdin.close()
            proc.stdout.close()


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("Run only as root on a disposable test host")
    trial("mcp", "handshake", 0)
    trial("stuck", "eof", 1, "MCP_EOF_TIMEOUT")
    trial("stuck", "proxy", 1, "EGRESS_PROXY_EXITED")
    trial("stuck", "signal", 143, "Guarded session interrupted")
