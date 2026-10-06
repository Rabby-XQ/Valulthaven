from PySide6.QtCore import QSettings

from app.constants import SETTINGS_APPLICATION, SETTINGS_ORGANIZATION



class DestinationStore:
    """Persistent Telegram backup destination settings."""

    KEY_ID = "telegram/upload_destination_id"
    KEY_TITLE = "telegram/upload_destination_title"
    KEY_TYPE = "telegram/upload_destination_type"

    def __init__(self):
        self.settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)

    def get_id(self):
        value = self.settings.value(self.KEY_ID, None)
        if value in (None, ""):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def get_title(self):
        return str(self.settings.value(self.KEY_TITLE, "") or "")

    def save_channel(self, channel_id, title):
        self.settings.setValue(self.KEY_ID, int(channel_id))
        self.settings.setValue(self.KEY_TITLE, str(title))
        self.settings.setValue(self.KEY_TYPE, "channel")
        self.settings.sync()

    def clear(self):
        self.settings.remove(self.KEY_ID)
        self.settings.remove(self.KEY_TITLE)
        self.settings.remove(self.KEY_TYPE)
        self.settings.sync()
