#!/usr/bin/env python3
"""Fresh installation only; no Docker, firewall or existing configuration changes.

Run from a reviewed, root-controlled staging directory using python3 -I -B.
"""
import os
from pathlib import Path
import stat
import sys

SOURCE = Path(__file__).absolute().parent
MANAGER = Path("/opt/alexa-egress-manager")
CONFIG = Path("/etc/alexa-egress-manager")
STACK = Path("/opt/containers-data/AlexaEgress")
COMMAND = Path("/usr/local/sbin/alexa-egress-manager")
STATE = Path("/run/alexa-egress-manager")
LAYOUT = {
    MANAGER: {"run.py": "run.py", "policy.py": "policy.py",
              "probe.mjs": "probe.mjs", "readiness.mjs": "readiness.mjs"},
    CONFIG: {".env.example": ".env.example"},
    STACK: {"Dockerfile": "Dockerfile", ".dockerignore": ".dockerignore",
            "compose.yml": "AlexaEgress.yml", "squid.conf.template": "squid.conf.template",
            "allowed-domains.txt": "allowed-domains.txt",
            "README.md": "README.md", "THREAT_MODEL.md": "THREAT_MODEL.md"},
}

def trusted_directory(path):
    for directory in (path, *path.parents):
        s = directory.lstat()
        if not stat.S_ISDIR(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
            raise RuntimeError("Untrusted directory or ancestor: " + str(directory))

def source_bytes(name):
    path = SOURCE / name
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid != 0 or s.st_mode & 0o022:
        raise RuntimeError("Untrusted source: " + name)
    return path.read_bytes()

def absent(path):
    if os.path.lexists(path):
        raise RuntimeError("Refusing to overwrite: " + str(path))

def main():
    if os.geteuid() != 0 or len(sys.argv) != 1:
        raise RuntimeError("Run as root without arguments")
    os.umask(0o077)
    trusted_directory(SOURCE)
    # Preflight all destinations and sources before writing anything.
    for path in (*LAYOUT, COMMAND, STATE, Path("/opt/alexa-egress"), Path("/run/alexa-egress")):
        absent(path)
    for parent in (MANAGER.parent, CONFIG.parent, COMMAND.parent, STATE.parent, STACK.parent.parent):
        trusted_directory(parent)
    create_stack_parent = not os.path.lexists(STACK.parent)
    if not create_stack_parent:
        trusted_directory(STACK.parent)
    payloads = [(directory / destination, source_bytes(source), 0o600 if directory == CONFIG else 0o644)
                for directory, mapping in LAYOUT.items() for source, destination in mapping.items()]
    payloads.append((COMMAND, source_bytes("alexa-egress-manager"), 0o755))
    created_dirs, created_files = [], []
    try:
        if create_stack_parent:
            STACK.parent.mkdir(mode=0o700)
            created_dirs.append(STACK.parent)
            os.chown(STACK.parent, 0, 0)
            os.chmod(STACK.parent, 0o700)
        for directory in LAYOUT:
            directory.mkdir(mode=0o700)
            created_dirs.append(directory)
            # mkdir can inherit group and setgid from an existing parent.
            # Normalize only the directory we just created, never its parent.
            os.chown(directory, 0, 0)
            os.chmod(directory, 0o700)
        for path, data, mode in payloads:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
            created_files.append(path)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fchown(stream.fileno(), 0, 0)
                os.fchmod(stream.fileno(), mode)
        print("EGRESS_MANAGER_INSTALL: PASS")
        print("Review and create /etc/alexa-egress-manager/.env before running checks.")
    except BaseException:
        for path in reversed(created_files):
            path.unlink()
        for directory in reversed(created_dirs):
            directory.rmdir()
        raise

if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as exc:
        print("EGRESS_MANAGER_INSTALL: FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
