import asyncio
import ctypes
import os
import sys
from pathlib import Path

from PySide6.QtCore import QPropertyAnimation, QSettings, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QSplashScreen
from qasync import QEventLoop

from app.constants import APP_NAME, SETTINGS_APPLICATION, SETTINGS_ORGANIZATION
from app.ui.branding import app_icon, startup_splash_pixmap
from app.ui.main_window import MainWindow
from app.utils.startup_manager import (
    is_startup_enabled,
    migrate_legacy_startup_name,
)


def main():

    # Give Windows a stable application identity so Explorer and the taskbar
    # use VaultHaven's executable/window icon instead of Python's icon.
    if os.name == "nt":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "RabbyXQ.VaultHaven"
        )

    startup_mode = "--startup" in sys.argv[1:]
    if not startup_mode:
        # Recognize startup links created by older AutoBackup versions that
        # launched pythonw without the explicit --startup argument.
        startup_mode = (
            Path(sys.executable).name.lower() == "pythonw.exe"
            and is_startup_enabled()
        )
    migrate_legacy_startup_name()
    qt_arguments = [
        argument
        for argument in sys.argv
        if argument != "--startup"
    ]

    app = QApplication(
        qt_arguments
    )

    # Use an explicit point size instead of inheriting a Windows default
    # font whose point size may be unset (-1).
    app.setFont(
        QFont("Segoe UI", 10)
    )
    application_icon = app_icon()
    app.setWindowIcon(application_icon)

    # Closing the main window should not automatically
    # destroy the application. Tray mode handles that.
    app.setQuitOnLastWindowClosed(False)

    splash = None
    welcome_splash = False
    if not startup_mode:
        settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        already_shown = settings.value(
            "install/welcome_splash_shown", False, type=bool
        )
        has_existing_app_settings = any(
            key != "install/welcome_splash_shown"
            for key in settings.allKeys()
        )
        welcome_splash = not already_shown and not has_existing_app_settings
        if welcome_splash:
            settings.setValue("install/welcome_splash_shown", True)
            settings.sync()

        splash = QSplashScreen(
            startup_splash_pixmap(show_welcome=welcome_splash)
        )
        splash.setWindowTitle(APP_NAME)
        splash.setWindowOpacity(0.0)
        splash.show()
        fade_in = QPropertyAnimation(splash, b"windowOpacity", splash)
        fade_in.setDuration(450)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.start()

    loop = QEventLoop(app)

    asyncio.set_event_loop(
        loop
    )

    window = MainWindow(startup_mode=startup_mode)
    window.setWindowIcon(application_icon)

    if startup_mode and window.tray_icon is not None:
        window.hide()
    else:
        window.show()
        if splash is not None:
            if welcome_splash:
                QTimer.singleShot(7000, lambda: splash.finish(window))
            else:
                def fade_out_splash():
                    fade_out = QPropertyAnimation(
                        splash,
                        b"windowOpacity",
                        splash,
                    )
                    fade_out.setDuration(350)
                    fade_out.setStartValue(1.0)
                    fade_out.setEndValue(0.0)
                    fade_out.finished.connect(
                        lambda: splash.finish(window)
                    )
                    fade_out.start()

                QTimer.singleShot(850, fade_out_splash)

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
