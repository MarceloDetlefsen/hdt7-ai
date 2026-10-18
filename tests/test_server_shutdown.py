import os
import signal
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ServerShutdownTests(unittest.TestCase):
    def test_mcp_sigint_shutdown_has_no_closed_logging_stream(self):
        env = os.environ.copy()
        try:
            port = free_port()
        except PermissionError:
            self.skipTest("el entorno no permite abrir sockets locales")
        env["MCP_PORT"] = str(port)
        process = subprocess.Popen(
            [sys.executable, "mcp_server.py"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            time.sleep(1)
            process.send_signal(signal.SIGINT)
            output, _ = process.communicate(timeout=10)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
        self.assertIn("Application startup complete", output)
        self.assertNotIn("I/O operation on closed file", output)
        self.assertNotIn("Traceback (most recent call last)", output)
        self.assertIn(process.returncode, (0, 130, -signal.SIGINT))


if __name__ == "__main__":
    unittest.main()
