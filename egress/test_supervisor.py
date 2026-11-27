import os
import subprocess
import sys
import time
import unittest

from supervisor import supervise


class SupervisorTests(unittest.TestCase):
    def scenario(self, source_data, program, expected=None, proxy_seconds=30):
        read, write = os.pipe()
        child = subprocess.Popen([sys.executable, "-c", program],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, bufsize=0)
        proxy = subprocess.Popen([sys.executable, "-c",
                                  f"import time; time.sleep({proxy_seconds})"])
        try:
            os.write(write, source_data)
            os.close(write)
            write = None
            start = time.monotonic()
            if expected:
                with self.assertRaisesRegex(RuntimeError, expected):
                    supervise(child, proxy, source=read, sink=None, eof_timeout=0.8)
            else:
                supervise(child, proxy, source=read, sink=None, eof_timeout=2)
                self.assertEqual(child.returncode, 0)
            self.assertLess(time.monotonic() - start, 4)
            self.assertTrue(child.stdin.closed)
        finally:
            if write is not None:
                os.close(write)
            os.close(read)
            for proc in (child, proxy):
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3)

    def test_exact_input_and_clean_eof(self):
        self.scenario(b"synthetic\n",
            "import sys; sys.exit(0 if sys.stdin.buffer.read() == b'synthetic\\n' else 1)")

    def test_stuck_after_eof(self):
        self.scenario(b"", "import sys,time; sys.stdin.read(); time.sleep(30)",
                      "MCP_EOF_TIMEOUT")

    def test_proxy_death(self):
        self.scenario(b"", "import time; time.sleep(30)", "EGRESS_PROXY_EXITED",
                      proxy_seconds=0.1)

    def test_nonzero_child(self):
        self.scenario(b"", "import sys; sys.stdin.read(); sys.exit(7)",
                      "MCP_PROCESS_FAILED")

    def test_disconnected_output(self):
        r, w = os.pipe()
        out_read, out_write = os.pipe()
        os.close(out_read)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 stdin=subprocess.PIPE, bufsize=0)
        proxy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            with self.assertRaisesRegex(RuntimeError, "MCP_CLIENT_OUTPUT_CLOSED"):
                supervise(child, proxy, source=r, sink=out_write)
        finally:
            os.close(r)
            os.close(w)
            os.close(out_write)
            for proc in (child, proxy):
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3)

    def test_input_open_early_exit(self):
        r, w = os.pipe()
        child = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.PIPE,
                                 bufsize=0)
        proxy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            with self.assertRaisesRegex(RuntimeError, "MCP_EXITED_BEFORE_EOF"):
                supervise(child, proxy, source=r, sink=None, eof_timeout=1)
        finally:
            os.close(r)
            os.close(w)
            for proc in (child, proxy):
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
