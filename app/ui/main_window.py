import asyncio
import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

try:
    import winsound
except ImportError:  # Windows system sound is unavailable on other platforms.
    winsound = None

from PySide6.QtCore import (
    Qt, QThread, Signal, QTimer, QSettings, QPoint, QSize, QStandardPaths,
    QByteArray,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QPalette,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QFileDialog,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QDialog,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSystemTrayIcon,
    QMenu,
    QStyle,
    QToolButton,
    QWidgetAction,
    QVBoxLayout,
    QPushButton,
    QWidget,
)

from app.scanner.scan_worker import ScanWorker
from app.telegram.client import TelegramService
from app.telegram.credential_store import get_credentials, save_credentials
from app.telegram.login_dialog import TelegramLoginDialog
from app.telegram.destination_dialog import BackupLocationDialog
from app.telegram.destination_store import DestinationStore
from app.telegram.async_dialog import open_dialog
from app.backup.scan_permission_dialog import ScanPermissionDialog
from app.backup.backup_settings import BackupSettings
from app.backup.review_files_dialog import ReviewFilesDialog
from app.uploader.uploader import UploadWorker
from app.database.database import Database
from app.utils.startup_manager import (
    enable_startup,
    disable_startup,
    is_startup_enabled,
)
from app.utils.hashing import sha256_file_async
from app.ui.photo_tile import MediaDetailsDialog, PhotoTile
from app.ui.branding import app_icon
from app.constants import (
    APP_NAME,
    APP_VERSION,
    DEVELOPER_NAME,
    DEVELOPER_GITHUB_URL,
    DEVELOPER_FACEBOOK_URL,
    GITHUB_REPOSITORY_URL,
    SETTINGS_APPLICATION,
    SETTINGS_ORGANIZATION,
)


def format_size(size):
    value = float(size)

    for unit in ("B", "KB", "MB", "GB", "TB"):

        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"

        value /= 1024

    return f"{size} B"


class ReleaseCheckWorker(QThread):
    result_ready = Signal(str, str, str)

    def __init__(self, repository_url, parent=None):
        super().__init__(parent)
        self.repository_url = repository_url

    def run(self):
        parsed = urlsplit(self.repository_url)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if parsed.hostname not in {"github.com", "www.github.com"} or len(parts) < 2:
            self.result_ready.emit("", "", "The GitHub repository URL is invalid.")
            return

        owner, repository = parts[:2]
        repository = repository.removesuffix(".git")
        api_url = f"https://api.github.com/repos/{owner}/{repository}/releases/latest"
        request = Request(
            api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"{APP_NAME}/{APP_VERSION}",
            },
        )

        try:
            with urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.result_ready.emit(
                str(payload.get("tag_name", "")).strip(),
                str(payload.get("html_url", "")).strip(),
                "",
            )
        except HTTPError as exc:
            if exc.code == 404:
                self.result_ready.emit(
                    "",
                    "",
                    "No published GitHub release was found for this project.",
                )
            else:
                self.result_ready.emit("", "", f"GitHub returned HTTP {exc.code}.")
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            self.result_ready.emit("", "", f"Could not check GitHub releases: {exc}")


class FileCard(QFrame):
    skip_signal = Signal(str)
    retry_signal = Signal(str)

    def __init__(self, item):
        super().__init__()

        self.item = item
        self.backup_item = item
        self.file_path = item["path"]

        self.setObjectName("fileCard")
        self.setFixedSize(100, 124)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.photo_tile = PhotoTile(item, status=item.get("status", "pending"))
        self.photo_tile.setParent(self)
        layout.addWidget(self.photo_tile, alignment=Qt.AlignmentFlag.AlignCenter)

        top = QHBoxLayout()

        self.name_label = QLabel(
            item["name"]
        )
        self.name_label.setObjectName(
            "fileName"
        )
        self.name_label.setToolTip(
            item["path"]
        )
        self.name_label.hide()

        self.status_label = QLabel()
        self.set_status_style(
            item["status"]
        )
        self.status_label.hide()

        top.addWidget(
            self.name_label,
            1,
        )
        top.addWidget(
            self.status_label
        )

        meta = QLabel(
            f'{item["kind"]}  •  '
            f'{format_size(item["size"])}'
        )
        meta.setObjectName(
            "fileMeta"
        )
        meta.hide()

        self.progress = QProgressBar()
        self.progress.setTextVisible(
            False
        )
        self.progress.setRange(
            0,
            100,
        )
        self.progress.setValue(
            100
            if item["status"] == "uploaded"
            else 0
        )
        self.progress.setFixedHeight(
            5
        )
        self.progress.hide()

        self.transfer_label = QLabel(
            ""
        )
        self.transfer_label.setObjectName(
            "transferInfo"
        )
        self.transfer_label.hide()

        action_row = QHBoxLayout()
        action_row.setSpacing(
            8
        )
        action_row.addStretch()

        self.retry_button = QPushButton(
            "Retry"
        )
        self.retry_button.setFixedWidth(
            80
        )
        self.retry_button.clicked.connect(
            self.retry_requested
        )
        self.retry_button.setVisible(
            False
        )

        self.skip_button = QPushButton(
            "Skip"
        )
        self.skip_button.setFixedWidth(
            80
        )
        self.skip_button.clicked.connect(
            self.skip_requested
        )
        self.skip_button.setVisible(
            False
        )

        action_row.addWidget(
            self.retry_button
        )
        action_row.addWidget(
            self.skip_button
        )

        layout.addLayout(
            top
        )
        layout.addWidget(
            meta
        )
        layout.addWidget(
            self.progress
        )
        layout.addWidget(
            self.transfer_label
        )
        layout.addLayout(
            action_row
        )

        self.set_status(
            item["status"]
        )

    def set_status_style(self, status):
        status_text = {
            "pending": "Pending",
            "uploaded": "Uploaded ✓",
            # Queued uploads are still pending until their turn starts.
            "waiting": "Pending",
            "uploading": "Uploading...",
            "skipped": "Skipped ⏭",
            "failed": "Failed",
        }.get(
            status,
            status.title(),
        )

        self.status_label.setText(
            status_text
        )

        self.status_label.setObjectName(
            f"status_{status}"
        )

        self.status_label.style().unpolish(
            self.status_label
        )

        self.status_label.style().polish(
            self.status_label
        )

    def set_status(self, status):
        self.backup_item["status"] = status
        self.photo_tile.set_status(status)

        self.set_status_style(
            status
        )

        self.skip_button.setVisible(
            status == "uploading"
        )

        if status == "uploaded":
            self.progress.setValue(100)
            self.transfer_label.setText(
                "Completed"
            )

        elif status == "pending":
            self.transfer_label.setText(
                "Waiting for upload"
            )

        elif status == "waiting":
            self.transfer_label.setText("Pending upload")

        elif status == "uploading":
            self.transfer_label.setText(
                "Starting upload..."
            )

        elif status == "failed":
            self.transfer_label.setText(
                "Upload failed"
            )

        elif status == "skipped":
            self.transfer_label.setText(
                "Skipped"
            )

    def set_progress(
        self,
        current,
        total,
        speed=0,
        eta=None,
    ):
        if total <= 0:
            return

        percent = int(
            (current / total) * 100
        )
        percent = max(
            0,
            min(
                100,
                percent,
            ),
        )
        self.photo_tile.set_upload_progress(current, total)

        current_text = format_size(
            current
        )
        total_text = format_size(
            total
        )

        if speed > 0:
            speed_text = (
                f"{format_size(speed)}/s"
            )
        else:
            speed_text = "Calculating speed..."

        if eta is not None:
            if eta < 60:
                eta_text = (
                    f"{eta:.0f}s remaining"
                )
            else:
                minutes = int(eta // 60)
                seconds = int(eta % 60)
                eta_text = (
                    f"{minutes}m {seconds}s remaining"
                )
        else:
            eta_text = "Calculating ETA..."

        self.transfer_label.setText(
            f"{percent}%  •  "
            f"{current_text} / {total_text}  •  "
            f"{speed_text}  •  "
            f"{eta_text}"
        )

    def set_waiting(self, position=None):
        self.set_status(
            "waiting"
        )

        if position is not None:
            self.transfer_label.setText(
                f"Pending upload  •  Queue position {position}"
            )

    def retry_requested(self):
        self.retry_signal.emit(
            self.backup_item["path"]
        )

    def skip_requested(self):
        self.set_status(
            "skipped"
        )

        self.skip_signal.emit(
            self.backup_item["path"]
        )


class SettingsToggle(QPushButton):

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)

        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(58, 30)
        self.setObjectName("settingsToggle")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._update_text)
        self._update_text(self.isChecked())

    def _update_text(self, checked):
        self.setText("ON" if checked else "OFF")


