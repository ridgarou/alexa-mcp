"""Bounded stdin relay for a guarded, attached Docker exec process.

No MCP parsing, logging, background threads or credential access. The caller
owns the containers and must stop them before removing network guards.
"""
import os
import select
import time

EOF_TIMEOUT = 15.0
POLL_MS = 250
CHUNK = 65536
ERROR = select.POLLERR | select.POLLNVAL


def supervise(child, proxy, source=0, sink=1, eof_timeout=EOF_TIMEOUT):
    if child.stdin is None:
        raise RuntimeError("Missing MCP input pipe")
    target = child.stdin.fileno()
    os.set_blocking(target, False)
    pending = b""
    eof = False
    deadline = None
    closed = False
    try:
        while True:
            if proxy.poll() is not None:
                raise RuntimeError("EGRESS_PROXY_EXITED")
            code = child.poll()
            if code is not None:
                if not closed:
                    raise RuntimeError("MCP_EXITED_BEFORE_EOF")
                if code != 0:
                    raise RuntimeError("MCP_PROCESS_FAILED")
                return

            if deadline is not None and time.monotonic() >= deadline:
                raise RuntimeError("MCP_EOF_TIMEOUT")

            poller = select.poll()
            # Even with buffered input, observe disconnects without allocating
            # additional memory. A pipe HUP can accompany unread data.
            if not eof:
                poller.register(source, 0 if pending else select.POLLIN)
            if pending:
                poller.register(target, select.POLLOUT)
            if sink is not None:
                poller.register(sink, 0)

            for fd, events in poller.poll(POLL_MS):
                if fd == sink:
                    if events & (ERROR | select.POLLHUP):
                        raise RuntimeError("MCP_CLIENT_OUTPUT_CLOSED")
                elif fd == source:
                    if events & ERROR:
                        raise RuntimeError("MCP_CLIENT_INPUT_FAILED")
                    if events & select.POLLHUP and deadline is None:
                        deadline = time.monotonic() + eof_timeout
                    if not pending and events & (select.POLLIN | select.POLLHUP):
                        chunk = os.read(source, CHUNK)
                        if chunk:
                            pending = chunk
                        else:
                            eof = True
                            if deadline is None:
                                deadline = time.monotonic() + eof_timeout
                elif fd == target:
                    if events & (ERROR | select.POLLHUP):
                        raise RuntimeError("MCP_INPUT_PIPE_CLOSED")
                    if events & select.POLLOUT:
                        try:
                            count = os.write(target, pending)
                        except BlockingIOError:
                            continue
                        except BrokenPipeError:
                            raise RuntimeError("MCP_INPUT_PIPE_CLOSED") from None
                        pending = pending[count:]

            if eof and not pending and not closed:
                child.stdin.close()
                closed = True
    finally:
        if not child.stdin.closed:
            child.stdin.close()
