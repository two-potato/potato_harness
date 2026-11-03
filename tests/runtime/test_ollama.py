import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch


class OllamaTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.status = 200
        self.declared_length = None
        self.body = json.dumps({'done': True, 'message': {'role': 'assistant', 'content': '{"operator":"multiply"}'}}).encode()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                owner.requests.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                self.send_response(owner.status)
                if owner.status == 302:
                    self.send_header('Location', 'http://example.com/secret')
                if owner.declared_length is not None:
                    self.send_header("Content-Length", str(owner.declared_length))
                self.end_headers()
                self.wfile.write(owner.body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.endpoint = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def propose(self, **kwargs):
        from harness.adapters.ollama import propose
        return propose('installed-model', endpoint=self.endpoint, **kwargs)

    def test_request_and_success(self):
        with patch.dict('os.environ', {'http_proxy': 'http://example.com:9', 'HTTP_PROXY': 'http://example.com:9'}):
            self.assertEqual(self.propose(), {'operator': 'multiply'})
        path, request = self.requests[0]
        self.assertEqual(path, '/api/chat')
        self.assertEqual(request['model'], 'installed-model')
        self.assertIs(request['stream'], False)
        self.assertEqual(request['format'], {'type': 'object', 'properties': {'operator': {'type': 'string', 'enum': ['multiply', 'add']}}, 'required': ['operator'], 'additionalProperties': False})
        self.assertIn('1250', str(request['messages']))
        self.assertIn('3750', str(request['messages']))

    def test_malformed_responses(self):
        for value in [None, {}, {'done': False}, {'done': 1, 'message': {'role': 'assistant', 'content': '{"operator":"add"}'}}, {'done': True, 'message': {'role': 'user', 'content': '{"operator":"add"}'}}, {'done': True, 'message': {}}, {'done': True, 'message': {'role': 'assistant', 'content': '{}'}}, {'done': True, 'message': {'role': 'assistant', 'content': '{"operator":"multiply","code":"SECRET"}'}}, {'done': True, 'message': {'role': 'assistant', 'content': []}}]:
            self.body = json.dumps(value).encode()
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                self.propose()
            self.assertNotIn('SECRET', str(caught.exception))
        self.body = b'{incomplete'
        with self.assertRaises(ValueError):
            self.propose()

    def test_oversized_response(self):
        self.body = b' ' * (65536 + 1)
        with self.assertRaises(ValueError):
            self.propose()

    def test_redirect_is_not_followed(self):
        self.status = 302
        with self.assertRaises(ValueError):
            self.propose()
        self.assertEqual(len(self.requests), 1)

    def test_rejects_endpoints_before_network(self):
        from harness.adapters.ollama import propose
        for endpoint in ['https://example.com', 'http://127.0.0.2', 'http://localhost.evil', 'http://user@localhost', 'http://localhost/', 'http://localhost/x', 'http://localhost?x', 'http://localhost#x', 'ftp://localhost', 'http://2130706433', 'http://localhost:bad', 'http://localhost\\@example.com', 'http://LOCALHOST', 'http://localhost\n']:
            with self.subTest(endpoint=endpoint), patch('urllib.request.OpenerDirector.open') as opened, self.assertRaises(ValueError):
                propose('installed-model', endpoint=endpoint)
            opened.assert_not_called()

    def test_rejects_bad_model_and_timeout(self):
        for kwargs in [{'model': ''}, {'model': None}, {'model': 'm', 'timeout': 0}, {'model': 'm', 'timeout': float('nan')}]:
            from harness.adapters.ollama import propose
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                propose(endpoint=self.endpoint, **kwargs)
        self.assertFalse(self.requests)

    def test_truncated_transport(self):
        self.declared_length = len(self.body) + 10
        with self.assertRaises(ValueError):
            self.propose()

    def test_transport_errors_are_clean(self):
        import http.client
        for error in [TimeoutError('SECRET'), ConnectionError('SECRET'), http.client.IncompleteRead(b'SECRET')]:
            with self.subTest(error=type(error)), patch('urllib.request.OpenerDirector.open', side_effect=error):
                with self.assertRaises(ValueError) as caught:
                    self.propose()
                self.assertNotIn('SECRET', str(caught.exception))
