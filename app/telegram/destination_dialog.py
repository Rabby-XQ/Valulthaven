from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QLineEdit,
    QVBoxLayout,
)

from app.constants import APP_NAME


class BackupLocationDialog(QDialog):
    """Choose an existing broadcast channel or create a new private channel."""

    def __init__(self, parent=None, channels=None, current_id=None):
        super().__init__(parent)

        self.setWindowTitle("Choose Telegram Backup Channel")
        self.setMinimumSize(560, 450)
        self.setStyleSheet("""
            QDialog {
                background: #f7f8fa;
                color: #202124;
            }

            QLabel {
                background: transparent;
                color: #202124;
            }

            QLabel#dialogTitle {
                font-size: 22px;
                font-weight: 600;
                color: #202124;
            }

            QLabel#dialogSubtitle {
                font-size: 13px;
                color: #5f6368;
            }

            QLabel#sectionTitle {
                font-size: 14px;
                font-weight: 600;
                color: #202124;
            }

            QListWidget {
                background: #ffffff;
                color: #202124;
                border: 1px solid #e2e5e9;
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }

            QListWidget::item {
                color: #202124;
                background: transparent;
                padding: 10px 8px;
                border-radius: 6px;
            }

            QListWidget::item:hover {
                background: #f1f3f4;
            }

            QListWidget::item:selected {
                background: #e8eaed;
                color: #202124;
            }

            QLineEdit {
                background: #ffffff;
                color: #202124;
                border: 1px solid #dadce0;
                border-radius: 8px;
                padding: 9px 10px;
                font-size: 13px;
            }

            QLineEdit:focus {
                border: 1px solid #1a73e8;
            }

            QLineEdit::placeholder {
                color: #9aa0a6;
            }

            QPushButton {
                background: #202124;
                color: #ffffff;
                border: none;
                border-radius: 9px;
                padding: 9px 16px;
                font-size: 13px;
            }

            QPushButton:hover {
                background: #303134;
            }

            QPushButton:pressed {
                background: #171717;
            }

            QDialogButtonBox QPushButton {
                min-width: 70px;
            }
        """)

        self.channels = channels or []
        self.current_id = current_id

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)

        title = QLabel("Choose Telegram Backup Channel")
        title.setObjectName("dialogTitle")

        subtitle = QLabel(
            f"Choose the Telegram channel where {APP_NAME} will store "
            "your photos and videos."
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
            item.setData(Qt.ItemDataRole.UserRole, int(channel["id"]))
            self.list_widget.addItem(item)

            if current_id is not None and int(channel["id"]) == int(current_id):
                item.setSelected(True)
                self.list_widget.setCurrentItem(item)

        root.addWidget(self.list_widget, 1)

        create_label = QLabel("Or create a new private channel")
        create_label.setObjectName("sectionTitle")
        root.addWidget(create_label)

        create_row = QHBoxLayout()
        self.channel_name_input = QLineEdit()
        self.channel_name_input.setPlaceholderText(
            f"Example: {APP_NAME} Photos"
        )

        self.create_button = QPushButton("Create Private Channel")
        self.create_button.clicked.connect(self.accept_create)

        create_row.addWidget(self.channel_name_input, 1)
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

    def new_channel_name_value(self):
        return self.channel_name_input.text().strip()

    def accept_existing(self):
        if self.selected_channel_id() is None:
            QMessageBox.warning(
                self,
                "Telegram Backup Channel",
                "Please select a Telegram channel.",
            )
            return

        self.done(QDialog.DialogCode.Accepted)

    def accept_create(self):
        name = self.new_channel_name_value()

        if not name:
            QMessageBox.warning(
                self,
                "Create Channel",
                "Enter a channel name first.",
            )
            self.channel_name_input.setFocus()
            return

        self.done(2)

    def result_mode(self):
        if self.result() == 2:
            return "create"

        if self.result() == QDialog.DialogCode.Accepted:
            return "select"

        return "cancel"
