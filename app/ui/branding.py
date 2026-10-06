from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


from app.constants import APP_NAME


LOGO_PATH = Path(__file__).resolve().parents[1] / "assets" / "vaulthaven_logo.svg"


def app_icon():
    return QIcon(str(LOGO_PATH))


def startup_splash_pixmap(show_welcome=True):
    if not show_welcome:
        size = 180
        pixmap = QPixmap(size, size)
        pixmap.fill(QColor("#f5f7fb"))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(8, 8, size - 16, size - 16, 34, 34)
        QSvgRenderer(str(LOGO_PATH)).render(
            painter,
            QRectF(42, 42, 96, 96),
        )
        painter.end()
        return pixmap

    width, height = 560, 340
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#f5f7fb"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(12, 12, width - 24, height - 24, 24, 24)

    renderer = QSvgRenderer(str(LOGO_PATH))
    renderer.render(painter, QRectF(237, 42, 86, 86))

    painter.setPen(QColor("#202124"))
    title_font = QFont("Segoe UI", 22)
    title_font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(title_font)
    painter.drawText(
        30, 170, width - 60, 34, Qt.AlignmentFlag.AlignCenter, APP_NAME
    )

    painter.setPen(QColor("#1765cc"))
    headline_font = QFont("Segoe UI", 14)
    headline_font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(headline_font)
    painter.drawText(
        30, 213, width - 60, 28, Qt.AlignmentFlag.AlignCenter,
        "Storage worries? Leave them behind.",
    )

    painter.setPen(QColor("#5f6368"))
    detail_font = QFont("Segoe UI", 10)
    painter.setFont(detail_font)
    painter.drawText(
        30, 248, width - 60, 24, Qt.AlignmentFlag.AlignCenter,
        "Secure Telegram cloud backup for your files",
    )

    painter.setPen(QColor("#80868b"))
    caption_font = QFont("Segoe UI", 9)
    painter.setFont(caption_font)
    painter.drawText(
        30, 294, width - 60, 20, Qt.AlignmentFlag.AlignCenter,
        "Private storage  ·  Automatic backup  ·  Easy recovery",
    )
    painter.end()
    return pixmap
