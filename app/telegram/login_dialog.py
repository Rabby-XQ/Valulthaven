from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from app.constants import APP_NAME


class TelegramLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Connect Telegram")
        self.setMinimumWidth(470)
        self.setStyleSheet("""
            QDialog {
                background: #f7f8fa;
                color: #202124;
            }
            QLabel {
                background: transparent;
                color: #202124;
            }
            QLabel#loginTitle {
                font-size: 22px;
                font-weight: 600;
                color: #202124;
            }
            QLabel#loginSubtitle {
                color: #5f6368;
                font-size: 13px;
            }
            QLabel#apiInfo {
                background: #ffffff;
                border: 1px solid #e2e5e9;
                border-radius: 10px;
                padding: 12px;
                color: #5f6368;
                font-size: 12px;
            }
            QLabel#apiInfo a {
                color: #1a73e8;
                text-decoration: none;
            }
            QLabel#fieldLabel {
                color: #3c4043;
                font-size: 13px;
                font-weight: 600;
            }
            QLineEdit {
                background: #ffffff;
                color: #202124;
                border: 1px solid #dadce0;
                border-radius: 8px;
                padding: 10px 12px;
                selection-background-color: #d2e3fc;
            }
            QLineEdit:focus {
                border: 1px solid #1a73e8;
            }
            QLineEdit:disabled {
                background: #f1f3f4;
                color: #80868b;
                border: 1px solid #dadce0;
            }
            QDialogButtonBox QPushButton {
                background: #202124;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 9px 18px;
                min-width: 82px;
            }
            QDialogButtonBox QPushButton:hover {
                background: #303134;
            }
            QDialogButtonBox QPushButton:pressed {
                background: #171717;
            }
            QDialogButtonBox QPushButton[text="Cancel"] {
                background: #e8eaed;
                color: #202124;
            }
            QDialogButtonBox QPushButton[text="Cancel"]:hover {
                background: #dadce0;
            }
        """)

        self.title_label = QLabel("Connect your Telegram account")
        self.title_label.setObjectName("loginTitle")

        self.info_label = QLabel(
            "Enter the phone number linked to your Telegram account."
        )
        self.info_label.setObjectName("loginSubtitle")
        self.info_label.setWordWrap(True)

        self.api_info_label = QLabel(
            f'{APP_NAME} needs a Telegram API ID and API Hash. '
            'Get them from '
            '<a href="https://my.telegram.org/apps">Telegram API Development Tools</a>, '
            'then add them to the app\'s .env file.'
        )
        self.api_info_label.setObjectName("apiInfo")
        self.api_info_label.setWordWrap(True)
        self.api_info_label.setOpenExternalLinks(True)

        self.phone_label = QLabel("Phone number")
        self.phone_label.setObjectName("fieldLabel")
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("+8801XXXXXXXXX")

        self.code_label = QLabel("Login code")
        self.code_label.setObjectName("fieldLabel")
        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Enter the code from Telegram")
        self.code_label.hide()
        self.code_input.hide()

        self.password_label = QLabel("2-step verification password")
        self.password_label.setObjectName("fieldLabel")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your Telegram password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_label.hide()
        self.password_input.hide()

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Continue")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(self.title_label)
        layout.addWidget(self.info_label)
        layout.addWidget(self.api_info_label)
        layout.addSpacing(4)
        layout.addWidget(self.phone_label)
        layout.addWidget(self.phone_input)
        layout.addWidget(self.code_label)
        layout.addWidget(self.code_input)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addSpacing(6)
        layout.addWidget(self.buttons)

    def show_code_step(self):
        self.setWindowTitle("Verify Telegram Login")
        self.title_label.setText("Check your Telegram")
        self.info_label.setText(
            "Enter the login code Telegram sent to your account."
        )
        self.phone_input.setEnabled(False)
        self.code_label.show()
        self.code_input.show()
        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Verify")
        self.code_input.setFocus()

    def show_password_step(self):
        self.setWindowTitle("Telegram Two-Step Verification")
        self.title_label.setText("Enter your Telegram password")
        self.info_label.setText(
            "Two-step verification is enabled for this account."
        )
        self.code_input.setEnabled(False)
        self.password_label.show()
        self.password_input.show()
        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Sign in")
        self.password_input.setFocus()

    def phone(self):
        return self.phone_input.text().strip()

    def code(self):
        return self.code_input.text().strip()

    def password(self):
        return self.password_input.text()

    def set_error(self, message):
        self.info_label.setText(f"Error: {message}")
