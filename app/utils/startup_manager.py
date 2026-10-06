import sys
from pathlib import Path

from app.constants import APP_NAME


LEGACY_APP_NAME = "AutoBackup"


def get_project_root():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def get_startup_directory():
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )


def get_launcher_path():
    return (
        Path.home()
        / "AppData"
        / "Local"
        / APP_NAME
        / f"{APP_NAME}_startup.vbs"
    )


def get_legacy_launcher_path():
    return (
        Path.home()
        / "AppData"
        / "Local"
        / LEGACY_APP_NAME
        / f"{LEGACY_APP_NAME}_startup.vbs"
    )


def create_launcher():
    project_root = get_project_root()
    startup_dir = get_startup_directory()
    launcher_path = get_launcher_path()

    startup_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    launcher_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if getattr(sys, "frozen", False):
        executable = Path(sys.executable).resolve()
        launch_command = f'"""{executable}"" --startup"'
    else:
        python_executable = (
            project_root
            / ".venv"
            / "Scripts"
            / "pythonw.exe"
        )

        if not python_executable.exists():
            current_python = Path(sys.executable)
            pythonw_executable = current_python.with_name("pythonw.exe")
            python_executable = (
                pythonw_executable
                if pythonw_executable.exists()
                else current_python
            )

        launch_command = (
            f'"""{python_executable}"" -m app.main --startup"'
        )

    script = f'''Set shell = CreateObject("WScript.Shell")

shell.CurrentDirectory = "{project_root}"

shell.Run {launch_command}, 0, False
'''

    launcher_path.write_text(
        script,
        encoding="utf-8",
    )

    return launcher_path


def get_startup_shortcut_path():
    return (
        get_startup_directory()
        / f"{APP_NAME}.lnk"
    )


def get_legacy_startup_shortcut_path():
    return get_startup_directory() / f"{LEGACY_APP_NAME}.lnk"


def enable_startup():
    launcher_path = create_launcher()
    shortcut_path = get_startup_shortcut_path()

    powershell_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "wscript.exe"
$Shortcut.Arguments = """{launcher_path}"""
$Shortcut.WorkingDirectory = "{get_project_root()}"
$Shortcut.Description = "{APP_NAME} startup"
$Shortcut.Save()
'''

    import subprocess

    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            powershell_script,
        ],
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    # Keep upgraded installations enabled while replacing the old shortcut name.
    for legacy_path in (
        get_legacy_startup_shortcut_path(),
        get_legacy_launcher_path(),
    ):
        if legacy_path.exists():
            legacy_path.unlink()

def disable_startup():
    for path in (
        get_startup_shortcut_path(),
        get_legacy_startup_shortcut_path(),
        get_launcher_path(),
        get_legacy_launcher_path(),
    ):
        if path.exists():
            path.unlink()


def is_startup_enabled():
    return (
        get_startup_shortcut_path().exists()
        or get_legacy_startup_shortcut_path().exists()
    )


def migrate_legacy_startup_name():
    """Upgrade the old shortcut and launcher names without disabling startup."""
    legacy_shortcut = get_legacy_startup_shortcut_path()
    if not legacy_shortcut.exists() or get_startup_shortcut_path().exists():
        return

    try:
        enable_startup()
    except Exception as exc:
        # Preserve the existing shortcut if the new one could not be created.
        print(f"Could not rename legacy startup shortcut: {exc}")
