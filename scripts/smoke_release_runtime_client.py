"""Linux Unix-socket client tests with synthetic peers only."""
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest

from release_runtime_client import request
from release_runtime_contract import ContractError


@unittest.skipUnless(hasattr(socket, 'SO_PEERCRED'), 'Linux peer credentials required')
class ClientContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vantaline-control-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.settimeout(1)
        self.path = self.root / 'web-control.sock'
        self.listener.bind(str(self.path))
        self.path.chmod(0o600)
        self.listener.listen()
        self.addCleanup(self.listener.close)
        self.errors = []
        self.threads = []
        self.addCleanup(self.join)

    def join(self):
        self.listener.close()
        for thread in self.threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(self.errors, [])

    def serve(self, reply=b'{"ok":true}\n', delay=0):
        def run():
            try:
                connection, _ = self.listener.accept()
                with connection:
                    connection.settimeout(1)
                    raw = bytearray()
                    while not raw.endswith(b'\n'):
                        part = connection.recv(1024)
                        if not part:
                            return
                        raw.extend(part)
                    message = json.loads(raw)
                    self.assertEqual(message, {'schema': 1, 'command': 'status', 'revision': 'a' * 32})
                    if delay:
                        for byte in reply:
                            time.sleep(delay)
                            connection.sendall(bytes([byte]))
                    else:
                        connection.sendall(reply)
            except (BrokenPipeError, ConnectionResetError):
                pass  # Expected when a bounded client rejects the response.
            except Exception as error:
                self.errors.append(type(error).__name__)
        thread = threading.Thread(target=run, daemon=True)
        self.threads.append(thread)
        thread.start()

    def call(self, **options):
        args = dict(uid=os.getuid(), pid=os.getpid(), directory=self.root, timeout=0.25)
        args.update(options)
        return request('vantaline', 'status', 'a' * 32, **args)

    def test_actual_peer_credentials_and_json(self):
        self.serve()
        self.assertEqual(self.call(), {'ok': True})

    def test_wrong_pid_is_rejected_before_sending_command(self):
        self.serve()
        with self.assertRaisesRegex(ContractError, 'peer mismatch'):
            self.call(pid=os.getpid() + 1)

    def test_world_readable_socket_rejected(self):
        self.path.chmod(0o666)
        with self.assertRaises(ContractError):
            self.call()

    def test_response_is_bounded(self):
        self.serve(b'x' * 17000 + b'\n')
        with self.assertRaises(ContractError):
            self.call()

    def test_slow_peer_cannot_extend_total_deadline(self):
        self.serve(delay=0.04)
        start = time.monotonic()
        with self.assertRaises(ContractError):
            self.call(timeout=0.15)
        self.assertLess(time.monotonic() - start, 0.35)

    def test_bad_json_and_untrusted_message_are_not_logged(self):
        self.serve(b'synthetic-secret-customer-content\n')
        with self.assertRaises(ContractError) as error:
            self.call()
        self.assertNotIn('synthetic-secret', str(error.exception))


if __name__ == '__main__':
    unittest.main()
