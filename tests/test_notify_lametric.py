from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("notify_lametric", ROOT / "plugins/notify-lametric.py")
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


class LaMetricTests(unittest.TestCase):
    def test_silent_window_wraps_midnight(self) -> None:
        self.assertTrue(module.in_silent_window("23:9", dt.datetime(2026, 1, 1, 1)))
        self.assertFalse(module.in_silent_window("23:9", dt.datetime(2026, 1, 1, 12)))

    def test_no_silent_window_is_default(self) -> None:
        self.assertFalse(module.in_silent_window(None, dt.datetime(2026, 1, 1, 1)))

    def test_reads_quoted_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notifications.env"
            path.write_text("LAMETRIC_GUID='secret'\n", encoding="utf-8")
            self.assertEqual(module.read_config(path)["LAMETRIC_GUID"], "secret")

    def test_rejects_invalid_window(self) -> None:
        with self.assertRaises(ValueError):
            module.in_silent_window("25:9", dt.datetime.now())

    def test_builds_safe_ipv4_hostname_and_ipv6_endpoints(self) -> None:
        self.assertEqual(
            module.notification_endpoint("192.0.2.10"),
            "http://192.0.2.10:8080/api/v2/device/notifications",
        )
        self.assertEqual(
            module.notification_endpoint("clock.example.org"),
            "http://clock.example.org:8080/api/v2/device/notifications",
        )
        self.assertEqual(
            module.notification_endpoint("2001:db8::10"),
            "http://[2001:db8::10]:8080/api/v2/device/notifications",
        )

    def test_rejects_url_injection_as_host(self) -> None:
        with self.assertRaises(ValueError):
            module.notification_endpoint("clock.example.org/path")


if __name__ == "__main__":
    unittest.main()
