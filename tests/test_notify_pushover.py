from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "plugins/notify_by_pushover.sh"


class PushoverTests(unittest.TestCase):
    def run_script(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "notifications.env"
            config.write_text("PUSHOVER_USER_KEY=user\nPUSHOVER_APP_TOKEN=token\n", encoding="utf-8")
            fake_curl = root / "curl"
            fake_curl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_curl.chmod(0o755)
            environment = os.environ.copy()
            environment["CURL_BIN"] = str(fake_curl)
            return subprocess.run(
                [str(SCRIPT), "-f", str(config), *arguments],
                text=True, capture_output=True, env=environment, check=False,
            )

    def test_accepts_normal_notification(self) -> None:
        self.assertEqual(self.run_script("-t", "Test", "-m", "Hello").returncode, 0)

    def test_rejects_short_emergency_retry(self) -> None:
        result = self.run_script("-t", "Test", "-m", "Hello", "-p", "2", "-r", "29")
        self.assertEqual(result.returncode, 3)
        self.assertIn("at least 30", result.stderr)

    def test_rejects_excessive_message(self) -> None:
        result = self.run_script("-t", "Test", "-m", "x" * 1025)
        self.assertEqual(result.returncode, 3)


if __name__ == "__main__":
    unittest.main()

