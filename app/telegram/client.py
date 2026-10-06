import os
import shutil
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.types import Channel, InputPeerChannel

from app.constants import APP_NAME


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

    def __init__(self, api_id=None, api_hash=None):
        self.api_id = None
        self.api_hash = None
        self.client = None
        self.session_path = self._get_session_path()
        if api_id and api_hash:
            self.configure_credentials(api_id, api_hash)
        self.upload_destination = None

    @staticmethod
    def _get_session_path():
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            user_data_root = Path(local_app_data)
        elif os.name == "nt":
            user_data_root = (
                Path.home() / "AppData" / "Local"
            )
        else:
            user_data_root = Path.home() / ".local" / "share"

        session_directory = user_data_root / APP_NAME / "data"
        session_directory.mkdir(parents=True, exist_ok=True)
        session_path = session_directory / "telegram"

        # Preserve a developer's existing source-run login once, but never
        # migrate session data from a frozen/release bundle.
        session_file = session_path.with_suffix(".session")
        legacy_session = Path.cwd() / "data" / "telegram.session"
        if (
            not getattr(sys, "frozen", False)
            and not session_file.exists()
            and legacy_session.is_file()
        ):
            temporary_session = session_file.with_suffix(".session.tmp")
            shutil.copy2(legacy_session, temporary_session)
            os.replace(temporary_session, session_file)

        return session_path

    def configure_credentials(self, api_id, api_hash):
        try:
            parsed_api_id = int(str(api_id).strip())
        except (TypeError, ValueError) as exc:
            raise ValueError("Telegram API ID must be a number.") from exc
        api_hash = str(api_hash).strip()
        if not api_hash:
            raise ValueError("Telegram API Hash is required.")

        if self.api_id == parsed_api_id and self.api_hash == api_hash:
            return

        if self.client is not None and self.client.is_connected():
            raise RuntimeError("Disconnect Telegram before changing API credentials.")

        self.api_id = parsed_api_id
        self.api_hash = api_hash
        self.client = TelegramClient(
            str(self.session_path),
            self.api_id,
            self.api_hash,
        )

    def has_credentials(self):
        return self.client is not None

    async def connect(self):
        if self.client is None:
            return False
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
        if self.client is not None and self.client.is_connected():
            await self.client.disconnect()
