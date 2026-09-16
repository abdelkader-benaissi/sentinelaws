"""SentinelAWS demonstration API with an explicit PostgreSQL readiness check."""

from __future__ import annotations

import json
import logging
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Protocol

LOG = logging.getLogger("sentinelaws")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))


class Connection(Protocol):
    """Subset of a PostgreSQL connection used by the health probe."""

    def __enter__(self) -> "Connection": ...
    def __exit__(self, *args: Any) -> None: ...
    def execute(self, query: str) -> Any: ...


class DatabaseProbe:
    """Resolve RDS credentials and perform a small, read-only query."""

    def __init__(
        self,
        secret_loader: Callable[[str], dict[str, Any]],
        connector: Callable[..., Connection],
        *,
        secret_arn: str,
        host: str,
        database: str,
        port: int = 5432,
    ) -> None:
        self._secret_loader = secret_loader
        self._connector = connector
        self._secret_arn = secret_arn
        self._host = host
        self._database = database
        self._port = port

    def check(self) -> dict[str, str]:
        secret = self._secret_loader(self._secret_arn)
        username = secret.get("username")
        password = secret.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError("RDS secret is missing username or password")

        with self._connector(
            host=self._host,
            port=self._port,
            dbname=self._database,
            user=username,
            password=password,
            connect_timeout=3,
            sslmode="require",
        ) as connection:
            row = connection.execute("SELECT current_database(), current_user").fetchone()

        return {"status": "connected", "database": str(row[0]), "user": str(row[1])}


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, body: dict[str, Any]) -> None:
    payload = json.dumps(body, separators=(",", ":")).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.end_headers()
    handler.wfile.write(payload)


def make_handler(probe: DatabaseProbe, environment: str) -> type[BaseHTTPRequestHandler]:
    """Build an HTTP handler with dependencies supplied by the caller."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            if self.path == "/health":
                _json_response(self, HTTPStatus.OK, {"status": "healthy"})
                return

            if self.path in {"/", "/ready"}:
                try:
                    database = probe.check()
                except Exception as error:  # keep credentials and driver details out of logs/responses
                    LOG.error("Database readiness check failed (%s)", type(error).__name__)
                    _json_response(
                        self,
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {"status": "degraded", "database": "unavailable"},
                    )
                    return

                _json_response(
                    self,
                    HTTPStatus.OK,
                    {
                        "service": "SentinelAWS",
                        "environment": environment,
                        "status": "ready",
                        "database": database,
                    },
                )
                return

            _json_response(self, HTTPStatus.NOT_FOUND, {"status": "not_found"})

        def log_message(self, fmt: str, *args: Any) -> None:
            LOG.info(
                json.dumps(
                    {"client": self.client_address[0], "message": fmt % args},
                    separators=(",", ":"),
                )
            )

    return Handler


def _secret_loader(secret_arn: str) -> dict[str, Any]:
    import boto3

    value = boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)
    return json.loads(value["SecretString"])


def main() -> None:
    import psycopg

    probe = DatabaseProbe(
        _secret_loader,
        psycopg.connect,
        secret_arn=os.environ["DB_SECRET_ARN"],
        host=os.environ["DB_HOST"],
        database=os.getenv("DB_NAME", "sentineldb"),
    )
    handler = make_handler(probe, os.getenv("ENVIRONMENT", "dev"))
    ThreadingHTTPServer(("0.0.0.0", 8080), handler).serve_forever()


if __name__ == "__main__":
    main()
