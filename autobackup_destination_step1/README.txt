STEP 1: VaultHaven Backup Destination

Files included:
- client.py
- destination_dialog.py

This step adds:
1. Private broadcast-channel discovery.
2. Private channel creation through the logged-in user account.
3. Runtime upload destination support.
4. Uploading to the selected Telegram channel instead of Saved Messages.

Important:
- Do NOT delete data/telegram.session.
- Do NOT change .env.
- The existing SQLite database is untouched.
- The current uploader.py is intentionally untouched.
- MainWindow integration is the next patch because the exact current
  MainWindow/login flow should not be overwritten blindly.

Telethon's current documentation confirms:
- get_dialogs() returns dialogs and their entities.
- Dialog/entity objects can be passed to send_file().
- CreateChannelRequest can create a broadcast channel.
