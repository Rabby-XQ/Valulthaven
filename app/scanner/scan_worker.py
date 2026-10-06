from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from app.scanner.folder_watcher import iter_media_files


class ScanWorker(QObject):

    file_found = Signal(dict)
    finished = Signal(str)

    def __init__(
        self,
        folder,
        destination_id=None,
        uploaded_signatures=None,
    ):
        super().__init__()

        self.folder = folder
        self.destination_id = destination_id
        self.uploaded_signatures = uploaded_signatures or {}

    @Slot()
    def run(self):
        """
        Fast scan.

        Scan-এর সময়:
        - SHA-256 hash করা হবে না
        - Database access করা হবে না
        - Telegram check করা হবে না
        - file stable কিনা তার জন্য wait করা হবে না

        শুধু supported media files detect করে UI-তে পাঠাবে।
        """

        detected_count = 0

        for path, stat in iter_media_files(self.folder):
            result = self._inspect_file(path, stat)

            if result is None:
                continue

            upload_record = self._uploaded_record(path, stat)
            if upload_record is not None:
                result["status"] = "uploaded"
                result["hash"] = upload_record.get("hash")
                result["telegram_message_id"] = upload_record.get(
                    "telegram_message_id"
                )
                result["uploaded_at"] = upload_record.get("uploaded_at")

            detected_count += 1
            self.file_found.emit(result)

        self.finished.emit(
            f"{detected_count} media file(s) found."
        )

    def _uploaded_record(self, path, stat):
        record = self.uploaded_signatures.get(str(path))
        if not record:
            return None
        if record.get("signature") != (stat.st_size, stat.st_mtime_ns):
            return None
        return record

    def _inspect_file(self, path, stat=None):
        path = Path(path)

        if stat is None:
            try:
                stat = path.stat()
            except (OSError, FileNotFoundError):
                return None

        if stat.st_size <= 0:
            return None

        suffix = path.suffix.lower()

        photo_extensions = {
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".bmp",
        }

        if suffix in photo_extensions:
            kind = "Photo"
        else:
            kind = "Video"

        return {
            "path": str(path),
            "name": path.name,
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "status": "pending",
            "hash": None,
            "kind": kind,
        }
