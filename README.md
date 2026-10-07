# VaultHaven

VaultHaven backs up selected local files to a private Telegram channel.

## First run

1. Download and run `VaultHaven-Setup-<version>.exe` on Windows.
2. Choose **Connect Telegram**. Each user enters their own Telegram API ID and API Hash from [my.telegram.org/apps](https://my.telegram.org/apps), then signs in with their own phone number and Telegram verification code.
3. Choose a private Telegram channel and the local folder to back up.

API credentials are stored in that Windows account's Windows Credential Manager. The Telegram login session and backup database are stored under `%LOCALAPPDATA%\VaultHaven\data`. They are not stored beside the executable, included in the build, or uploaded to the project repository. Keep the Windows account protected; the session file grants access to the signed-in Telegram account.

## Build a Windows executable

Use Windows with Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt
python -m unittest discover -s tests -v
python -m PyInstaller --clean --noconfirm VaultHaven.spec
```

The output is the `dist\VaultHaven` application folder. The build spec bundles the app, its logo, and required libraries as separate files; Inno Setup packages that folder in the user-level installer. It does not bundle `data`, `.env`, `.venv`, `.git`, a Telegram session, or a user database. Do not add project-local user data to the spec.

Before compiling the installer, generate the version-specific third-party license bundle:

```powershell
.\installer\prepare_licenses.ps1
```

The script creates a license inventory for the exact Python packages used in the build, downloads the GNU LGPLv3/GPLv3 texts used by Qt for Python, and copies the Python runtime license. The installer includes these files.

To compile the user-level Windows setup wizard, install Inno Setup 6 or newer and run:

```powershell
ISCC.exe /DBuildVersion=0.1.0 installer\VaultHaven.iss
```

The setup wizard shows privacy/system requirements information; supports the standard Back/Next/Cancel flow; offers an optional desktop shortcut; and offers to launch VaultHaven after installation. It installs under the current user's LocalAppData and does not require administrator access. No separate runtime download is required. VaultHaven's original code is open source under the MIT License; third-party components remain governed by their own licenses, summarized in `installer\Third-Party-Notices.txt`.

## Pre-release verification

The release workflow runs the automated regression tests and a clean-install startup smoke test before creating a draft release. The tests cover SHA-256 hash deduplication per Telegram destination, re-queuing a file when its Telegram message is deleted, recovery of interrupted uploads, and blocking public Telegram channels.

The smoke test installs the generated setup wizard into a temporary directory, verifies that `VaultHaven.exe` is installed, starts it, and confirms that it stays running. It does not perform Telegram login or upload because release automation must not use a real account.

Before publishing a release, follow `installer\telegram-release-checklist.md` on a clean Windows account or virtual machine. This manual check covers Telegram login, private-channel upload, deleted-message re-upload, file changes, restart recovery, and uninstall behavior.

## Releases and updates

The GitHub Actions workflow runs when a `v*` tag is pushed. It builds the Windows executable and setup wizard and creates a **draft** GitHub release, so a maintainer can inspect the artifacts and release notes before publishing. Set the app version to match the tag in `app/build_info.py` for local builds; the workflow sets it from the tag for release builds. Once a release is published, VaultHaven's **Check for updates** action detects newer versions and opens the release page. Users download and run the new installer themselves; updates are not silently installed.

### Windows security notice

VaultHaven's Windows installer is not code-signed. Windows SmartScreen may show a warning when you download or run it. Download the installer only from the official [VaultHaven GitHub Releases](https://github.com/Rabby-XQ/Valulthaven/releases) page.

## Telegram API requirement

Telegram requires each distributed client to use an API ID and API Hash registered by its operator. VaultHaven asks each user to provide their own. Do not put personal API credentials, account sessions, or `.env` files into a public executable or repository.
