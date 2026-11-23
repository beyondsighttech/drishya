import json
import os
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import tests
from drishya.engine import local_json, Cancelled, InferenceError


class EngineTests(unittest.TestCase):
    def setUp(self):
        owner = self
        self.headers_seen = None
        self.delay = 0
        self.status = 200

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                owner.headers_seen = dict(self.headers)
                self.rfile.read(int(self.headers["Content-Length"]))
                time.sleep(owner.delay)
                self.send_response(owner.status)
                self.end_headers()
                try:
                    self.wfile.write(json.dumps({"ok": True}).encode())
                except OSError:
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_local_request_authentication(self):
        result = local_json(self.server.server_port, "/test", "secret", {}, threading.Event(), 2)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(self.headers_seen["Authorization"], "Bearer secret")

    def test_timeout_is_bounded(self):
        self.delay = 1
        start = time.monotonic()
        with self.assertRaises(InferenceError):
            local_json(self.server.server_port, "/test", "secret", {}, threading.Event(), .1)
        self.assertLess(time.monotonic() - start, .5)

    def test_cancellation_during_request(self):
        self.delay = 1
        event = threading.Event()
        timer = threading.Timer(.1, event.set)
        timer.start()
        self.addCleanup(timer.cancel)
        start = time.monotonic()
        with self.assertRaises(Cancelled):
            local_json(self.server.server_port, "/test", "secret", {}, event, 2)
        self.assertLess(time.monotonic() - start, .5)

    def test_http_error_has_clear_message(self):
        self.status = 503
        with self.assertRaises(InferenceError):
            local_json(self.server.server_port, "/test", "secret", {}, threading.Event(), 2)

    def test_peer_ownership_checked_before_key_or_image_is_sent(self):
        with self.assertRaises(InferenceError):
            local_json(self.server.server_port, "/test", "secret", {"image": "private"},
                       threading.Event(), 2, owned_pid=os.getpid() + 1)
        self.assertIsNone(self.headers_seen)

    def test_actual_tcp_peer_owner_can_receive_request(self):
        result = local_json(self.server.server_port, "/test", "secret", {},
                            threading.Event(), 2, owned_pid=os.getpid())
        self.assertEqual(result, {"ok": True})

    def test_checked_socket_cannot_reconnect_without_ownership_check(self):
        import http.client
        import drishya.engine as engine
        from unittest.mock import patch
        real_connection = http.client.HTTPConnection
        connections = []
        def connection(*args, **kwargs):
            instance = real_connection(*args, **kwargs)
            connections.append(instance)
            return instance
        def peer_checked_then_closed(sock, pid):
            connections[-1].close()
            return True
        with patch.object(engine.http.client, "HTTPConnection", connection), patch.object(engine, "peer_is_owned", peer_checked_then_closed):
            with self.assertRaises(InferenceError):
                local_json(self.server.server_port, "/test", "secret", {"image": "private"},
                           threading.Event(), 2, owned_pid=os.getpid())
        self.assertIsNone(self.headers_seen)