class MainWindow(QMainWindow):

    def __init__(self, startup_mode=False):
        super().__init__()

        self.startup_mode = bool(startup_mode)
        self._in_tray_mode = self.startup_mode

        self.setWindowTitle(
            APP_NAME
        )
        self.setWindowIcon(app_icon())

        self.resize(
            900,
            680,
        )

        self.setMinimumSize(
            760,
            560,
        )

        self.settings = QSettings(
            SETTINGS_ORGANIZATION,
            SETTINGS_APPLICATION,
        )
        self.sidebar_collapsed = self.settings.value(
            "ui/sidebar_collapsed",
            False,
            type=bool,
        )

        self.selected_folder = self.settings.value(
            "backup/folder",
            "",
        )

        saved_telegram_credentials = get_credentials()
        self.telegram = TelegramService(
            *(saved_telegram_credentials or (None, None))
        )
        self.telegram_connected = False
        self.telegram_user = None
        self.telegram_profile_photo = None
        self.telegram_connecting = False
        self.db = Database()
        self.recovered_upload_count = self.db.recover_interrupted_uploads()
        self.destination_store = DestinationStore()
        self.backup_destination_id = self.destination_store.get_id()
        self.backup_destination_title = self.destination_store.get_title()
        self.backup_destination_available = False

        self.scan_thread = None
        self.scan_worker = None

        self.cards = []
        self.upload_queue = []
        self.upload_current = None
        self.upload_in_progress = False
        self.backup_paused = self.settings.value(
            "backup/paused",
            False,
            type=bool,
        )
        self.upload_worker = None
        self.upload_task = None
        self.upload_total = 0
        self.upload_completed_count = 0
        self.upload_failed_count = 0
        self._upload_batch_notified = False
        self.upload_started_at = None
        self.upload_last_current = 0
        self.upload_last_time = None
        self.upload_speed = 0.0
        self.backup_settings = BackupSettings()
        self.automatic_scan_enabled = self.settings.value(
            "backup/automatic_scan_enabled",
            True,
            type=bool,
        )
        self.auto_backup_interval_minutes = self.settings.value(
            "backup/interval_minutes",
            60,
            type=int,
        )
        self.auto_backup_interval_minutes = max(
            1,
            min(1440, int(self.auto_backup_interval_minutes)),
        )
        self.last_scan_items = []
        self._scan_auto_upload = False
        self._allow_close = False
        self._shutdown_started = False
        self.tray_icon = None
        self._notification_toast = None
        self._notification_title = None
        self._notification_message = None
        self._notification_icon = None
        self._notification_timer = QTimer(self)
        self._notification_timer.setSingleShot(True)
        self._notification_timer.timeout.connect(self._hide_notification)
        self.auto_scan_timer = QTimer(self)
        self.auto_scan_timer.setInterval(self.auto_backup_interval_minutes * 60 * 1000)
        self.auto_scan_timer.timeout.connect(
            self.auto_scan
        )

        self.setup_ui()
        self.setup_tray()
        self._in_tray_mode = bool(
            self.startup_mode and self.tray_icon is not None
        )

        if self.recovered_upload_count:
            self.last_scan.setText(
                f"{self.recovered_upload_count} upload(s) were interrupted. "
                "Scan the folder to review and retry them."
            )

        QTimer.singleShot(
            500,
            self.auto_connect_telegram,
        )

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        self.tray_icon = QSystemTrayIcon(self)

        # Use the application's icon if one exists.
        icon = self.windowIcon()

        # Fallback to a built-in Windows/Qt icon.
        if icon.isNull():
            icon = self.style().standardIcon(
                QStyle.StandardPixmap.SP_ComputerIcon
            )

        self.tray_icon.setIcon(icon)

        self.tray_menu = QMenu(self)

        self.tray_menu.setStyleSheet("""
            QMenu {
                background-color: #1f1f1f;
                color: #f5f5f5;
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                padding: 6px;
                font-size: 13px;
            }

            QMenu::item {
                background-color: transparent;
                color: #f5f5f5;
                padding: 9px 28px 9px 12px;
                border-radius: 5px;
            }

            QMenu::item:selected {
                background-color: #2f2f2f;
                color: #ffffff;
            }

            QMenu::item:disabled {
                color: #777777;
            }

            QMenu::separator {
                height: 1px;
                background-color: #363636;
                margin: 5px 8px;
            }
        """)

        open_action = QAction(
            f"Open {APP_NAME}",
            self,
        )
        open_action.triggered.connect(
            self.show_window
        )

        scan_action = QAction(
            "Scan Now",
            self,
        )
        scan_action.triggered.connect(
            self.scan_from_tray
        )

        self.tray_menu.addAction(open_action)
        self.tray_menu.addAction(scan_action)

        self.tray_menu.addSeparator()

        self.pause_action = QAction(
            "Resume Backup" if self.backup_paused else "Stop Backup",
            self,
        )

        self.pause_action.triggered.connect(
            self.toggle_backup_pause
        )

        self.tray_menu.addAction(
            self.pause_action
        )

        self.tray_menu.addSeparator()

        exit_action = QAction(
            "Exit",
            self,
        )
        exit_action.triggered.connect(
            self.exit_application
        )

        self.tray_menu.addAction(
            exit_action
        )

        self.tray_icon.setContextMenu(
            self.tray_menu
        )

        self.tray_icon.activated.connect(
            self.tray_activated
        )

        self.tray_icon.setToolTip(
            APP_NAME
        )

        self.tray_icon.show()

    def show_main_window(self):
        self._in_tray_mode = False
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def show_dashboard(self):
        self.show_main_window()
        self.dashboard_scroll.verticalScrollBar().setValue(0)

    def show_window(self):
        self._in_tray_mode = False
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _hide_notification(self):
        if self._notification_toast is not None:
            self._notification_toast.hide()

    @staticmethod
    def _play_notification_sound(kind):
        """Play one system sound for completed or failed upload batches."""
        if kind not in {"success", "warning"}:
            return

        try:
            if winsound is not None:
                sound = (
                    winsound.MB_OK
                    if kind == "success"
                    else winsound.MB_ICONEXCLAMATION
                )
                winsound.MessageBeep(sound)
            else:
                QApplication.beep()
        except Exception as exc:
            print(f"Could not play notification sound: {exc}")

    def show_notification(self, title, message, kind="info"):
        """Show a compact in-app toast, or a native tray notice when hidden."""
        self._play_notification_sound(kind)

        if not self.isVisible() or self.isMinimized():
            if self.tray_icon is not None and self.tray_icon.isVisible():
                tray_icon = (
                    QSystemTrayIcon.MessageIcon.Warning
                    if kind == "warning"
                    else QSystemTrayIcon.MessageIcon.Information
                )
                self.tray_icon.showMessage(
                    title,
                    message,
                    tray_icon,
                    8000,
                )
            return

        if self._notification_toast is None:
            toast = QFrame(self)
            toast.setObjectName("appNotification")
            toast.setFixedSize(360, 88)

            effect = QGraphicsDropShadowEffect(toast)
            effect.setBlurRadius(24)
            effect.setOffset(0, 5)
            effect.setColor(QColor(32, 33, 36, 65))
            toast.setGraphicsEffect(effect)

            row = QHBoxLayout(toast)
            row.setContentsMargins(14, 12, 16, 12)
            row.setSpacing(12)

            self._notification_icon = QLabel()
            self._notification_icon.setObjectName("notificationIcon")
            self._notification_icon.setFixedSize(38, 38)
            self._notification_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(self._notification_icon, 0, Qt.AlignmentFlag.AlignVCenter)

            text_column = QVBoxLayout()
            text_column.setContentsMargins(0, 0, 0, 0)
            text_column.setSpacing(3)
            self._notification_title = QLabel()
            self._notification_title.setObjectName("notificationTitle")
            self._notification_message = QLabel()
            self._notification_message.setObjectName("notificationMessage")
            self._notification_message.setWordWrap(True)
            text_column.addWidget(self._notification_title)
            text_column.addWidget(self._notification_message)
            row.addLayout(text_column, 1)

            self._notification_toast = toast

        palettes = {
            "info": ("#1a73e8", "#e8f0fe", "●"),
            "success": ("#188038", "#e6f4ea", "✓"),
            "warning": ("#b06000", "#fff4e5", "!"),
        }
        accent, tint, glyph = palettes.get(kind, palettes["info"])
        self._notification_toast.setStyleSheet(f"""
            QFrame#appNotification {{
                background: #ffffff;
                border: 1px solid #e2e5e9;
                border-left: 4px solid {accent};
                border-radius: 14px;
            }}
            QLabel#notificationIcon {{
                background: {tint};
                color: {accent};
                border: none;
                border-radius: 19px;
                font-size: 19px;
                font-weight: 700;
            }}
            QLabel#notificationTitle {{
                background: transparent;
                color: #202124;
                border: none;
                font-size: 14px;
                font-weight: 700;
            }}
            QLabel#notificationMessage {{
                background: transparent;
                color: #5f6368;
                border: none;
                font-size: 12px;
            }}
        """)
        self._notification_icon.setText(glyph)
        self._notification_title.setText(title)
        self._notification_message.setText(message)
        self._notification_toast.move(
            max(12, self.width() - self._notification_toast.width() - 22),
            18,
        )
        self._notification_toast.show()
        self._notification_toast.raise_()
        self._notification_timer.start(8000)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_main_window()

    def scan_from_tray(self):
        self.show_main_window()
        self.scan_now()

    def exit_application(self):
        if self._shutdown_started:
            return

        self._shutdown_started = True
        self._allow_close = True
        self.auto_scan_timer.stop()
        self._notification_timer.stop()

        self.upload_queue.clear()

        if self.tray_icon is not None:
            self.tray_icon.hide()

        # Exit stops the timer and cancels work above; quitting the loop now
        # ensures no VaultHaven process remains in the tray.
        QApplication.quit()

    async def _graceful_shutdown(self):
        try:
            # Stop current upload task.
            if self.upload_task is not None:
                if not self.upload_task.done():
                    self.upload_task.cancel()

                try:
                    await asyncio.wait_for(
                        asyncio.shield(self.upload_task),
                        timeout=1.0,
                    )
                except asyncio.CancelledError:
                    pass
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    pass

                self.upload_task = None

            self.upload_in_progress = False
            self.upload_worker = None

            # Disconnect Telegram cleanly.
            try:
                await asyncio.wait_for(
                    self.telegram.disconnect(),
                    timeout=2.0,
                )
            except Exception as exc:
                print(
                    f"Telegram shutdown warning: {exc}"
                )

        finally:
            QApplication.quit()

    def toggle_backup_pause(self):
        self.backup_paused = not self.backup_paused
        self.settings.setValue(
            "backup/paused",
            self.backup_paused,
        )
        self.settings.sync()

        if self.backup_paused:
            self.pause_action.setText(
                "Resume Backup"
            )

            if hasattr(self, "auto_scan_timer"):
                self.auto_scan_timer.stop()

            self.status_label.setText(
                "● Backup paused"
            )

            self.last_scan.setText(
                "Backup is paused"
            )
            self.release_tray_memory_if_idle()

        else:
            self.pause_action.setText(
                "Stop Backup"
            )

            if (
                self.selected_folder
                and self.automatic_scan_enabled
                and hasattr(self, "auto_scan_timer")
                and not self.auto_scan_timer.isActive()
            ):
                self.auto_scan_timer.start()

            if self.automatic_scan_enabled and self.selected_folder:
                QTimer.singleShot(0, self.auto_scan)

            self.status_label.setText(
                "● Backup resumed"
            )

            # Continue anything that was already waiting.
            self.process_next_upload()

    def setup_ui(self):

        central = QWidget()

        self.setCentralWidget(
            central
        )

        outer_layout = QHBoxLayout(
            central
        )

        outer_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        dashboard_scroll = QScrollArea()
        self.dashboard_scroll = dashboard_scroll

        dashboard_scroll.setObjectName(
            "dashboardScroll"
        )

        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )
        dashboard_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        dashboard_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        dashboard_content = QWidget()

        root = QVBoxLayout(
            dashboard_content
        )

        root.setContentsMargins(
            28,
            24,
            28,
            24,
        )

        root.setSpacing(16)

        dashboard_scroll.setWidget(
            dashboard_content
        )

        outer_layout.addWidget(
            dashboard_scroll
        )

        # Header

        header = QHBoxLayout()

        title = QLabel("Overview")

        title.setObjectName(
            "title"
        )

        self.status_label = QLabel(
            "● Ready"
        )

        self.status_label.setObjectName(
            "readyStatus"
        )

        self.settings_button = QToolButton()
        self.settings_button.setText("")
        self.settings_button.setToolTip("Settings")
        self.settings_button.setFixedWidth(204)
        self.settings_button.setFixedHeight(42)
        settings_action_layout = QHBoxLayout(self.settings_button)
        settings_action_layout.setContentsMargins(14, 0, 12, 0)
        settings_action_layout.setSpacing(12)
        self.settings_icon_label = QLabel()
        self.settings_icon_label.setFixedSize(22, 22)
        self.settings_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.settings_icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.settings_text_label = QLabel("Settings")
        self.settings_text_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.settings_text_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        settings_action_layout.addWidget(self.settings_icon_label)
        settings_action_layout.addWidget(self.settings_text_label, 1)
        self.settings_action_layout = settings_action_layout
        self.settings_button.setArrowType(
            Qt.ArrowType.NoArrow
        )
        self.settings_button.clicked.connect(
            self.show_settings_menu
        )

        self.about_button = QToolButton()
        self.about_button.setText("")
        self.about_button.setToolTip("About VaultHaven")
        self.about_button.setFixedWidth(204)
        self.about_button.setFixedHeight(42)
        self.about_action_layout = QHBoxLayout(self.about_button)
        self.about_action_layout.setContentsMargins(14, 0, 12, 0)
        self.about_action_layout.setSpacing(12)
        self.about_icon_label = QLabel()
        self.about_icon_label.setFixedSize(22, 22)
        self.about_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.about_icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.about_text_label = QLabel("About")
        self.about_text_label.setAlignment(
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.about_text_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.about_action_layout.addWidget(self.about_icon_label)
        self.about_action_layout.addWidget(self.about_text_label, 1)
        self.about_button.clicked.connect(self.show_about_dialog)

        header.addWidget(title)

        header.addStretch()

        self.settings_menu = QMenu(self)
        self.settings_menu.setMinimumWidth(330)
        self.settings_menu.setStyleSheet("""
            QMenu {
                background: #ffffff;
                color: #202124;
                border: 1px solid #dadce0;
                border-radius: 10px;
                padding: 8px;
            }
            QMenu::item {
                padding: 8px 12px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: #f1f3f4;
            }
        """)
        self.build_settings_menu()

        self.telegram_button = QToolButton()
        self.telegram_button.setText("👤   Connect Telegram")
        self.telegram_button.setToolTip("Telegram connection")
        self.telegram_button.setFixedWidth(204)
        self.telegram_button.setFixedHeight(50)
        self.telegram_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.telegram_button.setIconSize(QSize(30, 30))
        self.telegram_button.setArrowType(Qt.ArrowType.NoArrow)
        self.telegram_button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.telegram_button.clicked.connect(self.handle_telegram_button_click)

        self.profile_menu = QMenu(self)
        self.profile_menu.setMinimumWidth(220)
        self.profile_menu.setStyleSheet("""
            QMenu {
                background: #ffffff;
                color: #202124;
                border: 1px solid #dadce0;
                border-radius: 10px;
                padding: 8px;
            }
            QMenu::item {
                padding: 8px 12px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background: #f1f3f4;
            }
            QMenu::item:disabled {
                color: #202124;
            }
        """)
        self.profile_account_action = self.profile_menu.addAction(
            "Telegram account"
        )
        self.profile_account_action.setEnabled(False)
        self.profile_destination_action = self.profile_menu.addAction(
            "Telegram backup channel: Not selected"
        )
        self.profile_destination_action.setEnabled(False)
        self.profile_menu.addSeparator()
        self.profile_change_destination_action = self.profile_menu.addAction(
            "Choose Telegram backup channel"
        )
        self.profile_change_destination_action.triggered.connect(
            self.change_backup_location
        )
        self.profile_menu.addSeparator()
        self.profile_logout_action = self.profile_menu.addAction(
            "Log out Telegram"
        )
        self.profile_logout_action.triggered.connect(
            self.logout_telegram
        )

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(236)
        self.sidebar = sidebar
        sidebar_layout = QVBoxLayout(sidebar)
        self.sidebar_layout = sidebar_layout
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(8)

        brand_stack = QVBoxLayout()
        brand_stack.setSpacing(10)
        brand_row = QHBoxLayout()
        self.sidebar_brand_row = brand_row
        brand_row.setSpacing(0)
        self.sidebar_logo_label = QLabel()
        self.sidebar_logo_label.setFixedSize(34, 34)
        self.sidebar_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_logo_label.setPixmap(
            app_icon().pixmap(QSize(32, 32))
        )
        brand_row.addWidget(self.sidebar_logo_label)
        self.sidebar_brand_name = QLabel(APP_NAME)
        self.sidebar_brand_name.setObjectName("sidebarBrandName")
        self.sidebar_brand_name.setStyleSheet(
            "color: #202124; font-size: 15px; font-weight: 700;"
        )
        brand_row.addWidget(self.sidebar_brand_name)
        toggle_row = QHBoxLayout()
        self.sidebar_toggle_button = QToolButton()
        self.sidebar_toggle_button.setObjectName("sidebarToggle")
        self.sidebar_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_toggle_button.setFixedSize(36, 36)
        self.sidebar_toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
        )
        self.sidebar_toggle_button.setIconSize(QSize(22, 22))
        self.sidebar_toggle_button.setIcon(self._sidebar_icon("panel"))
        self.sidebar_toggle_button.clicked.connect(self.toggle_sidebar)
        toggle_row.addWidget(self.sidebar_toggle_button)
        self.sidebar_toggle_row = toggle_row
        brand_stack.addLayout(brand_row)
        brand_stack.addLayout(toggle_row)
        sidebar_layout.addLayout(brand_stack)
        sidebar_layout.addSpacing(20)

        section_label = QLabel("WORKSPACE")
        self.sidebar_section_label = section_label
        section_label.setObjectName("sidebarSection")
        sidebar_layout.addWidget(section_label)

        def add_sidebar_action(label, callback):
            button = QPushButton()
            button.setObjectName("sidebarAction")
            button.setMinimumHeight(42)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            action_layout = QHBoxLayout(button)
            action_layout.setContentsMargins(14, 0, 12, 0)
            action_layout.setSpacing(12)
            icon_label = QLabel()
            icon_label.setFixedSize(24, 24)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            text_label = QLabel(label)
            text_label.setAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            text_label.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents
            )
            action_layout.addWidget(icon_label)
            action_layout.addWidget(text_label, 1)
            button.action_layout = action_layout
            button.icon_label = icon_label
            button.text_label = text_label
            button.clicked.connect(callback)
            sidebar_layout.addWidget(button)
            return button

        overview_button = add_sidebar_action(
            "Overview",
            self.show_dashboard,
        )
        overview_button.setObjectName("sidebarActiveAction")
        self.sidebar_nav_actions = [
            (overview_button, "Overview", "home"),
            (add_sidebar_action("", self.choose_folder), "Choose folder", "folder"),
            (add_sidebar_action("", self.scan_now), "Scan now", "scan"),
            (add_sidebar_action("", self.change_backup_location), "Telegram channel", "storage"),
            (add_sidebar_action("", self.show_upload_queue), "Upload queue", "queue"),
        ]
        sidebar_layout.addStretch()

        sidebar_layout.addWidget(self.about_button)
        sidebar_layout.addWidget(self.settings_button)
        sidebar_layout.addWidget(self.telegram_button)
        outer_layout.insertWidget(0, sidebar)

        self.update_telegram_indicator(False)

        root.addLayout(header)

        # Folder card

        folder_card = QFrame()

        folder_card.setObjectName(
            "card"
        )

        folder_layout = QVBoxLayout(
            folder_card
        )

        folder_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        folder_layout.setSpacing(8)

        folder_title = QLabel(
            "Folder to scan"
        )

        folder_title.setObjectName(
            "sectionTitle"
        )

        self.folder_label = QLabel(
            "No folder selected"
        )

        self.folder_label.setObjectName(
            "folderLabel"
        )

        folder_help = QLabel(
            "New files in this folder will be checked for backup."
        )
        folder_help.setObjectName("muted")
        folder_help.setWordWrap(True)

        self.folder_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        browse_button = QPushButton(
            "Choose Folder"
        )

        browse_button.clicked.connect(
            self.choose_folder
        )

        folder_layout.addWidget(
            folder_title
        )

        folder_layout.addWidget(folder_help)

        folder_layout.addWidget(
            self.folder_label
        )

        folder_layout.addWidget(
            browse_button
        )

        root.addWidget(
            folder_card
        )

        # Telegram backup channel card

        destination_card = QFrame()
        destination_card.setObjectName("card")

        destination_layout = QVBoxLayout(destination_card)
        destination_layout.setContentsMargins(18, 16, 18, 16)
        destination_layout.setSpacing(8)

        destination_title = QLabel("Telegram backup channel")
        destination_title.setObjectName("sectionTitle")

        destination_help = QLabel(
            "Your backups are stored in this private Telegram channel."
        )
        destination_help.setObjectName("muted")
        destination_help.setWordWrap(True)

        self.destination_label = QLabel("Not configured")
        self.destination_label.setObjectName("destinationLabel")
        self.destination_label.setWordWrap(True)

        destination_row = QHBoxLayout()
        destination_row.setSpacing(10)

        destination_row.addWidget(self.destination_label, 1)

        self.change_destination_button = QPushButton("Choose channel")
        self.change_destination_button.setFixedWidth(150)
        self.change_destination_button.setEnabled(False)
        self.change_destination_button.clicked.connect(
            self.change_backup_location
        )

        destination_row.addWidget(self.change_destination_button)

        destination_layout.addWidget(destination_title)
        destination_layout.addWidget(destination_help)
        destination_layout.addLayout(destination_row)

        root.addWidget(destination_card)

        self.update_destination_ui()

        # Summary

        summary = QHBoxLayout()

        self.detected_label = (
            self.make_summary(
                "Detected",
                "0",
            )
        )

        self.pending_label = (
            self.make_summary(
                "Pending",
                "0",
            )
        )

        self.uploaded_label = (
            self.make_summary(
                "Uploaded",
                "0",
            )
        )

        summary.addWidget(
            self.detected_label[0]
        )

        summary.addWidget(
            self.pending_label[0]
        )

        summary.addWidget(
            self.uploaded_label[0]
        )

        root.addLayout(
            summary
        )

        # Files

        self.queue_panel = QFrame()
        self.queue_panel.setObjectName("queuePanel")
        queue_panel_layout = QVBoxLayout(self.queue_panel)
        queue_panel_layout.setContentsMargins(14, 14, 14, 14)
        queue_panel_layout.setSpacing(12)

        queue_header = QHBoxLayout()

        queue_heading = QVBoxLayout()
        queue_heading.setSpacing(3)
        queue_title = QLabel("Files & uploads")

        queue_title.setObjectName(
            "sectionTitle"
        )

        queue_heading.addWidget(queue_title)
        queue_description = QLabel(
            "Review detected media and follow upload progress."
        )
        queue_description.setObjectName("muted")
        queue_heading.addWidget(queue_description)
        queue_header.addLayout(queue_heading)

        queue_header.addStretch()

        self.cancel_pending_button = QPushButton(
            "Cancel Pending"
        )

        self.cancel_pending_button.setFixedWidth(
            130
        )

        self.cancel_pending_button.setEnabled(
            False
        )

        self.cancel_pending_button.clicked.connect(
            self.cancel_pending_uploads
        )

        queue_header.addWidget(
            self.cancel_pending_button
        )

        queue_panel_layout.addLayout(queue_header)

        self.queue_container = QWidget()

        self.queue_container.setObjectName(
            "queueContainer"
        )

        self.queue_layout = QGridLayout(
            self.queue_container
        )

        self.queue_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.queue_layout.setHorizontalSpacing(12)
        self.queue_layout.setVerticalSpacing(12)
        self.queue_layout.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        queue_panel_layout.addWidget(self.queue_container, 1)
        root.addWidget(self.queue_panel, 1)

        # Bottom

        bottom = QHBoxLayout()

        self.last_scan = QLabel(
            "Last scan: Never"
        )

        self.last_scan.setObjectName(
            "muted"
        )

        scan_button = QPushButton(
            "Scan Now"
        )

        scan_button.clicked.connect(
            self.scan_now
        )

        bottom.addWidget(
            self.last_scan
        )

        bottom.addStretch()

        bottom.addWidget(
            scan_button
        )

        root.addLayout(
            bottom
        )

        if self.selected_folder:
            saved_folder = Path(
                self.selected_folder
            )

            if saved_folder.exists() and saved_folder.is_dir():
                self.folder_label.setText(
                    str(saved_folder)
                )

                if self.automatic_scan_enabled and not self.backup_paused:
                    if not self.auto_scan_timer.isActive():
                        self.auto_scan_timer.start()
            else:
                self.selected_folder = None
                self.settings.remove(
                    "backup/folder"
                )

        self.apply_style()
        self._apply_sidebar_state()

    def update_destination_ui(self):
        if self.backup_destination_available:
            title = self.backup_destination_title or "Telegram Channel"
            self.destination_label.setText(
                title
            )
            self.change_destination_button.setText("Change")
            self.change_destination_button.setEnabled(
                self.telegram_connected
            )
        elif self.backup_destination_id is not None:
            self.destination_label.setText(
                "Saved Telegram channel is unavailable"
            )
            self.change_destination_button.setText("Choose channel")
            self.change_destination_button.setEnabled(
                self.telegram_connected
            )
        else:
            self.destination_label.setText(
                "No channel selected"
            )
            self.change_destination_button.setText("Choose channel")
            self.change_destination_button.setEnabled(
                self.telegram_connected
            )

        if hasattr(self, "profile_destination_action"):
            if self.backup_destination_available:
                title = (
                    self.backup_destination_title or "Telegram channel"
                )
                self.profile_destination_action.setText(
                    f"Telegram backup channel: {title}"
                )
            elif self.backup_destination_id is not None:
                self.profile_destination_action.setText(
                    "Telegram backup channel: Unavailable"
                )
            else:
                self.profile_destination_action.setText(
                    "Telegram backup channel: Not selected"
                )
            self.profile_change_destination_action.setEnabled(
                self.telegram_connected
            )

    def change_backup_location(self):
        if not self.telegram_connected:
            QMessageBox.warning(
                self,
                "Telegram not connected",
                "Connect your Telegram account first.",
            )
            return

        if self.upload_in_progress:
            QMessageBox.information(
                self,
                "Upload in progress",
                "Please wait for the current upload to finish "
                "before changing the Telegram backup channel.",
            )
            return

        asyncio.create_task(
            self._change_backup_location()
        )

    async def _change_backup_location(self):
        self.change_destination_button.setEnabled(False)

        try:
            channels = await self.telegram.get_backup_channels()

            dialog = BackupLocationDialog(
                self,
                channels=channels,
                current_id=self.backup_destination_id,
            )

            result = await open_dialog(dialog)

            if result == QDialog.DialogCode.Rejected:
                self.update_destination_ui()
                return

            mode = dialog.result_mode()

            if mode == "select":
                channel_id = dialog.selected_channel_id()

                if channel_id is None:
                    return

                channel = await self.telegram.resolve_channel(
                    channel_id
                )

                if channel is None:
                    self.backup_destination_available = False

                    await self.show_async_message(
                        QMessageBox.Icon.Warning,
                        "Telegram backup channel",
                        "That Telegram channel is no longer "
                        "available.",
                    )
                    return

            elif mode == "create":
                channel_name = dialog.new_channel_name_value()

                if not channel_name:
                    return

                channel = await self.telegram.create_backup_channel(
                    channel_name
                )

            else:
                return

            self.telegram.set_upload_destination(
                channel["entity"]
            )

            self.backup_destination_id = channel["id"]
            self.backup_destination_title = channel["title"]
            self.backup_destination_available = True

            self.destination_store.save_channel(
                channel["id"],
                channel["title"],
            )

            self.update_destination_ui()

            self.status_label.setText(
                "● Telegram backup channel ready"
            )
            self.process_next_upload()

        except Exception as exc:
            await self.show_async_message(
                QMessageBox.Icon.Critical,
                "Telegram backup channel error",
                str(exc),
            )

            self.backup_destination_available = False
            self.update_destination_ui()

        finally:
            self.change_destination_button.setEnabled(
                self.telegram_connected
            )

    async def initialize_backup_location(self):
        """
        Restore the saved Telegram backup destination after login.
        Never falls back to Saved Messages.
        """

        saved_id = self.destination_store.get_id()

        if saved_id is None:
            self.backup_destination_id = None
            self.backup_destination_title = ""
            self.backup_destination_available = False

            self.update_destination_ui()

            if self.startup_mode and not self.isVisible():
                self.show_notification(
                    "Choose a private Telegram backup channel",
                    f"Open {APP_NAME} from the tray to finish setup.",
                    "warning",
                )
                return

            await self._change_backup_location()
            return

        self.backup_destination_id = saved_id
        self.backup_destination_title = (
            self.destination_store.get_title()
        )

        try:
            channel = await self.telegram.resolve_channel(
                saved_id
            )

            if channel is None:
                self.telegram.clear_upload_destination()

                self.backup_destination_available = False

                self.update_destination_ui()

                if self.startup_mode and not self.isVisible():
                    self.show_notification(
                        "Backup location unavailable",
                        f"Open {APP_NAME} from the tray and choose a private channel.",
                        "warning",
                    )
                    return

                await self.show_async_message(
                    QMessageBox.Icon.Warning,
                    "Telegram backup channel unavailable",
                    "Your saved Telegram backup channel "
                    "could not be found, accessed, or is no longer private.\n\n"
                    "Please choose a new Telegram backup channel.",
                )

                await self._change_backup_location()
                return

            self.telegram.set_upload_destination(
                channel["entity"]
            )

            self.backup_destination_id = channel["id"]
            self.backup_destination_title = channel["title"]
            self.backup_destination_available = True

            self.destination_store.save_channel(
                channel["id"],
                channel["title"],
            )

            self.update_destination_ui()
            self.process_next_upload()

        except Exception as exc:
            self.telegram.clear_upload_destination()

            self.backup_destination_available = False
            self.update_destination_ui()

            if self.startup_mode and not self.isVisible():
                self.show_notification(
                    "Backup location unavailable",
                    f"Open {APP_NAME} from the tray to check the destination.",
                    "warning",
                )
                return

            await self.show_async_message(
                QMessageBox.Icon.Warning,
                "Telegram backup channel unavailable",
                f"Could not verify the saved Telegram backup channel.\n\n"
                f"{exc}",
            )

    def auto_connect_telegram(self):
        """
        Automatically reconnect using the saved Telegram session.
        If the session is not authorized, do nothing and let the
        user connect manually.
        """

        if self.telegram_connecting or self.telegram_connected:
            return
        self.telegram_connecting = True
        self.telegram_button.setEnabled(False)
        asyncio.create_task(self._auto_connect_telegram())

    async def _auto_connect_telegram(self):
        try:
            if not self.telegram.has_credentials():
                self.status_label.setText(
                    "● Ready - Connect Telegram"
                )
                return

            self.status_label.setText(
                "● Connecting Telegram..."
            )

            authorized = await self.telegram.connect()

            if not authorized:
                self.status_label.setText(
                    "● Ready - Connect Telegram"
                )
                if self.startup_mode and not self.isVisible():
                    self.show_notification(
                        "Telegram sign-in required",
                        f"Open {APP_NAME} from the tray and connect Telegram.",
                        "warning",
                    )
                return

            await self.telegram_connected_success()

        except Exception as exc:
            self.telegram_connected = False
            self.update_telegram_indicator(False)

            self.status_label.setText(
                "● Telegram connection unavailable"
            )

            if self.startup_mode and not self.isVisible():
                self.show_notification(
                    "Telegram connection unavailable",
                    f"{APP_NAME} will try again at the next backup interval.",
                    "warning",
                )

            self.telegram_button.setEnabled(
                True
            )

            print(
                f"Automatic Telegram connection failed: {exc}"
            )
        finally:
            self.telegram_connecting = False
            self.telegram_button.setEnabled(True)

    def connect_telegram(self):
        if self.telegram_connecting:
            return
        self.telegram_connecting = True
        self.telegram_button.setEnabled(False)
        asyncio.create_task(self._connect_telegram())

    async def show_async_message(self, icon, title, message):
        """Show a message without starting a nested Qt event loop."""
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(message)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        await open_dialog(box)

    async def _connect_telegram(self):
        dialog = None

        self.status_label.setText(
            "● Connecting..."
        )

        try:
            authorized = await self.telegram.connect()

            if authorized:
                await self.telegram_connected_success()
                return

            dialog = TelegramLoginDialog(self)
            saved_credentials = get_credentials()
            if saved_credentials:
                dialog.api_id_input.setText(saved_credentials[0])
                dialog.api_hash_input.setText(saved_credentials[1])

            result = await open_dialog(dialog, delete_on_finish=False)

            if result != QDialog.DialogCode.Accepted:
                self.telegram_button.setEnabled(
                    True
                )

                self.status_label.setText(
                    "● Ready"
                )

                return

            try:
                credentials_changed = (
                    str(self.telegram.api_id or "") != dialog.api_id()
                    or self.telegram.api_hash != dialog.api_hash()
                )
                if (
                    credentials_changed
                    and self.telegram.client is not None
                    and self.telegram.client.is_connected()
                ):
                    await self.telegram.disconnect()
                self.telegram.configure_credentials(
                    dialog.api_id(),
                    dialog.api_hash(),
                )
                save_credentials(
                    dialog.api_id(),
                    dialog.api_hash(),
                )
            except Exception as exc:
                await self.show_async_message(
                    QMessageBox.Icon.Critical,
                    "Telegram API credentials",
                    f"Could not save or use these credentials.\n\n{exc}",
                )
                return

            await self.telegram.connect()

            phone = dialog.phone()

            if not phone:
                await self.show_async_message(
                    QMessageBox.Icon.Warning,
                    "Telegram",
                    "Phone number is required.",
                )

                self.telegram_button.setEnabled(
                    True
                )

                self.status_label.setText(
                    "● Ready"
                )

                return

            sent_code = await self.telegram.request_code(
                phone
            )

            dialog.show_code_step()

            result = await open_dialog(dialog, delete_on_finish=False)

            if result != QDialog.DialogCode.Accepted:
                self.telegram_button.setEnabled(
                    True
                )

                self.status_label.setText(
                    "● Ready"
                )

                return

            code = dialog.code()

            try:
                await self.telegram.sign_in(
                    phone,
                    code,
                    sent_code.phone_code_hash,
                )

            except SessionPasswordNeededError:

                dialog.show_password_step()

                result = await open_dialog(dialog, delete_on_finish=False)

                if result != QDialog.DialogCode.Accepted:
                    self.telegram_button.setEnabled(
                        True
                    )

                    self.status_label.setText(
                        "● Ready"
                    )

                    return

                await self.telegram.sign_in_password(
                    dialog.password()
                )

            me = await self.telegram.get_me()

            name = (
                me.first_name
                or me.username
                or "Telegram"
            )

            self.telegram_connected = True
            self.telegram_user = me
            self.update_telegram_indicator(True)
            await self._load_telegram_profile_photo()

            self.update_profile_button_text()
            self.telegram_button.setEnabled(True)

            self.status_label.setText(
                f"● Connected as {name}"
            )

            await self.initialize_backup_location()

        except PhoneNumberInvalidError:

            await self.show_async_message(
                QMessageBox.Icon.Critical,
                "Telegram Login",
                "The phone number is invalid.",
            )

            self.telegram_button.setEnabled(
                True
            )

            self.status_label.setText(
                "● Ready"
            )

        except PhoneCodeInvalidError:

            await self.show_async_message(
                QMessageBox.Icon.Critical,
                "Telegram Login",
                "The Telegram login code is invalid.",
            )

            self.telegram_button.setEnabled(
                True
            )

            self.status_label.setText(
                "● Ready"
            )

        except PhoneCodeExpiredError:

            await self.show_async_message(
                QMessageBox.Icon.Critical,
                "Telegram Login",
                "The Telegram login code has expired.",
            )

            self.telegram_button.setEnabled(
                True
            )

            self.status_label.setText(
                "● Ready"
            )

        except Exception as exc:

            await self.show_async_message(
                QMessageBox.Icon.Critical,
                "Telegram Error",
                str(exc),
            )

            self.telegram_button.setEnabled(
                True
            )

            self.status_label.setText(
                "● Ready"
            )

        finally:
            if dialog is not None:
                dialog.deleteLater()
            self.telegram_connecting = False
            self.telegram_button.setEnabled(True)

    async def telegram_connected_success(self):

        me = await self.telegram.get_me()

        name = (
            me.first_name
            or me.username
            or "Telegram"
        )

        self.telegram_connected = True
        self.telegram_user = me
        self.update_telegram_indicator(True)
        await self._load_telegram_profile_photo()

        self.update_profile_button_text()
        self.telegram_button.setEnabled(True)

        self.status_label.setText(
            f"● Connected as {name}"
        )

        self.update_destination_ui()

        await self.initialize_backup_location()

        if self.startup_mode:
            if (
                self.automatic_scan_enabled
                and self.selected_folder
                and self.backup_destination_available
            ):
                QTimer.singleShot(250, self.auto_scan)
            elif self.automatic_scan_enabled and not self.selected_folder:
                self.show_notification(
                    "Automatic backup needs setup",
                    f"Choose a folder to scan in {APP_NAME}.",
                    "warning",
                )

    def update_telegram_indicator(self, connected):
        if self.telegram_button.icon().isNull():
            self.telegram_button.setIcon(self._sidebar_icon("user"))
        if connected:
            if hasattr(self, "profile_logout_action"):
                self.profile_logout_action.setEnabled(True)
            if hasattr(self, "profile_change_destination_action"):
                self.profile_change_destination_action.setEnabled(True)

            self.telegram_button.setToolTip(
                "View Telegram account"
            )
        else:
            if hasattr(self, "profile_logout_action"):
                self.profile_logout_action.setEnabled(False)
            if hasattr(self, "profile_change_destination_action"):
                self.profile_change_destination_action.setEnabled(False)

            self.telegram_button.setToolTip(
                "Connect Telegram"
            )
        self.update_profile_button_text()

    def update_profile_button_text(self):
        if self.sidebar_collapsed:
            self.telegram_button.setText(
                "" if not self.telegram_button.icon().isNull() else "👤"
            )
            return
        if not self.telegram_connected or self.telegram_user is None:
            self.telegram_button.setText("Connect Telegram")
            return

        username = getattr(self.telegram_user, "username", None)
        display_name = " ".join(
            part
            for part in (
                getattr(self.telegram_user, "first_name", None),
                getattr(self.telegram_user, "last_name", None),
            )
            if part
        )
        account_name = f"@{username}" if username else display_name
        account_name = account_name or "Telegram account"
        if len(account_name) > 20:
            account_name = account_name[:19] + "…"
        self.telegram_button.setText(account_name)

    def handle_telegram_button_click(self):
        if self.telegram_connected:
            self.show_telegram_profile()
        else:
            self.connect_telegram()

    def show_telegram_profile(self):
        user = self.telegram_user
        if user is None:
            account_label = "Telegram account unavailable"
        elif user.username:
            account_label = f"@{user.username}"
        else:
            account_label = " ".join(
                part for part in (user.first_name, user.last_name) if part
            ) or "Telegram account"

        self.profile_account_action.setText(account_label)
        position = self.telegram_button.mapToGlobal(
            QPoint(
                self.telegram_button.width() + 8
                if self.sidebar_collapsed
                else self.telegram_button.width()
                - self.profile_menu.sizeHint().width(),
                self.telegram_button.height()
                - self.profile_menu.sizeHint().height()
                if self.sidebar_collapsed
                else -self.profile_menu.sizeHint().height(),
            )
        )
        self.profile_menu.popup(position)

    def toggle_sidebar(self):
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.settings.setValue("ui/sidebar_collapsed", self.sidebar_collapsed)
        self.settings.sync()
        self._apply_sidebar_state()

    def show_about_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(f"About {APP_NAME}")
        dialog.setMinimumWidth(460)
        dialog.setStyleSheet("""
            QDialog { background: #f7f8fa; color: #202124; }
            QLabel { background: transparent; color: #202124; }
            QLabel a { color: #202124; text-decoration: none; }
            QLabel a:hover { color: #202124; text-decoration: none; }
            QLabel#aboutTitle { font-size: 21px; font-weight: 700; }
            QLabel#aboutMuted { color: #5f6368; }
            QPushButton {
                background: #1a73e8; color: #ffffff; border: none;
                border-radius: 9px; padding: 9px 16px; font-weight: 600;
            }
            QPushButton:hover { background: #1765cc; }
            QPushButton#aboutClose {
                background: #e8eaed; color: #202124;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(9)

        header = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(52, 52)
        logo.setPixmap(app_icon().pixmap(QSize(48, 48)))
        header.addWidget(logo)

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        name = QLabel(APP_NAME)
        name.setObjectName("aboutTitle")
        tagline = QLabel("Your files, safely kept.")
        tagline.setObjectName("aboutMuted")
        title_column.addWidget(name)
        title_column.addWidget(tagline)
        header.addLayout(title_column, 1)
        layout.addLayout(header)

        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setObjectName("aboutMuted")
        layout.addWidget(version_label)

        developer_label = QLabel(f"Developer: {DEVELOPER_NAME}")
        layout.addWidget(developer_label)

        social_links = QHBoxLayout()
        social_links.setContentsMargins(0, 0, 0, 0)
        social_links.setSpacing(18)

        def add_social_link(label, url, icon_svg):
            link = QLabel(
                f'<a href="{url}" style="text-decoration:none">{label}</a>'
            )
            link.setOpenExternalLinks(True)
            link_palette = link.palette()
            link_palette.setColor(
                QPalette.ColorRole.Link,
                QColor("#202124"),
            )
            link_palette.setColor(
                QPalette.ColorRole.LinkVisited,
                QColor("#202124"),
            )
            link.setPalette(link_palette)
            icon_label = QLabel()
            icon_label.setFixedSize(18, 18)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            renderer = QSvgRenderer(QByteArray(icon_svg.encode("utf-8")))
            pixmap = QPixmap(18, 18)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter)
            painter.end()
            icon_label.setPixmap(pixmap)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            row.addWidget(icon_label)
            row.addWidget(link)
            social_links.addLayout(row)

        add_social_link(
            "GitHub",
            DEVELOPER_GITHUB_URL,
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="#24292f"><path d="M12 .8a11.2 11.2 0 0 0-3.54 21.83c.56.1.76-.24.76-.54v-2.1c-3.1.68-3.76-1.32-3.76-1.32-.5-1.28-1.23-1.62-1.23-1.62-1.01-.69.08-.68.08-.68 1.12.08 1.71 1.15 1.71 1.15 1 .1.76 2.1 3.46 1.48.1-.72.4-1.21.72-1.49-2.48-.28-5.09-1.24-5.09-5.53 0-1.22.44-2.22 1.15-3-.12-.28-.5-1.42.11-2.96 0 0 .94-.3 3.08 1.14a10.7 10.7 0 0 1 5.6 0c2.13-1.44 3.07-1.14 3.07-1.14.62 1.54.23 2.68.12 2.96.71.78 1.14 1.78 1.14 3 0 4.3-2.61 5.25-5.1 5.53.4.35.76 1.02.76 2.06v3.12c0 .3.2.65.77.54A11.2 11.2 0 0 0 12 .8z"/></svg>',
        )
        add_social_link(
            "Facebook",
            DEVELOPER_FACEBOOK_URL,
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
            'fill="#1877f2"><path d="M24 12a12 12 0 1 0-13.88 11.86v-8.39H7.08V12h3.04V9.35c0-3 1.79-4.66 4.52-4.66 1.31 0 2.68.23 2.68.23v2.95h-1.51c-1.49 0-1.95.93-1.95 1.88V12h3.32l-.53 3.47h-2.79v8.39A12 12 0 0 0 24 12z"/></svg>',
        )
        social_links.addStretch(1)
        layout.addLayout(social_links)

        project_link = QLabel(
            f'<a href="{GITHUB_REPOSITORY_URL}">VaultHaven project</a>'
        )
        project_link.setOpenExternalLinks(True)
        project_link_palette = project_link.palette()
        project_link_palette.setColor(
            QPalette.ColorRole.Link,
            QColor("#202124"),
        )
        project_link_palette.setColor(
            QPalette.ColorRole.LinkVisited,
            QColor("#202124"),
        )
        project_link.setPalette(project_link_palette)
        layout.addWidget(project_link)

        credit_label = QLabel(
            "Made with assistance from ChatGPT and OpenAI Codex."
        )
        credit_label.setObjectName("aboutMuted")
        credit_label.setWordWrap(True)
        layout.addWidget(credit_label)

        buttons = QHBoxLayout()
        update_button = QPushButton("Check for updates")
        update_button.clicked.connect(
            lambda: self.check_for_updates(dialog, update_button)
        )
        close_button = QPushButton("Close")
        close_button.setObjectName("aboutClose")
        close_button.clicked.connect(dialog.close)
        buttons.addWidget(update_button)
        buttons.addStretch()
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

        self._about_dialog = dialog
        dialog.open()

    def check_for_updates(self, dialog, button):
        if not GITHUB_REPOSITORY_URL:
            QMessageBox.information(
                dialog,
                "Update check unavailable",
                "Set the public GitHub repository URL to enable release checks.",
            )
            return

        button.setEnabled(False)
        button.setText("Checking...")
        worker = ReleaseCheckWorker(GITHUB_REPOSITORY_URL, self)
        worker.result_ready.connect(
            lambda version, url, error: self._show_update_result(
                dialog, button, version, url, error
            )
        )
        self._release_check_worker = worker
        worker.start()

    def _show_update_result(self, dialog, button, latest_version, release_url, error):
        button.setEnabled(True)
        button.setText("Check for updates")

        if error:
            QMessageBox.information(dialog, "Update check", error)
            return

        current_numbers = tuple(
            int(value) for value in re.findall(r"\d+", APP_VERSION)[:3]
        )
        latest_numbers = tuple(
            int(value) for value in re.findall(r"\d+", latest_version)[:3]
        )
        current_numbers += (0,) * (3 - len(current_numbers))
        latest_numbers += (0,) * (3 - len(latest_numbers))

        message = QMessageBox(dialog)
        message.setWindowTitle("VaultHaven updates")
        message.setTextFormat(Qt.TextFormat.RichText)
        if latest_numbers > current_numbers:
            message.setIcon(QMessageBox.Icon.Information)
            message.setText(
                f"A newer version is available: <b>{latest_version}</b>.<br>"
                f'<a href="{release_url}">Open the GitHub release</a> '
                "to download it."
            )
        else:
            message.setIcon(QMessageBox.Icon.Information)
            message.setText(
                f"VaultHaven is up to date (version {APP_VERSION})."
            )
        message.setStandardButtons(QMessageBox.StandardButton.Ok)
        message.open()

    @staticmethod
    def _sidebar_icon(name, color="#5f6368"):
        paths = {
            "panel": (
                '<rect x="3.5" y="4.5" width="17" height="15" rx="2" />'
                '<path d="M9 5v14" />'
            ),
            "home": (
                '<path d="m3.5 10 8.5-7 8.5 7" />'
                '<path d="M5.5 9v11h13V9" />'
                '<path d="M9.5 20v-6h5v6" />'
            ),
            "folder": (
                '<path d="M3.5 7.5h6l2 2h9v9a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />'
                '<path d="M3.5 8V5.5a2 2 0 0 1 2-2h4l2 2h6" />'
            ),
            "scan": (
                '<path d="M20 11a8 8 0 0 0-14.8-4L3.5 9" />'
                '<path d="M3.5 4.5V9h4.5" />'
                '<path d="M4 13a8 8 0 0 0 14.8 4l1.7-2" />'
                '<path d="M20.5 19.5V15H16" />'
            ),
            "storage": (
                '<rect x="3.5" y="4" width="17" height="16" rx="2" />'
                '<path d="M3.5 9h17M8 14h.01M11 14h5" />'
            ),
            "queue": (
                '<path d="M8 6h12M8 12h12M8 18h12" />'
                '<path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" />'
            ),
            "settings": (
                '<circle cx="12" cy="12" r="8" />'
                '<circle cx="12" cy="12" r="3" />'
                '<path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42m0-14.14-1.42 1.42m-11.3 11.3-1.42 1.42" />'
            ),
            "info": (
                '<circle cx="12" cy="12" r="9" />'
                '<path d="M12 11v5M12 8h.01" />'
            ),
            "user": (
                '<circle cx="12" cy="8" r="3.5" />'
                '<path d="M5 20a7 7 0 0 1 14 0" />'
            ),
        }
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" '
            f'viewBox="0 0 24 24" fill="none" stroke="{color}" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'{paths[name]}</svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)

    def _apply_sidebar_state(self):
        collapsed = self.sidebar_collapsed
        width = 72 if collapsed else 236
        self.sidebar.setFixedWidth(width)
        # Align the expanded logo/toggle centers with the navigation icon column.
        row_left_indent = 0 if collapsed else 7
        self.sidebar_brand_row.setContentsMargins(
            row_left_indent, 0, 0, 0
        )
        self.sidebar_toggle_row.setContentsMargins(
            row_left_indent, 0, 0, 0
        )
        self.sidebar_brand_row.setSpacing(0 if collapsed else 8)
        row_alignment = (
            Qt.AlignmentFlag.AlignHCenter
            if collapsed
            else Qt.AlignmentFlag.AlignLeft
        )
        self.sidebar_brand_row.setAlignment(row_alignment)
        self.sidebar_toggle_row.setAlignment(row_alignment)
        self.sidebar_logo_label.setFixedSize(
            32 if collapsed else 34,
            32 if collapsed else 34,
        )
        self.sidebar_logo_label.setPixmap(
            app_icon().pixmap(
                QSize(30, 30) if collapsed else QSize(32, 32)
            )
        )
        self.sidebar_brand_name.setVisible(not collapsed)
        self.sidebar_toggle_button.setFixedSize(
            34 if collapsed else 36,
            34 if collapsed else 36,
        )
        self.sidebar_toggle_button.setIconSize(
            QSize(22, 22)
        )
        self.sidebar_layout.setContentsMargins(
            10 if collapsed else 16, 20, 10 if collapsed else 16, 16
        )
        self.sidebar_section_label.setVisible(not collapsed)
        self.sidebar_toggle_button.setIcon(self._sidebar_icon("panel"))
        self.sidebar_toggle_button.setToolTip(
            "Expand sidebar" if collapsed else "Collapse sidebar"
        )
        self.sidebar_toggle_button.setStyleSheet(
            "QToolButton { background: #ffffff; color: #3c4043; "
            "border: 1px solid #dadce0; border-radius: 10px; "
            "font-size: 24px; font-weight: 500; }"
            "QToolButton:hover { background: #e8eaed; border-color: #c6cbd1; }"
            "QToolButton:pressed { background: #dadce0; }"
        )

        for button, label, icon_name in self.sidebar_nav_actions:
            button.setText("")
            button.text_label.setText(label)
            button.text_label.setVisible(not collapsed)
            icon_color = "#202124" if button is self.sidebar_nav_actions[0][0] else "#5f6368"
            icon_size = 26 if collapsed else 22
            button.icon_label.setFixedSize(icon_size, icon_size)
            button.icon_label.setPixmap(
                self._sidebar_icon(icon_name, icon_color).pixmap(
                    QSize(icon_size, icon_size)
                )
            )
            button.action_layout.setContentsMargins(
                0 if collapsed else 14, 0, 0 if collapsed else 12, 0
            )
            button.action_layout.setSpacing(0 if collapsed else 12)
            button.action_layout.setAlignment(
                Qt.AlignmentFlag.AlignCenter
                if collapsed
                else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
            button.setToolTip(label)
            button.setObjectName(
                "sidebarCollapsedAction" if collapsed
                else "sidebarActiveAction" if button is self.sidebar_nav_actions[0][0]
                else "sidebarAction"
            )
            button.setMinimumWidth(48)
        self.settings_button.setFixedWidth(48 if collapsed else 204)
        self.settings_button.setText("")
        self.settings_text_label.setVisible(not collapsed)
        settings_icon_size = 26 if collapsed else 22
        self.settings_icon_label.setFixedSize(
            settings_icon_size, settings_icon_size
        )
        self.settings_icon_label.setPixmap(
            self._sidebar_icon("settings").pixmap(
                QSize(settings_icon_size, settings_icon_size)
            )
        )
        self.settings_action_layout.setContentsMargins(
            0 if collapsed else 14, 0, 0 if collapsed else 12, 0
        )
        self.settings_action_layout.setSpacing(0 if collapsed else 12)
        self.settings_action_layout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
            if collapsed
            else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.settings_button.setToolTip("Settings")
        self.settings_button.setStyleSheet(self._sidebar_tool_button_style(collapsed))
        self.about_button.setFixedWidth(48 if collapsed else 204)
        self.about_text_label.setVisible(not collapsed)
        about_icon_size = 26 if collapsed else 22
        self.about_icon_label.setFixedSize(about_icon_size, about_icon_size)
        self.about_icon_label.setPixmap(
            self._sidebar_icon("info").pixmap(
                QSize(about_icon_size, about_icon_size)
            )
        )
        self.about_action_layout.setContentsMargins(
            0 if collapsed else 14, 0, 0 if collapsed else 12, 0
        )
        self.about_action_layout.setSpacing(0 if collapsed else 12)
        self.about_action_layout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
            if collapsed
            else Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
        )
        self.about_button.setToolTip("About VaultHaven")
        self.about_button.setStyleSheet(self._sidebar_tool_button_style(collapsed))
        self.telegram_button.setFixedWidth(48 if collapsed else 204)
        self.telegram_button.setStyleSheet(
            self._sidebar_tool_button_style(collapsed, profile=True)
        )
        self.telegram_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonIconOnly
            if collapsed
            else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.telegram_button.setIconSize(
            QSize(26 if collapsed else 22, 26 if collapsed else 22)
        )
        if self.telegram_profile_photo is not None:
            self._set_telegram_profile_icon()
        self.update_profile_button_text()

    @staticmethod
    def _sidebar_tool_button_style(collapsed, profile=False):
        radius = 12 if profile else 10
        padding = "0" if collapsed or not profile else "0 12px"
        alignment = "center" if collapsed else "left"
        font_size = 22 if collapsed else (13 if profile else 14)
        return f"""
            QToolButton {{ background: transparent; color: #202124;
                border: 1px solid transparent; border-radius: {radius}px;
                padding: {padding}; text-align: {alignment};
                font-size: {font_size}px; }}
            QToolButton:hover {{ background: #e8eaed; }}
            QToolButton:pressed {{ background: #dadce0; }}
            QToolButton:disabled {{ background: #f1f3f4; color: #202124; }}
        """

    async def _load_telegram_profile_photo(self):
        """Download and display the signed-in Telegram account photo."""
        if not self.telegram_user:
            self.telegram_button.setIcon(self._sidebar_icon("user"))
            return

        try:
            cache_dir = Path(
                QStandardPaths.writableLocation(
                    QStandardPaths.StandardLocation.CacheLocation
                )
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            photo_path = cache_dir / "telegram-profile-photo.jpg"
            result = await self.telegram.client.download_profile_photo(
                self.telegram_user,
                file=str(photo_path),
                download_big=True,
            )
            if result and photo_path.is_file():
                photo = QPixmap(str(photo_path))
                if not photo.isNull():
                    self.telegram_profile_photo = photo
                    self._set_telegram_profile_icon()
                    return
        except Exception as exc:
            print(f"Could not load Telegram profile photo: {exc}")

        self.telegram_button.setIcon(self._sidebar_icon("user"))

    def _set_telegram_profile_icon(self):
        if self.telegram_profile_photo is None:
            return

        size = 26 if self.sidebar_collapsed else 22
        scaled = self.telegram_profile_photo.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        left = (scaled.width() - size) // 2
        top = (scaled.height() - size) // 2
        circle = QPixmap(size, size)
        circle.fill(Qt.GlobalColor.transparent)
        painter = QPainter(circle)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, scaled, left, top, size, size)
        painter.end()
        self.telegram_button.setIcon(QIcon(circle))
        self.telegram_button.setIconSize(QSize(size, size))

    def make_summary(
        self,
        title,
        value,
    ):

        card = QFrame()

        card.setObjectName(
            "summaryCard"
        )
        card.setProperty("metricType", title.lower())

        layout = QVBoxLayout(
            card
        )

        layout.setContentsMargins(
            18,
            15,
            18,
            15,
        )
        layout.setSpacing(6)

        title_label = QLabel(
            title
        )

        title_label.setObjectName(
            "summaryTitle"
        )

        value_label = QLabel(
            value
        )

        value_label.setObjectName(
            "summaryValue"
        )

        layout.addWidget(
            title_label
        )

        layout.addWidget(
            value_label
        )

        return (
            card,
            value_label,
        )

    def choose_folder(self):

        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Scan",
            self.selected_folder
            or str(Path.home()),
        )

        if folder:

            self.selected_folder = folder

            self.settings.setValue(
                "backup/folder",
                folder,
            )
            self.settings.sync()

            self.folder_label.setText(
                folder
            )

            self.status_label.setText(
                "● Ready"
            )

            if self.automatic_scan_enabled and not self.backup_paused:
                if not self.auto_scan_timer.isActive():
                    self.auto_scan_timer.start()

    def show_settings_menu(self):
        position = self.settings_button.mapToGlobal(
            QPoint(
                self.settings_button.width() + 8 if self.sidebar_collapsed else 0,
                self.settings_button.height() - self.settings_menu.sizeHint().height()
                if self.sidebar_collapsed
                else -self.settings_menu.sizeHint().height(),
            )
        )
        self.settings_menu.popup(position)

    def show_upload_queue(self):
        self.dashboard_scroll.ensureWidgetVisible(self.queue_panel)

    def build_settings_menu(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        startup_row = QHBoxLayout()
        startup_text = QVBoxLayout()
        startup_label = QLabel("Windows Startup")
        startup_label.setObjectName("fileName")
        startup_description = QLabel(
            "Start in the tray at sign-in; closing the window keeps it running while enabled."
        )
        startup_description.setObjectName("muted")
        startup_description.setWordWrap(True)
        startup_text.addWidget(startup_label)
        startup_text.addWidget(startup_description)
        startup_row.addLayout(startup_text, 1)

        self.startup_toggle = SettingsToggle(
            is_startup_enabled()
        )
        self.startup_toggle.toggled.connect(
            self.toggle_windows_startup
        )
        startup_row.addWidget(self.startup_toggle)
        layout.addLayout(startup_row)

        scan_toggle_row = QHBoxLayout()
        scan_toggle_text = QVBoxLayout()
        scan_toggle_label = QLabel("Automatic Backup")
        scan_toggle_label.setObjectName("fileName")
        scan_toggle_description = QLabel(
            f"Scan and upload new files at the chosen interval while {APP_NAME} is running."
        )
        scan_toggle_description.setObjectName("muted")
        scan_toggle_description.setWordWrap(True)
        scan_toggle_text.addWidget(scan_toggle_label)
        scan_toggle_text.addWidget(scan_toggle_description)
        scan_toggle_row.addLayout(scan_toggle_text, 1)

        self.automatic_scan_toggle = SettingsToggle(
            self.automatic_scan_enabled
        )
        self.automatic_scan_toggle.toggled.connect(
            self.toggle_automatic_scan
        )
        scan_toggle_row.addWidget(self.automatic_scan_toggle)
        layout.addLayout(scan_toggle_row)

        interval_row = QHBoxLayout()
        interval_title = QLabel("Backup interval")
        interval_title.setObjectName("muted")
        self.auto_backup_interval_label = QLabel()
        self.auto_backup_interval_label.setObjectName("muted")
        interval_row.addWidget(interval_title)
        interval_row.addStretch(1)
        interval_row.addWidget(self.auto_backup_interval_label)
        layout.addLayout(interval_row)

        self.auto_backup_interval_slider = QSlider(Qt.Orientation.Horizontal)
        self.auto_backup_interval_slider.setRange(1, 1440)
        self.auto_backup_interval_slider.setSingleStep(1)
        self.auto_backup_interval_slider.setPageStep(15)
        self.auto_backup_interval_slider.setTickInterval(60)
        self.auto_backup_interval_slider.setTickPosition(
            QSlider.TickPosition.TicksBelow
        )
        self.auto_backup_interval_slider.setValue(
            self.auto_backup_interval_minutes
        )
        self.auto_backup_interval_slider.valueChanged.connect(
            self.set_auto_backup_interval
        )
        layout.addWidget(self.auto_backup_interval_slider)
        self.update_auto_backup_interval_label(
            self.auto_backup_interval_minutes
        )

        action = QWidgetAction(self.settings_menu)
        action.setDefaultWidget(panel)
        self.settings_menu.addAction(action)

    def logout_telegram(self):
        if not self.telegram_connected:
            return

        if self.upload_in_progress or self.upload_queue:
            QMessageBox.warning(
                self,
                "Telegram Logout",
                "Please wait until the current upload queue is finished "
                "before logging out.",
            )
            return

        answer = QMessageBox.question(
            self,
            "Log out Telegram",
            "Are you sure you want to log out of this Telegram account?\n\n"
            f"You will need to sign in again before {APP_NAME} can upload files.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.profile_menu.close()
        self.profile_logout_action.setEnabled(False)
        self.status_label.setText("● Logging out...")

        asyncio.create_task(
            self._logout_telegram()
        )

    async def _logout_telegram(self):
        try:
            if self.telegram.client.is_connected():
                await self.telegram.client.log_out()

        except Exception as exc:
            await self.show_async_message(
                QMessageBox.Icon.Critical,
                "Telegram Logout",
                f"Could not log out of Telegram.\n\n{exc}",
            )
            self.profile_logout_action.setEnabled(True)
            self.status_label.setText(
                "● Telegram logout failed"
            )
            return

        self.telegram.clear_upload_destination()
        self.destination_store.clear()

        self.telegram_connected = False
        self.telegram_user = None
        self.telegram_profile_photo = None
        self.telegram_button.setIcon(QIcon())
        self.backup_destination_id = None
        self.backup_destination_title = ""
        self.backup_destination_available = False

        self.update_telegram_indicator(False)
        self.telegram_button.setEnabled(True)
        self.update_destination_ui()

        self.profile_logout_action.setEnabled(False)
        self.status_label.setText(
            "● Logged out of Telegram"
        )

    def toggle_automatic_scan(self, enabled):
        self.automatic_scan_enabled = bool(enabled)
        self.settings.setValue(
            "backup/automatic_scan_enabled",
            self.automatic_scan_enabled,
        )
        self.settings.sync()

        if self.automatic_scan_enabled:
            if self.selected_folder and not self.backup_paused:
                self.auto_scan_timer.start(
                    self.auto_backup_interval_minutes * 60 * 1000
                )
                self.status_label.setText("● Automatic Scan enabled")
            elif not self.selected_folder:
                self.auto_scan_timer.stop()
                self.status_label.setText("● Choose a folder to enable scanning")
            else:
                self.status_label.setText("● Automatic Scan enabled")
        else:
            self.auto_scan_timer.stop()
            self.status_label.setText("● Automatic Scan disabled")

    def update_auto_backup_interval_label(self, minutes):
        minutes = int(minutes)
        if minutes < 60:
            label = f"{minutes} minute" + ("s" if minutes != 1 else "")
        elif minutes % 60 == 0:
            hours = minutes // 60
            label = f"{hours} hour" + ("s" if hours != 1 else "")
        else:
            label = f"{minutes // 60}h {minutes % 60}m"
        self.auto_backup_interval_label.setText(label)

    def set_auto_backup_interval(self, minutes):
        self.auto_backup_interval_minutes = max(1, min(1440, int(minutes)))
        self.settings.setValue(
            "backup/interval_minutes",
            self.auto_backup_interval_minutes,
        )
        self.settings.sync()
        self.update_auto_backup_interval_label(
            self.auto_backup_interval_minutes
        )
        self.auto_scan_timer.setInterval(
            self.auto_backup_interval_minutes * 60 * 1000
        )
        if self.auto_scan_timer.isActive():
            self.auto_scan_timer.start()

    def toggle_windows_startup(self, enabled):
        try:
            if enabled:
                enable_startup()

                self.settings.setValue(
                    "startup/enabled",
                    True,
                )

                self.settings.sync()

                self.status_label.setText(
                    "● Windows startup enabled"
                )

            else:
                disable_startup()

                self.settings.setValue(
                    "startup/enabled",
                    False,
                )

                self.settings.sync()

                self.status_label.setText(
                    "● Windows startup disabled"
                )

        except Exception as exc:
            self.startup_toggle.blockSignals(True)

            self.startup_toggle.setChecked(
                not enabled
            )

            self.startup_toggle.blockSignals(False)

            QMessageBox.critical(
                self,
                "Windows Startup",
                f"Could not change Windows startup setting.\n\n"
                f"{exc}",
            )

    def auto_scan(self):
        """
        Automatically scan and upload on the configured interval.
        """

        if self.backup_paused:
            return

        if not self.automatic_scan_enabled:
            return

        if not self.selected_folder:
            return

        if not self.telegram_connected:
            self.status_label.setText(
                "● Automatic backup waiting for Telegram connection"
            )
            self.auto_connect_telegram()
            return

        if not self.backup_destination_available:
            self.status_label.setText(
                "● Automatic backup waiting for a private destination"
            )
            return

        # Never interrupt an active upload queue.
        if self.upload_in_progress or self.upload_queue:
            return

        if (
            self.scan_thread
            and self.scan_thread.isRunning()
        ):
            return

        self.status_label.setText("● Automatic backup scanning...")
        self.scan_now(automatic=True)

    def scan_now(self, automatic=False):

        if (
            self.scan_thread
            and self.scan_thread.isRunning()
        ):
            return

        if not self.selected_folder:

            self.status_label.setText(
                "● Select a folder"
            )

            return

        self._scan_auto_upload = bool(automatic)

        self.clear_cards()

        try:
            uploaded_signatures = self.db.get_uploaded_file_signatures(
                self.backup_destination_id
            )
        except Exception as exc:
            uploaded_signatures = {}
            print(f"Could not load uploaded-file scan index: {exc}")

        self.status_label.setText(
            "● Scanning..."
        )

        self.last_scan.setText(
            "Scanning..."
        )

        self.scan_thread = QThread(
            self
        )

        self.scan_worker = ScanWorker(
            self.selected_folder,
            self.backup_destination_id,
            uploaded_signatures=uploaded_signatures,
        )

        self.scan_worker.moveToThread(
            self.scan_thread
        )

        self.scan_thread.started.connect(
            self.scan_worker.run
        )

        self.scan_worker.file_found.connect(
            self.add_file
        )

        self.scan_worker.finished.connect(
            self.scan_finished
        )

        self.scan_worker.finished.connect(
            self.scan_thread.quit
        )

        self.scan_worker.finished.connect(
            self.scan_worker.deleteLater
        )

        self.scan_thread.finished.connect(
            self.scan_thread.deleteLater
        )

        self.scan_thread.finished.connect(
            self.scan_complete_cleanup
        )

        self.scan_thread.start()

    def add_file(self, item):
        existing_card = self.find_card(
            item["path"]
        )

        # The file may already have a card from a
        # previous scan. Update that card instead of
        # creating a duplicate card.
        if existing_card is not None:
            existing_card.backup_item = item
            existing_card.item = item
            existing_card.photo_tile.item = item

            existing_card.set_status(
                item["status"]
            )

            if item["status"] == "uploaded":
                existing_card.set_progress(
                    1,
                    1,
                )
            else:
                existing_card.set_progress(
                    0,
                    1,
                )

            self.update_summary()
            return

        # Restore user-approved queue entries after a restart, but only when
        # the file still has the same fast-scan signature as when it was queued.
        try:
            record = self.db.get_by_path(item["path"])
            if (
                record
                and record[4] == "waiting"
                and record[5] == self.backup_destination_id
                and int(record[2]) == int(item.get("size", -1))
                and int(record[3]) == int(item.get("mtime_ns", -1))
            ):
                item["status"] = "waiting"
            elif record and record[4] == "waiting":
                self.db.set_status(
                    item["path"],
                    "pending",
                    "File changed since it was queued; review before upload",
                )
        except Exception as exc:
            print(f"Could not restore queued upload state: {exc}")

        card = FileCard(
            item
        )

        card.backup_item = item

        card.skip_signal.connect(
            self.skip_current_upload
        )

        card.retry_signal.connect(
            self.retry_failed
        )

        card.photo_tile.details_requested.connect(
            self.show_media_details
        )

        self.cards.append(
            card
        )

        self.reflow_file_cards()

        self.update_summary()

    async def handle_upload_all(self, items):
        if self.backup_paused:
            self.status_label.setText(
                "● Backup paused"
            )
            return

        if not self.telegram_connected:
            await self.show_async_message(
                QMessageBox.Icon.Warning,
                "Telegram",
                "Connect Telegram before uploading.",
            )
            return

        if not self.backup_destination_available:
            await self.show_async_message(
                QMessageBox.Icon.Warning,
                "Telegram backup channel",
                "Please choose a Telegram backup channel first.",
            )

            await self._change_backup_location()

            return

        if not self.upload_queue and not self.upload_in_progress:
            self.upload_total = 0
            self.upload_completed_count = 0
            self.upload_failed_count = 0
            self._upload_batch_notified = False
            self.upload_current = None
            self.upload_speed = 0.0
            self.upload_started_at = None
            self.upload_last_current = 0
            self.upload_last_time = None

        queued_paths = {
            card.file_path
            for card in self.upload_queue
        }
        added_count = 0

        for item in items:
            card = self.find_card(
                item["path"]
            )

            if card is not None:
                if card.item.get("status") not in {"pending", "waiting"}:
                    continue

                if card.file_path in queued_paths:
                    continue

                try:
                    stat = Path(card.file_path).stat()
                except OSError as exc:
                    card.set_status("failed")
                    card.transfer_label.setText(
                        "File unavailable  •  Scan the folder again"
                    )
                    self.db.mark_failed(card.file_path, exc)
                    continue

                self.db.upsert(
                    path=card.file_path,
                    file_hash=card.item.get("hash"),
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    status="waiting",
                    destination_id=self.backup_destination_id,
                )
                card.item["size"] = stat.st_size
                card.item["mtime_ns"] = stat.st_mtime_ns

                self.upload_queue.append(
                    card
                )
                queued_paths.add(card.file_path)
                added_count += 1

        if not self.upload_queue and not self.upload_in_progress:
            self.status_label.setText(
                "● No files ready for upload"
            )
            return

        self.upload_total += added_count

        self.cancel_pending_button.setEnabled(
            True
        )

        for index, card in enumerate(self.upload_queue, start=1):
            card.set_waiting(
                index
            )

        self.update_queue_status()

        if added_count:
            self.show_notification(
                "Uploading",
                f"Uploading {len(self.upload_queue)} file(s)...",
                "info",
            )

        self.process_next_upload()

    def process_next_upload(self):

        if self.backup_paused:
            self.status_label.setText(
                "● Backup paused"
            )
            return

        if not self.telegram_connected or not self.backup_destination_available:
            self.status_label.setText(
                "● Connect Telegram and choose a private backup channel to resume"
            )
            return

        if self.upload_in_progress:
            return

        while self.upload_queue:

            card = self.upload_queue.pop(0)

            if card.item.get("status") != "waiting":
                continue

            file_hash = card.item.get("hash")

            if (
                file_hash
                and self.backup_destination_id is not None
                and self.db.has_uploaded_to_destination(
                    file_hash,
                    self.backup_destination_id,
                )
            ):
                self.db.mark_duplicate(
                    card.file_path,
                    self.backup_destination_id,
                )

                card.item["skip_reason"] = "duplicate"
                card.set_status("skipped")

                continue

            self.upload_current = card

            for index, waiting_card in enumerate(
                self.upload_queue,
                start=1,
            ):
                if waiting_card.item.get("status") == "waiting":
                    waiting_card.set_waiting(
                        index
                    )

            self.start_upload(
                card
            )

            return

        self.upload_current = None
        self.upload_in_progress = False

        self.cancel_pending_button.setEnabled(
            False
        )

        self.update_summary()
        detected_count = len(self.cards)
        uploaded_count = sum(
            1 for card in self.cards
            if card.item.get("status") == "uploaded"
        )
        if detected_count and uploaded_count == detected_count:
            self.status_label.setText("● All files are backed up")
            self.last_scan.setText(
                f"{detected_count} detected · {uploaded_count} uploaded · "
                "No unique files left to upload"
            )
        else:
            self.status_label.setText("● Upload queue complete")
            self.last_scan.setText(
                f"Completed {self.upload_completed_count} "
                f"of {self.upload_total} upload(s)"
            )

        if not self._upload_batch_notified:
            if self.upload_completed_count and self.upload_failed_count:
                self.show_notification(
                    "Backup finished with issues",
                    f"{self.upload_completed_count} upload(s) complete · "
                    f"{self.upload_failed_count} failed",
                    "warning",
                )
                self._upload_batch_notified = True
            elif self.upload_completed_count:
                completed = self.upload_completed_count
                noun = "upload" if completed == 1 else "uploads"
                self.show_notification(
                    "Backup complete",
                    f"{completed} {noun} complete",
                    "success",
                )
                self._upload_batch_notified = True
            elif self.upload_failed_count:
                failed = self.upload_failed_count
                noun = "upload" if failed == 1 else "uploads"
                self.show_notification(
                    "Upload failed",
                    f"{failed} {noun} failed. Retry from the file list.",
                    "warning",
                )
                self._upload_batch_notified = True

        self.release_tray_memory_if_idle()

    def release_tray_memory_if_idle(self):
        if not self._in_tray_mode:
            return
        if self.upload_in_progress or self.upload_queue:
            return
        if self.scan_thread and self.scan_thread.isRunning():
            return
        if self.cards:
            self.clear_cards()

    def start_upload(self, card):

        if self.backup_paused:
            self.status_label.setText(
                "● Backup paused"
            )
            return

        if self.upload_in_progress:
            return

        if not self.telegram_connected:
            self.status_label.setText(
                "● Telegram disconnected"
            )
            return

        if not self.backup_destination_available:
            self.status_label.setText(
                "● Backup location unavailable"
            )
            return

        self.upload_in_progress = True
        card.set_status("uploading")
        card.transfer_label.setText("Preparing file hash...")
        self.status_label.setText(
            f'● Preparing: {card.item["name"]}'
        )
        self.upload_task = asyncio.create_task(
            self._prepare_and_upload(card)
        )
        self.upload_task.add_done_callback(
            self._upload_task_finished
        )

    async def _prepare_and_upload(self, card):
        """Hash only a file that is about to upload, off the UI thread."""
        path = Path(card.file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")

        before = path.stat()
        file_hash = await sha256_file_async(path)
        after = path.stat()

        if (
            before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
        ):
            raise RuntimeError(
                "The file changed while its hash was being calculated. "
                "Please scan again before uploading."
            )

        card.item["hash"] = file_hash
        self.db.upsert(
            path=path,
            file_hash=file_hash,
            size=after.st_size,
            mtime_ns=after.st_mtime_ns,
            status="pending",
            destination_id=self.backup_destination_id,
        )

        if (
            self.db.has_uploaded_to_destination(
                file_hash,
                self.backup_destination_id,
            )
        ):
            self.db.mark_duplicate(
                path,
                self.backup_destination_id,
            )
            card.item["skip_reason"] = "duplicate"
            card.set_status("skipped")
            card.transfer_label.setText(
                "Already uploaded to this Telegram backup channel"
            )
            self.upload_in_progress = False
            self.upload_worker = None
            self.update_summary()
            self.process_next_upload()
            return

        self.db.mark_uploading(
            path,
            self.backup_destination_id,
        )
        self.upload_started_at = asyncio.get_running_loop().time()
        self.upload_last_time = self.upload_started_at
        self.upload_last_current = 0
        self.upload_speed = 0.0
        self.update_queue_status()
        self.status_label.setText(
            f'● Uploading: {card.item["name"]}'
        )

        self.upload_worker = UploadWorker(
            self.telegram,
            path,
        )
        self.upload_worker.progress.connect(self.upload_progress)
        self.upload_worker.started.connect(self.upload_started)
        self.upload_worker.completed.connect(self.upload_completed)
        self.upload_worker.failed.connect(self.upload_failed)
        await self.upload_worker.run()

    def find_card(self, file_path):

        for card in self.cards:

            if card.file_path == str(
                file_path
            ):
                return card

        return None

    def upload_started(self, file_path):
        card = self.find_card(
            file_path
        )

        if card:
            card.set_status(
                "uploading"
            )

            card.transfer_label.setText(
                "0%  •  Starting upload..."
            )

        self.update_queue_status()

    def upload_progress(
        self,
        file_path,
        current,
        total,
    ):
        card = self.find_card(
            file_path
        )

        now = asyncio.get_running_loop().time()

        if self.upload_last_time is None:
            self.upload_last_time = now
            self.upload_last_current = current

        elapsed = now - self.upload_last_time
        bytes_delta = current - self.upload_last_current

        if elapsed > 0 and bytes_delta >= 0:
            instant_speed = (
                bytes_delta / elapsed
            )

            if self.upload_speed <= 0:
                self.upload_speed = instant_speed
            else:
                self.upload_speed = (
                    self.upload_speed * 0.7
                    + instant_speed * 0.3
                )

        self.upload_last_time = now
        self.upload_last_current = current

        eta = None

        if (
            self.upload_speed > 0
            and total > current
        ):
            eta = (
                (total - current)
                / self.upload_speed
            )

        if card:
            card.set_progress(
                current,
                total,
                speed=self.upload_speed,
                eta=eta,
            )

        if total > 0:
            percent = int(
                (current / total) * 100
            )

            self.update_queue_status(
                percent
            )

    def update_queue_status(
        self,
        percent=None,
    ):
        if self.upload_current is None:
            return

        current_number = (
            self.upload_completed_count + 1
        )

        total = self.upload_total

        waiting = len(
            [
                card
                for card in self.upload_queue
                if card.item.get("status") == "waiting"
            ]
        )

        if percent is None:
            percent_text = ""
        else:
            percent_text = f"  •  {percent}%"

        self.status_label.setText(
            f"● Uploading "
            f"{current_number} of {total}"
            f"{percent_text}"
        )

        self.last_scan.setText(
            f"Pending upload: {waiting}"
        )

    def _upload_task_finished(self, task):
        try:
            task.result()

        except asyncio.CancelledError:
            return

        except Exception as exc:
            if self.upload_in_progress:
                self.upload_in_progress = False
                self.upload_failed_count += 1
                card = self.upload_current
                if card is not None:
                    self.db.mark_failed(card.file_path, exc)
                    card.set_status("failed")
                    card.transfer_label.setText(
                        "Upload preparation failed  •  Click Retry"
                    )
                self.status_label.setText("● Upload preparation failed")
                self.last_scan.setText(str(exc))
                self.update_summary()
                self.process_next_upload()

        finally:
            if task is self.upload_task:
                self.upload_task = None

    def retry_failed(self, file_path):
        card = self.find_card(
            file_path
        )

        if card is None:
            return

        if self.upload_in_progress:
            QMessageBox.information(
                self,
                "Upload in progress",
                "Please wait for the current upload to finish.",
            )
            return

        if not self.telegram_connected:
            QMessageBox.warning(
                self,
                "Telegram",
                "Connect Telegram before retrying.",
            )
            return

        if not self.backup_destination_available:
            QMessageBox.warning(
                self,
                "Telegram backup channel",
                "Telegram backup channel is unavailable.",
            )
            return

        path = Path(
            file_path
        )

        if not path.exists():
            QMessageBox.warning(
                self,
                "File unavailable",
                "This file no longer exists.",
            )
            return

        if not self.upload_queue and not self.upload_in_progress:
            self.upload_total = 0
            self.upload_completed_count = 0
            self.upload_failed_count = 0
            self._upload_batch_notified = False

        self.db.set_status(
            file_path,
            "pending",
            None,
        )

        card.set_status(
            "pending"
        )

        card.transfer_label.setText(
            "Added to retry queue"
        )

        stat = path.stat()
        self.db.upsert(
            path=path,
            file_hash=card.item.get("hash"),
            size=stat.st_size,
            mtime_ns=stat.st_mtime_ns,
            status="waiting",
            destination_id=self.backup_destination_id,
        )

        self.upload_queue.append(
            card
        )

        self.upload_total += 1
        card.set_waiting(
            len(self.upload_queue)
        )
        self.cancel_pending_button.setEnabled(
            True
        )

        self.show_notification(
            "Uploading",
            f"Uploading {len(self.upload_queue)} file(s)...",
            "info",
        )

        self.process_next_upload()

    def cancel_pending_uploads(self):
        if not self.upload_queue:
            self.cancel_pending_button.setEnabled(
                False
            )
            return

        cancelled = 0

        for card in self.upload_queue:
            if card.item.get("status") != "waiting":
                continue

            card.set_status(
                "pending"
            )
            self.db.set_status(
                card.file_path,
                "pending",
                None,
            )
            card.transfer_label.setText(
                "Upload cancelled"
            )
            cancelled += 1

        self.upload_queue.clear()
        self.cancel_pending_button.setEnabled(
            False
        )
        self.status_label.setText(
            "● Pending uploads cancelled"
        )
        self.last_scan.setText(
            f"Cancelled {cancelled} pending upload(s)"
        )
        self.update_summary()

    def upload_completed(
        self,
        file_path,
        message,
    ):
        message_id = getattr(message, "id", None)

        if message_id is None:
            self.upload_failed_count += 1
            self.db.mark_failed(
                file_path,
                "Telegram upload completed but message ID was not returned.",
            )
            card = self.find_card(file_path)
            if card:
                card.set_status("failed")
            self.upload_in_progress = False
            self.upload_worker = None
            self.status_label.setText(
                "● Upload verification failed"
            )
            self.update_summary()
            self.process_next_upload()
            return

        try:
            card = self.find_card(file_path)

            if card is None:
                raise RuntimeError(
                    "Upload completed but the file card was not found."
                )

            file_hash = card.item.get("hash")

            if not file_hash:
                raise RuntimeError(
                    "Upload completed but file hash is missing."
                )

            if self.backup_destination_id is None:
                raise RuntimeError(
                    "Upload completed but backup destination is missing."
                )

            self.db.mark_uploaded(
                file_path,
                file_hash,
                self.backup_destination_id,
                message_id,
            )
            uploaded_record = self.db.get_by_path(file_path)
            if uploaded_record:
                card.item["uploaded_at"] = uploaded_record[7]
        except Exception as exc:
            self.upload_failed_count += 1
            if card:
                card.set_status("failed")
                card.transfer_label.setText(
                    "Upload failed  •  Click Retry"
                )

            self.upload_in_progress = False
            self.upload_worker = None
            self.status_label.setText(
                "● Database update failed"
            )
            QMessageBox.critical(
                self,
                "Database error",
                f"Telegram upload succeeded, but the local "
                f"database could not be updated.\n\n{exc}",
            )
            self.update_summary()
            self.process_next_upload()
            return

        card.set_status("uploaded")
        card.progress.setValue(100)
        card.transfer_label.setText(
            "100%  •  Completed"
        )

        self.upload_completed_count += 1
        self.upload_in_progress = False
        self.upload_worker = None
        self.status_label.setText(
            f"● Uploaded {self.upload_completed_count} "
            f"of {self.upload_total}"
        )
        self.update_summary()
        self.process_next_upload()

    def upload_failed(
        self,
        file_path,
        error,
    ):
        self.upload_failed_count += 1
        self.db.mark_failed(file_path, error)
        card = self.find_card(file_path)

        if card:
            card.set_status("failed")
            card.transfer_label.setText(
                "Upload failed  •  Click Retry"
            )

        if (
            "Upload blocked:" in str(error)
            or "Could not verify that the Telegram backup channel" in str(error)
        ):
            self.telegram.clear_upload_destination()
            self.backup_destination_available = False
            self.update_destination_ui()

        self.upload_in_progress = False
        self.upload_worker = None
        self.status_label.setText(
            "● Upload failed"
        )
        self.last_scan.setText(
            f"Failed: {Path(file_path).name}"
        )
        self.update_summary()
        self.process_next_upload()

    def skip_current_upload(
        self,
        file_path,
    ):
        if (
            not self.upload_in_progress
            or self.upload_current is None
        ):
            return

        if self.upload_current.file_path != file_path:
            return

        if self.upload_task is not None:
            self.upload_task.cancel()

        self.upload_task = None
        self.upload_in_progress = False
        self.upload_worker = None

        self.db.set_status(
            file_path,
            "skipped",
            None,
        )
        self.upload_current.set_status(
            "skipped"
        )
        self.status_label.setText(
            "● Skipped ⏭"
        )
        self.process_next_upload()

    def scan_finished(self, message):
        automatic = self._scan_auto_upload
        self._scan_auto_upload = False

        self.status_label.setText(
            "● Ready"
        )

        self.last_scan.setText(
            message
        )

        self.update_summary()

        scan_items = []

        for card in self.cards:
            item = getattr(
                card,
                "backup_item",
                None,
            )

            if not item:
                continue

            status = item.get("status")

            if status in {
                "pending",
                "waiting",
                "uploaded",
            }:
                scan_items.append(item)

        self.last_scan_items = scan_items

        if not scan_items:
            return

        asyncio.create_task(
            self._verify_and_continue_scan(
                scan_items,
                automatic=automatic,
            )
        )

    async def verify_uploaded_items(self, items):
        """
        Verify uploaded messages in batches and forget deleted Telegram files.
        """

        if not self.telegram_connected:
            return False

        if not self.backup_destination_available:
            return False

        destination_id = self.backup_destination_id
        message_by_hash = {}

        for item in items:
            if item.get("status") != "uploaded":
                continue

            file_hash = item.get("hash")
            if not file_hash:
                continue

            if file_hash in message_by_hash:
                continue

            message_id = item.get("telegram_message_id")
            if message_id is None:
                record = self.db.get_upload_record(
                    file_hash,
                    destination_id,
                )
                if record:
                    message_id = record[2]

            message_by_hash[file_hash] = message_id

        try:
            existing_ids = await self.telegram.existing_message_ids(
                message_id
                for message_id in message_by_hash.values()
                if message_id is not None
            )
        except Exception as exc:
            print(f"Could not verify Telegram backup messages: {exc}")
            return False

        missing_hashes = {
            file_hash
            for file_hash, message_id in message_by_hash.items()
            if message_id is None or int(message_id) not in existing_ids
        }

        if not missing_hashes:
            return True

        for file_hash in missing_hashes:
            self.db.delete_upload_record(
                file_hash,
                destination_id,
            )

        for item in items:
            if item.get("hash") not in missing_hashes:
                continue

            item["status"] = "pending"
            item["telegram_message_id"] = None
            card = self.find_card(item["path"])
            if card:
                card.set_status("pending")
                card.transfer_label.setText(
                    "Telegram copy was deleted • Ready to upload"
                )

        self.update_summary()
        return True

    async def _verify_and_continue_scan(self, items, automatic=False):
        """
        Verify uploaded Telegram messages before showing the permission dialog.
        """

        verification_available = await self.verify_uploaded_items(items)

        pending_items = [
            item
            for item in items
            if item.get("status") in {
                "pending",
                "waiting",
            }
        ]

        self.last_scan_items = pending_items

        detected_count = len(items)
        uploaded_count = sum(
            1 for item in items if item.get("status") == "uploaded"
        )
        self.update_summary()

        if not pending_items:
            if detected_count == 0:
                self.last_scan.setText("No supported files found")
                self.status_label.setText("● No media files found")
            elif verification_available and uploaded_count == detected_count:
                self.last_scan.setText(
                    f"{detected_count} detected · {uploaded_count} uploaded · "
                    "No unique files found"
                )
                self.status_label.setText("● All files are backed up")
            elif uploaded_count:
                self.last_scan.setText(
                    f"{detected_count} detected · {uploaded_count} uploaded · "
                    "Connect to Telegram to verify backups"
                )
                self.status_label.setText("● Telegram backup verification unavailable")
            self.release_tray_memory_if_idle()
            return

        noun = "file" if len(pending_items) == 1 else "files"
        self.show_notification(
            "New files detected",
            f"{len(pending_items)} new {noun} detected",
            "info",
        )

        if self._in_tray_mode and not automatic:
            self.show_notification(
                "Files need review",
                f"Open {APP_NAME} from the tray to review and upload them.",
                "info",
            )
            self.release_tray_memory_if_idle()
            return

        if automatic:
            if not self.telegram_connected or not self.backup_destination_available:
                self.status_label.setText(
                    "● Automatic backup paused until Telegram is connected"
                )
                self.last_scan.setText(
                    f"{len(pending_items)} unique file(s) found; connect Telegram to upload"
                )
                self.release_tray_memory_if_idle()
                return

            # Let the detection toast be seen before replacing it with the
            # upload-state toast in the automatic flow.
            await asyncio.sleep(1.2)
            if not self.automatic_scan_enabled or self.backup_paused:
                return

            self.last_scan.setText(
                f"{len(pending_items)} unique file(s) found · Uploading automatically"
            )
            await self.handle_upload_all(pending_items)
            return

        self.last_scan.setText(
            f"{detected_count} detected · {uploaded_count} uploaded · "
            f"{len(pending_items)} new file(s)"
        )

        photo_count = sum(
            1
            for item in pending_items
            if item.get("kind") == "Photo"
        )

        video_count = sum(
            1
            for item in pending_items
            if item.get("kind") == "Video"
        )

        large_count = sum(
            1
            for item in pending_items
            if self.backup_settings.is_large_file(
                item.get("size", 0)
            )
        )

        dialog = ScanPermissionDialog(
            total_files=len(pending_items),
            photo_count=photo_count,
            video_count=video_count,
            large_count=large_count,
            parent=self,
        )

        result = await open_dialog(
            dialog,
            delete_on_finish=False,
        )
        choice = dialog.selected_choice()
        dialog.deleteLater()

        if result != QDialog.DialogCode.Accepted:
            self._discard_scan_candidates(pending_items)
            self.last_scan.setText("Scan cancelled")
            self.status_label.setText("● Scan cancelled")
            return

        if choice == ScanPermissionDialog.UPLOAD_ALL:
            await self.handle_upload_all(
                pending_items,
            )
            return

        if choice == ScanPermissionDialog.REVIEW:
            await self.handle_review_files(pending_items)

    async def handle_review_files(self, items):
        if not items:
            return

        dialog = ReviewFilesDialog(
            items=items,
            large_file_checker=self.backup_settings.is_large_file,
            parent=self,
        )

        result = await open_dialog(
            dialog,
            delete_on_finish=False,
        )
        upload_items, skip_items = dialog.selected_files()
        dialog.deleteLater()

        if result != QDialog.DialogCode.Accepted:
            self._discard_scan_candidates(items)
            self.status_label.setText(
                "● Review cancelled"
            )
            return

        for item in skip_items:
            card = self.find_card(
                item["path"]
            )

            if card is None:
                continue

            self.db.set_status(
                card.file_path,
                "skipped",
                "Skipped by user during file review",
            )

            card.item["skip_reason"] = "manual"
            card.set_status(
                "skipped"
            )

        if upload_items:
            await self.handle_upload_all(
                upload_items,
            )
        else:
            self.status_label.setText(
                f"● {len(skip_items)} file(s) skipped"
            )

        self.update_summary()

    def _discard_scan_candidates(self, items):
        paths = {
            str(item.get("path"))
            for item in items
            if item.get("path")
        }
        for card in list(self.cards):
            if card.file_path not in paths:
                continue
            self.cards.remove(card)
            self.queue_layout.removeWidget(card)
            card.deleteLater()

        self.reflow_file_cards()
        self.last_scan_items = []
        self.update_summary()

    def show_media_details(self, item):
        card = self.find_card(item.get("path", ""))
        details_item = dict(item)
        if card is not None:
            details_item.update(card.item)
        status = details_item.get("status")
        self._media_details_dialog = MediaDetailsDialog(
            details_item,
            status=status,
            uploaded_at=details_item.get("uploaded_at"),
            parent=self,
        )
        self._media_details_dialog.open()

    def reflow_file_cards(self):
        if not hasattr(self, "queue_layout") or not hasattr(self, "cards"):
            return
        panel_width = max(160, self.queue_panel.contentsRect().width())
        columns = max(1, (panel_width + 12) // 112)
        for index, card in enumerate(self.cards):
            self.queue_layout.addWidget(card, index // columns, index % columns)

    def scan_complete_cleanup(self):

        self.scan_thread = None
        self.scan_worker = None

    def clear_cards(self):

        while self.queue_layout.count() > 0:

            item = self.queue_layout.takeAt(
                0
            )

            widget = item.widget()

            if widget:
                widget.deleteLater()

        self.cards.clear()

        self.update_summary()

    def update_summary(self):

        detected = len(
            self.cards
        )

        uploaded = 0
        pending = 0

        for card in self.cards:

            labels = card.findChildren(
                QLabel
            )

            for label in labels:

                text = label.text()

                if text == "Uploaded ✓":

                    uploaded += 1
                    break

                if text == "Pending":

                    pending += 1
                    break

        self.detected_label[1].setText(
            str(detected)
        )

        self.pending_label[1].setText(
            str(pending)
        )

        self.uploaded_label[1].setText(
            str(uploaded)
        )

    def apply_style(self):

        self.setStyleSheet("""
            QMainWindow {
                background: #f7f8fa;
                color: #202124;
            }

            QWidget {
                color: #202124;
            }

            QLabel {
                background: transparent;
            }

            QFrame#sidebar {
                background: #f0f2f5;
                border-right: 1px solid #e2e5e9;
            }

            QLabel#sidebarSection {
                color: #80868b;
                font-size: 10px;
                font-weight: 700;
                padding-left: 10px;
            }

            QPushButton#sidebarAction,
            QPushButton#sidebarActiveAction,
            QPushButton#sidebarCollapsedAction {
                background: transparent;
                color: #3c4043;
                border: none;
                border-radius: 10px;
                padding: 0;
                text-align: left;
                font-size: 14px;
            }

            QPushButton#sidebarActiveAction {
                background: #ffffff;
                color: #202124;
                font-weight: 600;
            }

            QPushButton#sidebarCollapsedAction {
                padding: 0;
                text-align: center;
                font-size: 20px;
            }

            QPushButton#sidebarAction:hover,
            QPushButton#sidebarActiveAction:hover,
            QPushButton#sidebarCollapsedAction:hover {
                background: #e5e8ed;
            }

            QPushButton#sidebarAction:pressed,
            QPushButton#sidebarActiveAction:pressed,
            QPushButton#sidebarCollapsedAction:pressed {
                background: #dadce0;
            }

            QLabel#title {
                font-size: 28px;
                font-weight: 600;
                color: #202124;
            }

            QLabel#readyStatus {
                font-size: 13px;
                color: #188038;
            }

            QLabel#sectionTitle {
                font-size: 16px;
                font-weight: 600;
                color: #202124;
            }

            QLabel#folderLabel {
                font-size: 13px;
                color: #5f6368;
            }

            QLabel#destinationLabel {
                font-size: 13px;
                color: #5f6368;
            }

            QLabel#muted {
                color: #6b7280;
                font-size: 12px;
            }

            QLabel#summaryValue {
                font-size: 26px;
                font-weight: 700;
                color: #202124;
            }

            QLabel#summaryTitle {
                color: #6b7280;
                font-size: 12px;
                font-weight: 600;
            }

            QLabel#fileName {
                font-size: 14px;
                font-weight: 600;
                color: #202124;
            }

            QLabel#fileMeta {
                font-size: 12px;
                color: #6b7280;
            }

            QLabel#uploadInfo {
                font-size: 11px;
                color: #6b7280;
            }

            QLabel#fileReason {
                font-size: 12px;
                color: #6b7280;
            }

            QLabel#status_pending {
                color: #b06000;
                font-size: 12px;
                font-weight: 600;
                background: #fff4e5;
                border-radius: 8px;
                padding: 4px 8px;
            }

            QLabel#status_uploaded {
                color: #188038;
                font-size: 12px;
                font-weight: 600;
                background: #e6f4ea;
                border-radius: 8px;
                padding: 4px 8px;
            }

            QLabel#status_waiting {
                color: #b06000;
                font-size: 12px;
                font-weight: 600;
                background: #fff4e5;
                border-radius: 8px;
                padding: 4px 8px;
            }

            QLabel#status_uploading {
                color: #1a73e8;
                font-size: 12px;
                font-weight: 600;
                background: #e8f0fe;
                border-radius: 8px;
                padding: 4px 8px;
            }

            QLabel#status_failed {
                color: #d93025;
                font-size: 12px;
                font-weight: 600;
                background: #fce8e6;
                border-radius: 8px;
                padding: 4px 8px;
            }

            QLabel#status_skipped {
                color: #6b7280;
                font-size: 12px;
                font-weight: 600;
                background: #f1f3f4;
                border-radius: 8px;
                padding: 4px 8px;
            }

            QLabel#transferInfo {
                color: #6b7280;
                font-size: 11px;
            }

            QFrame#card,
            QFrame#summaryCard {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 18px;
            }

            QFrame#queuePanel {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 18px;
            }

            QFrame#fileCard {
                background: transparent;
                border: none;
                border-radius: 0;
            }

            QFrame#summaryCard {
                min-width: 150px;
                min-height: 92px;
            }

            QFrame#summaryCard[metricType="detected"] {
                border-top: 3px solid #1a73e8;
            }

            QFrame#summaryCard[metricType="pending"] {
                border-top: 3px solid #f9ab00;
            }

            QFrame#summaryCard[metricType="uploaded"] {
                border-top: 3px solid #34a853;
            }

            QFrame#fileCard {
                margin: 1px;
            }

            QFrame#fileCard:hover {
                background: transparent;
                border: none;
            }

            QPushButton {
                background: #1a73e8;
                color: #ffffff;
                border: none;
                border-radius: 9px;
                padding: 10px 18px;
                font-size: 13px;
            }

            QPushButton:hover {
                background: #1765cc;
            }

            QPushButton:pressed {
                background: #1558b0;
            }

            QPushButton:disabled {
                background: #e8eaed;
                color: #9aa0a6;
                border: 1px solid #dadce0;
            }

            QPushButton#settingsToggle {
                background: #e8eaed;
                color: #5f6368;
                border: 1px solid #dadce0;
                border-radius: 15px;
                padding: 0;
                font-size: 11px;
                font-weight: 700;
            }

            QPushButton#settingsToggle:checked {
                background: #188038;
                color: #ffffff;
                border-color: #188038;
            }

            QScrollArea {
                background: #f7f8fa;
                border: none;
            }

            QScrollArea#dashboardScroll {
                background: #f7f8fa;
                border: none;
            }

            QScrollArea > QWidget {
                background: #f7f8fa;
            }

            QScrollArea > QWidget > QWidget {
                background: #f7f8fa;
            }

            QWidget#queueContainer {
                background: transparent;
            }

            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 4px 2px 4px 2px;
                border: none;
            }

            QScrollBar::handle:vertical {
                background: #b8bcc3;
                min-height: 40px;
                border-radius: 4px;
                margin: 0px;
            }

            QScrollBar::handle:vertical:hover {
                background: #8f959e;
            }

            QScrollBar::handle:vertical:pressed {
                background: #6f757d;
            }

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
                border: none;
            }

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {
                background: transparent;
            }

            QScrollBar:horizontal {
                background: transparent;
                height: 8px;
                margin: 2px 4px 2px 4px;
                border: none;
            }

            QScrollBar::handle:horizontal {
                background: #b8bcc3;
                min-width: 40px;
                border-radius: 4px;
            }

            QScrollBar::handle:horizontal:hover {
                background: #8f959e;
            }

            QScrollBar::handle:horizontal:pressed {
                background: #6f757d;
            }

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {
                width: 0px;
                background: transparent;
                border: none;
            }

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {
                background: transparent;
            }

            QProgressBar {
                background: #e8eaed;
                border: none;
                border-radius: 2px;
            }

            QProgressBar::chunk {
                background: #202124;
                border-radius: 2px;
            }

            QMessageBox {
                background-color: #202124;
            }

            QMessageBox QLabel {
                color: #f1f3f4;
                background-color: transparent;
            }

            QMessageBox QPushButton {
                background-color: #303134;
                color: #f1f3f4;
                border: 1px solid #5f6368;
                border-radius: 6px;
                padding: 7px 18px;
                min-width: 70px;
            }

            QMessageBox QPushButton:hover {
                background-color: #3c4043;
            }
        """)

    def closeEvent(self, event):
        if self._allow_close:
            event.accept()
            return

        if (
            self.tray_icon is not None
            and self.tray_icon.isVisible()
            and is_startup_enabled()
        ):
            self._in_tray_mode = True
            self.hide()
            if (
                not self.upload_in_progress
                and not self.upload_queue
                and not (self.scan_thread and self.scan_thread.isRunning())
            ):
                self.clear_cards()
            event.ignore()
            return

        self.exit_application()
        event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if (
            self._notification_toast is not None
            and self._notification_toast.isVisible()
        ):
            self._notification_toast.move(
                max(12, self.width() - self._notification_toast.width() - 22),
                18,
            )
        if hasattr(self, "queue_layout"):
            QTimer.singleShot(0, self.reflow_file_cards)
