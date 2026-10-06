from PySide6.QtCore import QSettings

from app.constants import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION



class BackupSettings:
    """
    Persistent settings for VaultHaven backup behavior.

    Modes:
        ask
        automatic
        photos_auto_videos_ask
    """

    MODE_ASK = "ask"
    MODE_AUTOMATIC = "automatic"
    MODE_PHOTOS_AUTO_VIDEOS_ASK = "photos_auto_videos_ask"

    KEY_MODE = "backup/permission_mode"
    KEY_LARGE_FILE_MB = "backup/large_file_threshold_mb"

    DEFAULT_MODE = MODE_ASK
    DEFAULT_LARGE_FILE_MB = 500

    ALLOWED_MODES = {
        MODE_ASK,
        MODE_AUTOMATIC,
        MODE_PHOTOS_AUTO_VIDEOS_ASK,
    }

    ALLOWED_LARGE_FILE_MB = {
        500,
        1024,
        2048,
        5120,
    }

    def __init__(self):
        self.settings = QSettings(
            SETTINGS_ORGANIZATION,
            SETTINGS_APPLICATION,
        )

    def get_mode(self):
        mode = str(
            self.settings.value(
                self.KEY_MODE,
                self.DEFAULT_MODE,
            )
            or self.DEFAULT_MODE
        )

        if mode not in self.ALLOWED_MODES:
            return self.DEFAULT_MODE

        return mode

    def set_mode(self, mode):
        if mode not in self.ALLOWED_MODES:
            raise ValueError(
                f"Invalid backup permission mode: {mode}"
            )

        self.settings.setValue(
            self.KEY_MODE,
            mode,
        )
        self.settings.sync()

    def get_large_file_threshold_mb(self):
        value = self.settings.value(
            self.KEY_LARGE_FILE_MB,
            self.DEFAULT_LARGE_FILE_MB,
        )

        try:
            value = int(value)
        except (TypeError, ValueError):
            return self.DEFAULT_LARGE_FILE_MB

        if value not in self.ALLOWED_LARGE_FILE_MB:
            return self.DEFAULT_LARGE_FILE_MB

        return value

    def set_large_file_threshold_mb(self, size_mb):
        try:
            size_mb = int(size_mb)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Large file threshold must be a number."
            ) from exc

        if size_mb not in self.ALLOWED_LARGE_FILE_MB:
            raise ValueError(
                "Invalid large file threshold."
            )

        self.settings.setValue(
            self.KEY_LARGE_FILE_MB,
            size_mb,
        )
        self.settings.sync()

    def is_automatic(self):
        return self.get_mode() == self.MODE_AUTOMATIC

    def is_photos_auto(self):
        return self.get_mode() == (
            self.MODE_PHOTOS_AUTO_VIDEOS_ASK
        )

    def is_large_file(self, size_bytes):
        threshold_mb = self.get_large_file_threshold_mb()

        threshold_bytes = (
            threshold_mb * 1024 * 1024
        )

        return size_bytes >= threshold_bytes

    @staticmethod
    def mode_label(mode):
        labels = {
            BackupSettings.MODE_ASK:
                "Ask Every Time",

            BackupSettings.MODE_AUTOMATIC:
                "Automatic Upload",

            BackupSettings.MODE_PHOTOS_AUTO_VIDEOS_ASK:
                "Photos Auto / Videos Ask",
        }

        return labels.get(mode, "Ask Every Time")
