from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class BackupLocationDialog(QDialog):
    """
    First-run/change-location dialog.

    The dialog itself is intentionally normal Qt UI. MainWindow should
    open it with an async helper instead of dialog.exec(), so it does not
    create a nested event loop inside qasync.
    """

    def __init__(self, parent=None, channels=None, current_id=None):
        super().__init__(parent)

        self.setWindowTitle("Choose Backup Location")
        self.setMinimumSize(520, 430)

        self.channels = channels or []
        self.current_id = current_id

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        title = QLabel("Choose Backup Location")
        title.setObjectName("dialogTitle")

        subtitle = QLabel(
            "Choose where VaultHaven should store your photos and videos."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("dialogSubtitle")

        root.addWidget(title)
        root.addWidget(subtitle)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(
            QListWidget.SelectionMode.SingleSelection
        )

        for channel in self.channels:
            item = QListWidgetItem(
                f"{channel['title']}\nPrivate Telegram Channel"
            )
            item.setData(Qt.ItemDataRole.UserRole, channel["id"])
            self.list_widget.addItem(item)

            if current_id is not None and channel["id"] == current_id:
                item.setSelected(True)
                self.list_widget.setCurrentItem(item)

        root.addWidget(self.list_widget, 1)

        create_row = QHBoxLayout()

        self.new_channel_name = QLineEdit()
        self.new_channel_name.setPlaceholderText(
            "New private channel name"
        )

        self.create_button = QPushButton(
            "Create Private Channel"
        )
        self.create_button.clicked.connect(self.accept_create)

        create_row.addWidget(self.new_channel_name, 1)
        create_row.addWidget(self.create_button)

        root.addLayout(create_row)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Ok
        )

        buttons.accepted.connect(self.accept_existing)
        buttons.rejected.connect(self.reject)

        root.addWidget(buttons)

    def selected_channel_id(self):
        item = self.list_widget.currentItem()

        if item is None:
            return None

        return item.data(Qt.ItemDataRole.UserRole)

    def new_channel_name(self):
        return self.new_channel_name.text().strip()

    def accept_existing(self):
        if self.selected_channel_id() is None:
            QMessageBox.warning(
                self,
                "Backup Location",
                "Please select a Telegram channel.",
            )
            return

        self.done(QDialog.DialogCode.Accepted)

    def accept_create(self):
        name = self.new_channel_name.text().strip()

        if not name:
            QMessageBox.warning(
                self,
                "Create Channel",
                "Enter a channel name first.",
            )
            self.new_channel_name.setFocus()
            return

        # 2 means the caller should create a channel.
        self.done(2)

    def result_mode(self):
        if self.result() == 2:
            return "create"

        if self.result() == QDialog.DialogCode.Accepted:
            return "select"

        return "cancel"
