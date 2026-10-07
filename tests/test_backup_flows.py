import tempfile
import unittest
from pathlib import Path

from app.database.database import Database
from app.utils.hashing import sha256_file


class BackupFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database = Database(
            Path(self.temp_directory.name) / "backup.db"
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_identical_hash_is_deduplicated_per_destination(self):
        first_path = Path(self.temp_directory.name) / "first.jpg"
        second_path = Path(self.temp_directory.name) / "second.jpg"
        first_path.write_bytes(b"same backup content")
        second_path.write_bytes(b"same backup content")
        file_hash = sha256_file(first_path)
        destination_id = 123

        self.database.upsert(
            first_path,
            file_hash,
            first_path.stat().st_size,
            first_path.stat().st_mtime_ns,
        )
        self.database.mark_uploaded(
            first_path,
            file_hash,
            destination_id,
            9001,
        )
        self.database.upsert(
            second_path,
            file_hash,
            second_path.stat().st_size,
            second_path.stat().st_mtime_ns,
        )

        self.assertTrue(
            self.database.has_uploaded_to_destination(
                file_hash,
                destination_id,
            )
        )
        self.database.mark_duplicate(second_path, destination_id)
        self.assertEqual(
            self.database.get_by_path(second_path)[4],
            "skipped",
        )
        self.assertIsNotNone(
            self.database.get_upload_record(file_hash, destination_id)
        )

    def test_deleted_telegram_record_becomes_uploadable_again(self):
        file_path = Path(self.temp_directory.name) / "photo.jpg"
        file_path.write_bytes(b"content")
        file_hash = sha256_file(file_path)
        destination_id = 456

        self.database.upsert(
            file_path,
            file_hash,
            file_path.stat().st_size,
            file_path.stat().st_mtime_ns,
        )
        self.database.mark_uploaded(
            file_path,
            file_hash,
            destination_id,
            9100,
        )
        self.database.delete_upload_record(file_hash, destination_id)

        record = self.database.get_by_path(file_path)
        self.assertFalse(
            self.database.has_uploaded_to_destination(
                file_hash,
                destination_id,
            )
        )
        self.assertEqual(record[4], "pending")
        self.assertIsNone(record[5])
        self.assertIsNone(record[6])

    def test_interrupted_upload_is_recovered_as_pending(self):
        file_path = Path(self.temp_directory.name) / "video.mp4"
        file_path.write_bytes(b"video")
        file_hash = sha256_file(file_path)

        self.database.upsert(
            file_path,
            file_hash,
            file_path.stat().st_size,
            file_path.stat().st_mtime_ns,
        )
        self.database.mark_uploading(file_path, 789)

        recovered_count = self.database.recover_interrupted_uploads()
        record = self.database.get_by_path(file_path)

        self.assertEqual(recovered_count, 1)
        self.assertEqual(record[4], "pending")
        self.assertIn("interrupted", record[8])


if __name__ == "__main__":
    unittest.main()
