from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.constants import APP_NAME

class ScanPermissionDialog(QDialog):
    """
    Ask the user what to do with newly discovered files.
    """

    UPLOAD_ALL = "upload_all"
    REVIEW = "review"
    CANCEL = "cancel"

    def __init__(
        self,
        total_files,
        photo_count,
        video_count,
        large_count,
        parent=None,
    ):
        super().__init__(parent)

        self.choice = self.CANCEL

        self.setWindowTitle("New Files Found")
        self.setMinimumWidth(520)

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

            QLabel#countValue {
                font-size: 18px;
                font-weight: 600;
                color: #202124;
            }

            QLabel#countLabel {
                font-size: 12px;
                color: #6b7280;
            }

            QLabel#warning {
                background: #fff8e1;
                color: #8a6100;
                border: 1px solid #f1df9b;
                border-radius: 8px;
                padding: 10px;
            }

            QPushButton {
                background: #202124;
                color: #ffffff;
                border: none;
                border-radius: 9px;
                padding: 10px 18px;
                font-size: 13px;
            }

            QPushButton:hover {
                background: #303134;
            }

            QPushButton:pressed {
                background: #171717;
            }

            QDialogButtonBox QPushButton {
                min-width: 80px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)

        title = QLabel("New Files Found")
        title.setObjectName("dialogTitle")

        subtitle = QLabel(
            f"{APP_NAME} found new files in your backup folder. "
            "Choose how you want to handle them."
        )
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)

        root.addWidget(title)
        root.addWidget(subtitle)

        counts = QHBoxLayout()
        counts.setSpacing(10)

        counts.addLayout(
            self._make_count(
                str(total_files),
                "New Files",
            )
        )

        counts.addLayout(
            self._make_count(
                str(photo_count),
                "Photos",
            )
        )

        counts.addLayout(
            self._make_count(
                str(video_count),
                "Videos",
            )
        )

        root.addLayout(counts)

        if large_count > 0:
            warning = QLabel(
                f"⚠ {large_count} large file(s) detected. "
                "You can review them before uploading."
            )
            warning.setObjectName("warning")
            warning.setWordWrap(True)
            root.addWidget(warning)

        root.addSpacing(4)

        upload_button = QPushButton("Upload All")
        upload_button.clicked.connect(self.choose_upload_all)

        review_button = QPushButton("Review Files")
        review_button.clicked.connect(self.choose_review)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        button_row.addWidget(review_button)
        button_row.addWidget(upload_button)

        root.addLayout(button_row)

        cancel_buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel
        )
        cancel_buttons.rejected.connect(self.choose_cancel)

        root.addWidget(cancel_buttons)

    @staticmethod
    def _make_count(value, label):
        layout = QVBoxLayout()
        layout.setSpacing(2)

        value_label = QLabel(value)
        value_label.setObjectName("countValue")
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        text_label = QLabel(label)
        text_label.setObjectName("countLabel")
        text_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        layout.addWidget(value_label)
        layout.addWidget(text_label)

        return layout

    def choose_upload_all(self):
        self.choice = self.UPLOAD_ALL
        self.accept()

    def choose_review(self):
        self.choice = self.REVIEW
        self.accept()

    def choose_cancel(self):
        self.choice = self.CANCEL
        self.reject()

    def selected_choice(self):
        return self.choice
