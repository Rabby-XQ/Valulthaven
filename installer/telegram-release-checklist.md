# Telegram Release Checklist

The automated Windows workflow verifies installation and application startup. It cannot safely perform Telegram login or upload with a real account. Before publishing a release, perform these checks on a clean Windows user account or virtual machine:

1. Install the generated `VaultHaven-Setup-<version>.exe`.
2. Start VaultHaven and confirm the main window opens without a Python or Qt runtime error.
3. Enter a test Telegram API ID and API Hash, then complete login with a test account.
4. Confirm credentials are saved in Windows Credential Manager and are not written to the application directory.
5. Create or select a private Telegram broadcast channel.
6. Add a small test folder containing one supported image or video file.
7. Run a scan and confirm the file is uploaded to the selected private channel.
8. Confirm the uploaded message can be found after restarting the app.
9. Delete the Telegram message, rescan, and confirm the file becomes uploadable again.
10. Make a small file change, rescan, and confirm the changed file is uploaded.
11. Attempt to select a public channel and confirm the app rejects it.
12. Close the app while an upload is active, reopen it, and confirm the interrupted item is eligible for retry.
13. Uninstall and confirm the application is removed while user backup data remains under `%LOCALAPPDATA%\VaultHaven\data`.

Do not use a personal production Telegram account or real private files for release testing. Never commit API credentials, Telegram session files, or test account data.
