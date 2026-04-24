"""
Tests for :mod:`d10_driver.config.settings`.

Covers:
- Default values when no file and no env vars are present.
- Loading from a YAML string (via a temp file).
- Environment variable overrides.
- Type coercion of env var strings.
"""

from __future__ import annotations

import os
import tempfile
import textwrap
import unittest

from d10_driver.config import settings as settings_module


class TestDefaultSettings(unittest.TestCase):
    def setUp(self):
        # Reset the singleton between tests
        settings_module._settings = None

    def test_default_serial_port(self):
        cfg = settings_module.load_settings(config_path="/nonexistent/config.yaml")
        self.assertEqual(cfg.serial.port, "/dev/ttyUSB0")

    def test_default_baud_rate(self):
        cfg = settings_module.load_settings(config_path="/nonexistent/config.yaml")
        self.assertEqual(cfg.serial.baud_rate, 9600)

    def test_default_database_host(self):
        cfg = settings_module.load_settings(config_path="/nonexistent/config.yaml")
        self.assertEqual(cfg.database.host, "localhost")

    def test_default_auto_commit(self):
        cfg = settings_module.load_settings(config_path="/nonexistent/config.yaml")
        self.assertTrue(cfg.driver.auto_commit)

    def test_get_settings_returns_singleton(self):
        settings_module._settings = None
        a = settings_module.get_settings()
        b = settings_module.get_settings()
        self.assertIs(a, b)


class TestYAMLLoading(unittest.TestCase):
    def setUp(self):
        settings_module._settings = None

    def test_serial_port_from_yaml(self):
        yaml_content = textwrap.dedent("""\
            serial:
              port: /dev/ttyS0
              baud_rate: 19200
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            tmp_path = f.name
        try:
            cfg = settings_module.load_settings(config_path=tmp_path)
            self.assertEqual(cfg.serial.port, "/dev/ttyS0")
            self.assertEqual(cfg.serial.baud_rate, 19200)
        finally:
            os.unlink(tmp_path)
            settings_module._settings = None

    def test_database_host_from_yaml(self):
        yaml_content = textwrap.dedent("""\
            database:
              host: db.example.com
              port: 5432
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            tmp_path = f.name
        try:
            cfg = settings_module.load_settings(config_path=tmp_path)
            self.assertEqual(cfg.database.host, "db.example.com")
            self.assertEqual(cfg.database.port, 5432)
        finally:
            os.unlink(tmp_path)
            settings_module._settings = None

    def test_defaults_preserved_for_unspecified_keys(self):
        yaml_content = "serial:\n  port: /dev/ttyUSB1\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            tmp_path = f.name
        try:
            cfg = settings_module.load_settings(config_path=tmp_path)
            # baud_rate not in yaml → default
            self.assertEqual(cfg.serial.baud_rate, 9600)
        finally:
            os.unlink(tmp_path)
            settings_module._settings = None


class TestEnvVarOverrides(unittest.TestCase):
    def setUp(self):
        settings_module._settings = None
        # Clean env
        for key in list(os.environ.keys()):
            if key.startswith("D10_"):
                del os.environ[key]

    def tearDown(self):
        settings_module._settings = None
        for key in list(os.environ.keys()):
            if key.startswith("D10_"):
                del os.environ[key]

    def test_string_override(self):
        os.environ["D10_SERIAL_PORT"] = "/dev/ttyS1"
        cfg = settings_module.load_settings(config_path="/nonexistent.yaml")
        self.assertEqual(cfg.serial.port, "/dev/ttyS1")

    def test_integer_override(self):
        os.environ["D10_SERIAL_BAUD_RATE"] = "115200"
        cfg = settings_module.load_settings(config_path="/nonexistent.yaml")
        self.assertEqual(cfg.serial.baud_rate, 115200)

    def test_boolean_override_true(self):
        os.environ["D10_DRIVER_AUTO_COMMIT"] = "false"
        cfg = settings_module.load_settings(config_path="/nonexistent.yaml")
        self.assertFalse(cfg.driver.auto_commit)

    def test_database_password_override(self):
        os.environ["D10_DATABASE_PASSWORD"] = "secret123"
        cfg = settings_module.load_settings(config_path="/nonexistent.yaml")
        self.assertEqual(cfg.database.password, "secret123")


if __name__ == "__main__":
    unittest.main()
