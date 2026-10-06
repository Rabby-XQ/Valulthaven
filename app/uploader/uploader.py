from pathlib import Path

from PySide6.QtCore import QObject, Signal


class UploadWorker(QObject):
    progress = Signal(str, int, int)
    started = Signal(str)
    completed = Signal(str, object)
    failed = Signal(str, str)

    def __init__(self, telegram_service, file_path):
        super().__init__()

        self.telegram = telegram_service
        self.file_path = Path(file_path)

    async def run(self):
        path = self.file_path

        try:
            if not path.exists():
                raise FileNotFoundError(
                    f"File not found: {path}"
                )

            if not path.is_file():
                raise ValueError(
                    f"Not a file: {path}"
                )

            self.started.emit(str(path))

            def progress_callback(current, total):
                self.progress.emit(
                    str(path),
                    current,
                    total,
                )

            message = await self.telegram.upload_file(
                path,
                progress_callback=progress_callback,
            )

            self.completed.emit(
                str(path),
                message,
            )

        except Exception as exc:
            self.failed.emit(
                str(path),
                str(exc),
            )