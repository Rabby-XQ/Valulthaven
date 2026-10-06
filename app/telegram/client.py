import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.types import Channel, InputPeerChannel

from app.constants import APP_NAME


load_dotenv()


class TelegramService:
    @staticmethod
    def _is_private_channel(entity):
        """Return whether a channel has no public username or alias."""
        if getattr(entity, "username", None):
            return False

        # Telegram can expose additional public aliases separately from the
        # primary username. Reject active aliases too.
        return not any(
            getattr(username, "active", False)
            and getattr(username, "username", None)
            for username in (getattr(entity, "usernames", None) or ())
        )

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

        self.upload_destination = None

    async def connect(self):
        await self.client.connect()
        return await self.client.is_user_authorized()

    async def request_code(self, phone):
        return await self.client.send_code_request(phone)

    async def sign_in(
        self,
        phone,
        code,
        phone_code_hash=None,
    ):
        return await self.client.sign_in(
            phone=phone,
            code=code,
            phone_code_hash=phone_code_hash,
        )

    async def sign_in_password(self, password):
        return await self.client.sign_in(
            password=password
        )

    async def get_me(self):
        return await self.client.get_me()

    async def get_backup_channels(self):
        if not self.client.is_connected():
            raise RuntimeError(
                "Telegram is not connected."
            )

        dialogs = await self.client.get_dialogs()

        channels = []

        for dialog in dialogs:
            entity = dialog.entity

            if not isinstance(entity, Channel):
                continue

            if not getattr(entity, "broadcast", False):
                continue

            if not self._is_private_channel(entity):
                continue

            channels.append(
                {
                    # Always use the canonical Telegram entity ID.
                    "id": entity.id,
                    "title": (
                        dialog.title
                        or getattr(entity, "title", None)
                        or "Untitled Channel"
                    ),
                    "entity": entity,
                }
            )

        channels.sort(
            key=lambda item: item["title"].lower()
        )

        return channels

    async def resolve_channel(self, channel_id):
        if not self.client.is_connected():
            raise RuntimeError(
                "Telegram is not connected."
            )

        try:
            saved_id = abs(int(channel_id))
        except (TypeError, ValueError):
            return None

        dialogs = await self.client.get_dialogs()

        for dialog in dialogs:
            entity = dialog.entity

            if not isinstance(entity, Channel):
                continue

            if not getattr(entity, "broadcast", False):
                continue

            if not self._is_private_channel(entity):
                continue

            # Compare against the canonical entity ID.
            # abs() also allows old saved negative dialog IDs
            # to continue working.
            if entity.id != saved_id:
                continue

            return {
                "id": entity.id,
                "title": (
                    dialog.title
                    or getattr(entity, "title", None)
                    or "Untitled Channel"
                ),
                "entity": entity,
            }

        return None

    async def create_backup_channel(self, channel_name):
        if not self.client.is_connected():
            raise RuntimeError(
                "Telegram is not connected."
            )

        channel_name = channel_name.strip()

        if not channel_name:
            raise ValueError(
                "Channel name is required."
            )

        result = await self.client(
            CreateChannelRequest(
                title=channel_name,
                about=(
                    "Private Telegram channel "
                    f"for {APP_NAME} files."
                ),
                broadcast=True,
                megagroup=False,
            )
        )

        entity = await self.client.get_entity(
            result.chats[0]
        )

        if not isinstance(entity, Channel):
            raise RuntimeError(
                "Telegram did not return a valid channel."
            )

        if not getattr(entity, "broadcast", False):
            raise RuntimeError(
                "The created destination is not a broadcast channel."
            )

        if not self._is_private_channel(entity):
            raise RuntimeError(
                f"Telegram created a public channel. {APP_NAME} only allows private channels."
            )

        return {
            "id": entity.id,
            "title": (
                getattr(entity, "title", None)
                or channel_name
            ),
            "entity": entity,
        }

    def set_upload_destination(self, entity):
        if entity is None:
            raise ValueError(
                "Upload destination cannot be empty."
            )

        if not isinstance(entity, Channel):
            raise ValueError(
                "Upload destination must be a Telegram channel."
            )

        if not getattr(entity, "broadcast", False):
            raise ValueError(
                "Upload destination must be a broadcast channel."
            )

        if not self._is_private_channel(entity):
            raise ValueError(
                "Public Telegram channels cannot be used as backup destinations."
            )

        self.upload_destination = entity

    def clear_upload_destination(self):
        self.upload_destination = None

    async def message_exists(
        self,
        message_id,
        destination=None,
    ):
        """
        Check whether a Telegram message still exists.

        Returns True when the message can be resolved and False when it
        was deleted or cannot be found.
        """

        if not self.client.is_connected():
            raise RuntimeError(
                "Telegram is not connected."
            )

        if message_id is None:
            return False

        if destination is None:
            destination = self.upload_destination

        if destination is None:
            raise RuntimeError(
                "No Telegram backup location is selected."
            )

        try:
            message_id = int(message_id)
        except (TypeError, ValueError):
            return False

        try:
            message = await self.client.get_messages(
                destination,
                ids=message_id,
            )
        except Exception as exc:
            print(
                f"Telegram message verification failed "
                f"for message {message_id}: {exc}"
            )
            return False

        if message is None:
            return False

        if isinstance(message, (list, tuple)):
            return len(message) > 0 and message[0] is not None

        return True

    async def existing_message_ids(
        self,
        message_ids,
        destination=None,
    ):
        """Fetch many destination messages in batches for backup verification."""
        if not self.client.is_connected():
            raise RuntimeError("Telegram is not connected.")

        if destination is None:
            destination = self.upload_destination

        if destination is None:
            raise RuntimeError("No Telegram backup location is selected.")

        existing = set()
        ids = [int(message_id) for message_id in message_ids if message_id]

        for offset in range(0, len(ids), 100):
            messages = await self.client.get_messages(
                destination,
                ids=ids[offset:offset + 100],
            )
            if messages is None:
                continue
            if not isinstance(messages, (list, tuple)):
                messages = [messages]
            existing.update(
                int(message.id)
                for message in messages
                if (
                    message is not None
                    and getattr(message, "id", None) is not None
                    and getattr(message, "media", None) is not None
                )
            )

        return existing

    async def upload_file(
        self,
        file_path,
        progress_callback=None,
    ):
        if not self.client.is_connected():
            raise RuntimeError(
                "Telegram is not connected."
            )

        if self.upload_destination is None:
            raise RuntimeError(
                "No Telegram backup location is selected."
            )

        if not self._is_private_channel(self.upload_destination):
            self.clear_upload_destination()
            raise RuntimeError(
                "Upload blocked: the selected Telegram channel is public. "
                "Choose a private channel as the backup location."
            )

        # Re-fetch the channel immediately before each send so a destination
        # that was made public after selection is rejected too.
        destination = self.upload_destination
        try:
            current_destination = await self.client.get_entity(
                InputPeerChannel(
                    destination.id,
                    destination.access_hash,
                )
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not verify that the Telegram backup location is still private. "
                "Upload was blocked."
            ) from exc

        if (
            not isinstance(current_destination, Channel)
            or not getattr(current_destination, "broadcast", False)
            or not self._is_private_channel(current_destination)
        ):
            self.clear_upload_destination()
            raise RuntimeError(
                "Upload blocked: the selected Telegram channel is public or is no longer a private channel."
            )

        self.upload_destination = current_destination

        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(
                f"File not found: {path}"
            )

        if not path.is_file():
            raise ValueError(
                f"Not a file: {path}"
            )

        message = await self.client.send_file(
            self.upload_destination,
            str(path),
            progress_callback=progress_callback,
        )

        return message

    async def disconnect(self):
        if self.client.is_connected():
            await self.client.disconnect()
