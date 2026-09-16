import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock


def load_module():
    path = Path(__file__).parents[1] / "app/server.py"
    spec = importlib.util.spec_from_file_location("sentinelaws_app", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DatabaseProbeTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def test_uses_secret_and_tls_for_database_query(self):
        loader = MagicMock(return_value={"username": "sentinel", "password": "secret"})
        cursor = MagicMock()
        cursor.fetchone.return_value = ("sentineldb", "sentinel")
        connection = MagicMock()
        connection.__enter__.return_value.execute.return_value = cursor
        connector = MagicMock(return_value=connection)

        probe = self.module.DatabaseProbe(
            loader,
            connector,
            secret_arn="arn:aws:secretsmanager:us-east-1:123456789012:secret:rds",
            host="database.internal",
            database="sentineldb",
        )

        self.assertEqual(
            probe.check(),
            {"status": "connected", "database": "sentineldb", "user": "sentinel"},
        )
        connector.assert_called_once_with(
            host="database.internal",
            port=5432,
            dbname="sentineldb",
            user="sentinel",
            password="secret",
            connect_timeout=3,
            sslmode="require",
        )

    def test_rejects_incomplete_secret(self):
        probe = self.module.DatabaseProbe(
            lambda _arn: {"username": "sentinel"},
            MagicMock(),
            secret_arn="secret",
            host="database.internal",
            database="sentineldb",
        )
        with self.assertRaisesRegex(ValueError, "missing username or password"):
            probe.check()


class HttpHandlerTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()

    def _request(self, probe, path):
        server = ThreadingHTTPServer(("127.0.0.1", 0), self.module.make_handler(probe, "test"))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}{path}"
            try:
                response = urllib.request.urlopen(url, timeout=2)
            except urllib.error.HTTPError as error:
                response = error
            return response.status, json.loads(response.read())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_health_does_not_query_database(self):
        probe = MagicMock()
        status, body = self._request(probe, "/health")
        self.assertEqual(status, 200)
        self.assertEqual(body, {"status": "healthy"})
        probe.check.assert_not_called()

    def test_ready_reports_database_failure_without_leaking_error(self):
        probe = MagicMock()
        probe.check.side_effect = RuntimeError("password=do-not-leak")
        status, body = self._request(probe, "/ready")
        self.assertEqual(status, 503)
        self.assertEqual(body, {"status": "degraded", "database": "unavailable"})
        self.assertNotIn("password", json.dumps(body))
