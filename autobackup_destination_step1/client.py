import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.types import Channel


load_dotenv()


class TelegramService:
    def __init__(self):
        api_id = os.getenv("TELEGRAM_API_ID")
        api_hash = os.getenv("TELEGRAM_API_HASH")

        if not api_id or not api_hash:
            raise RuntimeError(
                "Telegram API credentials are missing. "
                "Please configure TELEGRAM_API_ID and "
                "TELEGRAM_API_HASH in .env."
            )

        try:
            api_id = int(api_id)
        except ValueError as exc:
            raise RuntimeError(
                "TELEGRAM_API_ID must be a number."
            ) from exc

        session_path = Path("data/telegram")
        session_path.parent.mkdir(parents=True, exist_ok=True)

        self.client = TelegramClient(
            str(session_path),
            api_id,
            api_hash,
        )

        # Runtime-only destination entity.
        # The persistent destination ID/title are stored by MainWindow
        # with QSettings.
        self.upload_destination = None

    async def connect(self):
        await self.client.connect()
        return await self.client.is_user_authorized()

    async def request_code(self, phone):
        return await self.client.send_code_request(phone)

    async def sign_in(self, phone, code, phone_code_hash=None):
        return await self.client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash,
        )

    async def sign_in_password(self, password):
        return await self.client.sign_in(password=password)

    async def get_me(self):
        return await self.client.get_me()

    async def get_backup_channels(self):
        """
        Return channels available in the user's dialogs.

        Broadcast channels are preferred for backup because they are
        designed for administrator-only posting. Megagroups are excluded.
        """
        if not self.client.is_connected():
            raise RuntimeError("Telegram is not connected.")

        dialogs = await self.client.get_dialogs()

        channels = []

        for dialog in dialogs:
            entity = dialog.entity

            if not isinstance(entity, Channel):
                continue

            if not getattr(entity, "broadcast", False):
                continue

            channels.append(
                {
                    "id": dialog.id,
                    "title": dialog.title or "Untitled Channel",
                    "entity": entity,
                }
            )

        channels.sort(key=lambda item: item["title"].lower())

        return channels

    async def resolve_channel(self, channel_id):
        """
        Resolve a previously saved channel ID after app restart.

        get_dialogs() is intentionally used first so Telethon's entity
        cache is populated for private channels.
        """
        if not self.client.is_connected():
            raise RuntimeError("Telegram is not connected.")

        dialogs = await self.client.get_dialogs()

        for dialog in dialogs:
            if dialog.id != int(channel_id):
                continue

            entity = dialog.entity

            if not isinstance(entity, Channel):
                return None

            if not getattr(entity, "broadcast", False):
                return None

            return {
                "id": dialog.id,
                "title": dialog.title or "Untitled Channel",
                "entity": entity,
            }

        return None

    async def create_backup_channel(
        self,
        title,
        about="Private photo and video backup.",
    ):
        if not self.client.is_connected():
            raise RuntimeError("Telegram is not connected.")

        title = title.strip()

        if not title:
            raise ValueError("Channel name is required.")

        result = await self.client(
            CreateChannelRequest(
                title=title,
                about=about,
                broadcast=True,
                megagroup=False,
            )
        )

        # Telegram returns the created channel in the update response.
        entity = None

        for item in getattr(result, "chats", []):
            if isinstance(item, Channel):
                entity = item
                break

        if entity is None:
            raise RuntimeError(
                "The channel was created, but Telegram did not return "
                "the channel entity."
            )

        self.upload_destination = entity

        return {
            "id": entity.id,
            "title": entity.title or title,
            "entity": entity,
        }

    def set_upload_destination(self, entity):
        if entity is None:
            raise ValueError("Upload destination cannot be empty.")

        self.upload_destination = entity

    def clear_upload_destination(self):
        self.upload_destination = None

    async def upload_file(self, file_path, progress_callback=None):
        if not self.client.is_connected():
            raise RuntimeError("Telegram is not connected.")

        if self.upload_destination is None:
            raise RuntimeError(
                "No Telegram backup location is selected."
            )

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        if not path.is_file():
            raise ValueError(f"Not a file: {path}")

        message = await self.client.send_file(
            self.upload_destination,
            str(path),
            progress_callback=progress_callback,
        )

        return message

    async def disconnect(self):
        if self.client.is_connected():
            await self.client.disconnect()
