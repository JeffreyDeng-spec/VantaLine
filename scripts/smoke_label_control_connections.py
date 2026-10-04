"""Control-only connection options and configuration; no production database."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_inspection_service.runtime.control_connections import control_connector, create_control_factory
from local_inspection_service.runtime.label_identity import RuntimeUnavailable


class ControlConnections(unittest.TestCase):
    def test_connection_failure_detection_does_not_depend_on_dsn_defaults(self):
        calls = []
        connection = object()
        def connect(*args, **kwargs):
            calls.append((args, kwargs))
            return connection
        with patch.dict(sys.modules, {"psycopg": SimpleNamespace(connect=connect)}):
            self.assertIs(control_connector("synthetic dsn"), connection)
        self.assertEqual(calls, [(("synthetic dsn",), dict(connect_timeout=2, tcp_user_timeout=2000,
            keepalives=1, keepalives_idle=1, keepalives_interval=1, keepalives_count=2))])

    def test_explicit_postgres_selection_is_required_before_connect(self):
        for env in ({}, {"VANTALINE_DATA_STORE": "json", "DATABASE_URL": "fixture"},
                    {"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": ""}):
            with self.subTest(env=env), self.assertRaises(RuntimeUnavailable):
                create_control_factory(env)

    def test_control_factory_owns_separate_connection_and_captured_configuration(self):
        source = {"VANTALINE_DATA_STORE": "postgres", "DATABASE_URL": "synthetic-old"}
        with patch("local_inspection_service.runtime.control_connections.control_connector") as connect:
            connect.side_effect = [SimpleNamespace(closed=False, close=lambda: None) for _ in range(2)]
            first, second = create_control_factory(source), create_control_factory(source)
            source["DATABASE_URL"] = "synthetic-new"
            self.assertIsNot(first.selection().repository.connection, second.selection().repository.connection)
            self.assertEqual([call.args for call in connect.call_args_list], [("synthetic-old",), ("synthetic-old",)])
            first.clear()
            second.clear()


if __name__ == "__main__":
    unittest.main()
