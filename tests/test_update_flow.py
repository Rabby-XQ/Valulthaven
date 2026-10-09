import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.ui import main_window


class FakeResponse:
    def __init__(self, body, url, headers=None):
        self.body = body
        self.url = url
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        if size < 0:
            body, self.body = self.body, b""
            return body
        body, self.body = self.body[:size], self.body[size:]
        return body

    def geturl(self):
        return self.url


class UpdateFlowTests(unittest.TestCase):
    def test_release_check_returns_verified_installer_metadata(self):
        installer_bytes = b"test installer payload"
        installer_digest = hashlib.sha256(installer_bytes).hexdigest()
        payload = {
            "tag_name": "v0.1.5",
            "html_url": "https://github.com/Rabby-XQ/Valulthaven/releases/tag/v0.1.5",
            "assets": [
                {
                    "name": "VaultHaven-Setup-0.1.5.exe",
                    "state": "uploaded",
                    "browser_download_url": (
                        "https://github.com/Rabby-XQ/Valulthaven/releases/"
                        "download/v0.1.5/VaultHaven-Setup-0.1.5.exe"
                    ),
                    "digest": f"sha256:{installer_digest}",
                    "size": len(installer_bytes),
                }
            ],
        }
        results = []
        worker = main_window.ReleaseCheckWorker(
            "https://github.com/Rabby-XQ/Valulthaven.git"
        )
        worker.result_ready.connect(lambda *result: results.append(result))

        with patch(
            "app.ui.main_window.urlopen",
            return_value=FakeResponse(
                json.dumps(payload).encode(),
                "https://api.github.com/repos/Rabby-XQ/Valulthaven/releases/latest",
            ),
        ):
            worker.run()

        self.assertEqual(len(results), 1)
        version, _release_url, download_url, size, error, digest = results[0]
        self.assertEqual(version, "v0.1.5")
        self.assertTrue(download_url.endswith("VaultHaven-Setup-0.1.5.exe"))
        self.assertEqual(size, len(installer_bytes))
        self.assertEqual(error, "")
        self.assertEqual(digest, installer_digest)

    def test_download_verifies_hash_before_returning_installer(self):
        installer_bytes = b"known installer bytes"
        installer_digest = hashlib.sha256(installer_bytes).hexdigest()
        results = []
        progress = []

        with tempfile.TemporaryDirectory() as temp_directory:
            worker = main_window.UpdateDownloadWorker(
                "https://github.com/Rabby-XQ/Valulthaven/releases/"
                "download/v0.1.5/VaultHaven-Setup-0.1.5.exe",
                "v0.1.5",
                len(installer_bytes),
                installer_digest,
            )
            worker.download_finished.connect(
                lambda *result: results.append(result)
            )
            worker.progress_changed.connect(
                lambda *values: progress.append(values)
            )

            with (
                patch(
                    "app.ui.main_window.tempfile.gettempdir",
                    return_value=temp_directory,
                ),
                patch(
                    "app.ui.main_window.urlopen",
                    return_value=FakeResponse(
                        installer_bytes,
                        "https://release-assets.githubusercontent.com/installer.exe",
                        {"Content-Length": str(len(installer_bytes))},
                    ),
                ),
            ):
                worker.run()

            self.assertEqual(len(results), 1)
            installer_path, error = results[0]
            self.assertEqual(error, "")
            self.assertEqual(Path(installer_path).read_bytes(), installer_bytes)
            self.assertTrue(progress)

    def test_download_rejects_hash_mismatch_and_removes_partial_file(self):
        results = []

        with tempfile.TemporaryDirectory() as temp_directory:
            worker = main_window.UpdateDownloadWorker(
                "https://github.com/Rabby-XQ/Valulthaven/releases/"
                "download/v0.1.5/VaultHaven-Setup-0.1.5.exe",
                "v0.1.5",
                len(b"unexpected bytes"),
                "0" * 64,
            )
            worker.download_finished.connect(
                lambda *result: results.append(result)
            )
            with (
                patch(
                    "app.ui.main_window.tempfile.gettempdir",
                    return_value=temp_directory,
                ),
                patch(
                    "app.ui.main_window.urlopen",
                    return_value=FakeResponse(
                        b"unexpected bytes",
                        "https://release-assets.githubusercontent.com/installer.exe",
                        {"Content-Length": str(len(b"unexpected bytes"))},
                    ),
                ),
            ):
                worker.run()

            self.assertEqual(len(results), 1)
            installer_path, error = results[0]
            self.assertEqual(installer_path, "")
            self.assertIn("SHA-256 digest did not match", error)
            self.assertEqual(list(Path(temp_directory).rglob("*.part")), [])


if __name__ == "__main__":
    unittest.main()
