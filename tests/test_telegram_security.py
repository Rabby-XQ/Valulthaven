import asyncio
import unittest
from pathlib import Path

from telethon.tl.types import Channel

from app.telegram.client import TelegramService


class ConnectedTelegramClient:
    def __init__(self):
        self.send_file_calls = 0

    def is_connected(self):
        return True

    async def send_file(self, *args, **kwargs):
        self.send_file_calls += 1
        return object()


def channel(*, username=None, usernames=None):
    entity = Channel.__new__(Channel)
    entity.id = 100
    entity.access_hash = 200
    entity.username = username
    entity.usernames = usernames
    entity.broadcast = True
    return entity


class TelegramSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = TelegramService.__new__(TelegramService)
        self.service.client = ConnectedTelegramClient()
        self.service.upload_destination = None

    def test_public_channel_cannot_be_selected(self):
        public_channel = channel(username="public_backup")

        with self.assertRaisesRegex(ValueError, "Public Telegram channels"):
            self.service.set_upload_destination(public_channel)

        self.assertIsNone(self.service.upload_destination)

    async def test_public_channel_upload_is_blocked_before_send(self):
        self.service.upload_destination = channel(username="public_backup")
        file_path = Path("public-upload-test.jpg")
        file_path.write_bytes(b"test")
        self.addCleanup(file_path.unlink, missing_ok=True)

        with self.assertRaisesRegex(RuntimeError, "Upload blocked"):
            await self.service.upload_file(file_path)

        self.assertEqual(self.service.client.send_file_calls, 0)
        self.assertIsNone(self.service.upload_destination)


if __name__ == "__main__":
    unittest.main()
