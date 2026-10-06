from datetime import datetime
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QSize, Signal, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QImageReader, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QFrame,
)

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
except ImportError:
    QAudioOutput = QMediaPlayer = QVideoWidget = None


def media_thumbnail(item, size=QSize(176, 128)):
    path = Path(item.get("path", ""))
    if item.get("kind") == "Photo":
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        source_size = reader.size()
        if source_size.isValid():
            reader.setScaledSize(
                source_size.scaled(
                    size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                )
            )
        else:
            reader.setScaledSize(size)
        image = reader.read()
        if not image.isNull():
            pixmap = QPixmap.fromImage(image)
            scaled = pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            x = max(0, (scaled.width() - size.width()) // 2)
            y = max(0, (scaled.height() - size.height()) // 2)
            return scaled.copy(x, y, size.width(), size.height())
    return QPixmap()


def media_full_preview(item, size=QSize(1400, 1000)):
    """Load the whole photo for the detail view without thumbnail cropping."""
    path = Path(item.get("path", ""))
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    source_size = reader.size()
    if source_size.isValid():
        reader.setScaledSize(
            source_size.scaled(size, Qt.AspectRatioMode.KeepAspectRatio)
        )
    image = reader.read()
    return QPixmap.fromImage(image) if not image.isNull() else QPixmap()


class SelectionMark(QPushButton):
    """A custom painted selection control, independent of native checkbox styles."""

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(22, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Select photo")
        self.setStyleSheet("background: transparent; border: none; padding: 0;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        if self.isChecked():
            painter.setPen(QPen(QColor("#1a73e8"), 1.5))
            painter.setBrush(QColor("#1a73e8"))
            painter.drawEllipse(rect)
            painter.setPen(QPen(Qt.GlobalColor.white, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(rect.left() + 4, rect.center().y(), rect.center().x() - 1, rect.bottom() - 5)
            painter.drawLine(rect.center().x() - 1, rect.bottom() - 5, rect.right() - 4, rect.top() + 5)
        else:
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.setBrush(QColor(20, 24, 30, 140))
            painter.drawEllipse(rect)
            painter.setPen(QPen(Qt.GlobalColor.white, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(1, 1, -1, -1))


class CircularProgress(QWidget):
    """Compact corner progress ring for uploads."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(22, 22)
        self.progress = None
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(55)
        self.timer.timeout.connect(self._tick)

    def set_progress(self, current, total):
        self.progress = max(0.0, min(1.0, current / total)) if total else 0.0
        self.timer.stop()
        self.update()

    def start_activity(self):
        self.progress = None
        self.timer.start()
        self.update()

    def _tick(self):
        self.phase = (self.phase + 9) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(3, 3, -3, -3)
        painter.setPen(QPen(QColor(255, 255, 255, 225), 3.2))
        painter.drawEllipse(bounds)
        painter.setPen(QPen(QColor("#4285f4"), 3.2, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        span = 105 * 16 if self.progress is None else int(-360 * 16 * self.progress)
        start = int((90 - self.phase) * 16) if self.progress is None else 90 * 16
        painter.drawArc(bounds, start, span)


class CloudStatusIcon(QWidget):
    """Small state icon: cloud-check when backed up, outline while pending."""

    def __init__(self, status="pending", parent=None):
        super().__init__(parent)
        self.status = status
        self.setFixedSize(14, 14)
        self.setAccessibleName(self._description())
        self.setToolTip(self._description())

    def set_status(self, status):
        self.status = status
        self.setAccessibleName(self._description())
        self.setToolTip(self._description())
        self.update()

    def _description(self):
        if self.status == "uploaded":
            return "Backed up to cloud"
        if self.status == "uploading":
            return "Uploading to cloud"
        return "Not backed up to cloud"

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.scale(12 / 18, 12 / 18)
        painter.translate(1, 1)
        cloud = QPainterPath()
        cloud.moveTo(4, 13)
        cloud.cubicTo(1.5, 13, 1.5, 9, 4.5, 8)
        cloud.cubicTo(4.2, 5, 8, 4, 10, 6)
        cloud.cubicTo(12, 2, 16, 4, 15, 8)
        cloud.cubicTo(18, 8, 18, 13, 15, 13)
        cloud.closeSubpath()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#111827"), 3.8, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(cloud)
        painter.setPen(QPen(QColor("#ffffff"), 1.8, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(cloud)

        if self.status == "uploaded":
            painter.setPen(QPen(QColor("#111827"), 4.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(7, 9, 9, 11)
            painter.drawLine(9, 11, 13, 7)
            painter.setPen(QPen(QColor("#16a34a"), 2.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(7, 9, 9, 11)
            painter.drawLine(9, 11, 13, 7)
        elif self.status == "uploading":
            painter.setPen(QPen(QColor("#111827"), 4.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(9, 11, 9, 7)
            painter.drawLine(7, 9, 9, 7)
            painter.drawLine(9, 7, 11, 9)
            painter.setPen(QPen(QColor("#1a73e8"), 2.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            painter.drawLine(9, 11, 9, 7)
            painter.drawLine(7, 9, 9, 7)
            painter.drawLine(9, 7, 11, 9)
        else:
            painter.setPen(QPen(QColor("#111827"), 4.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(4, 15, 15, 4)
            painter.setPen(QPen(QColor("#dc2626"), 2.5, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawLine(4, 15, 15, 4)


class _ClickablePreview(QLabel):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thumbnail = QPixmap()
        self.placeholder = ""
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def set_thumbnail(self, pixmap):
        self.thumbnail = pixmap
        self.placeholder = ""
        self.update()

    def set_placeholder(self, text):
        self.thumbnail = QPixmap()
        self.placeholder = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(self.rect(), 12, 12)
        painter.setClipPath(clip)
        painter.fillPath(clip, QColor("#e8edf3"))
        if not self.thumbnail.isNull():
            painter.drawPixmap(self.rect(), self.thumbnail)
        elif self.placeholder:
            painter.setPen(QColor("#697586"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class PhotoTile(QFrame):
    details_requested = Signal(object)

    def __init__(self, item, status=None, selectable=False, parent=None):
        super().__init__(parent)
        self.item = item
        self.status = status or item.get("status", "pending")
        self.selection = None
        self.setObjectName("photoTile")
        self.setFixedSize(88, 64)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.preview = _ClickablePreview()
        self.preview.setFixedSize(88, 64)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet("background: transparent; border: none;")
        pixmap = media_thumbnail(item)
        if not pixmap.isNull():
            self.preview.set_thumbnail(pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            ))
        else:
            self.preview.setStyleSheet("font-size: 24px;")
            self.preview.set_placeholder("▶" if item.get("kind") == "Video" else "▧")
        self.preview.clicked.connect(lambda: self.details_requested.emit(self.item))
        root.addWidget(self.preview)

        self.cloud_icon = CloudStatusIcon(self.status, self.preview)
        self.cloud_icon.move(71, 3)
        if selectable:
            self.selection = SelectionMark(True, self.preview)
            self.selection.move(63, 38)
            self.selection.raise_()

        self.progress_ring = CircularProgress(self.preview)
        self.progress_ring.move(63, 38)
        self.progress_ring.hide()

    def set_status(self, status):
        self.status = status
        self.cloud_icon.set_status(status)
        if status == "uploaded":
            self.progress_ring.hide()
        elif status == "uploading":
            self.progress_ring.show()
            self.progress_ring.raise_()
            self.progress_ring.start_activity()
        elif status in {"pending", "waiting", "failed", "skipped"}:
            self.progress_ring.hide()

    def set_upload_progress(self, current, total):
        if self.status == "uploaded":
            self.progress_ring.hide()
            return
        self.progress_ring.show()
        self.progress_ring.raise_()
        self.progress_ring.set_progress(current, total)


class MediaDetailsDialog(QDialog):
    def __init__(self, item, status=None, uploaded_at=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(
            "Video details" if item.get("kind") == "Video" else "Photo details"
        )
        self.setMinimumSize(420, 440)
        self.item = item
        status = status or item.get("status", "pending")
        uploaded_at = uploaded_at or item.get("uploaded_at")

        layout = QVBoxLayout(self)
        if item.get("kind") == "Video":
            self._add_video_preview(layout, item)
        else:
            image = QLabel()
            image.setAlignment(Qt.AlignmentFlag.AlignCenter)
            image.setMinimumHeight(280)
            pixmap = media_full_preview(item)
            if not pixmap.isNull():
                image.setPixmap(pixmap.scaled(
                    QSize(720, 500),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            else:
                image.setText("Photo preview unavailable")
            layout.addWidget(image, 1)

        name = QLabel(item.get("name", Path(item.get("path", "")).name))
        name.setWordWrap(True)
        name.setStyleSheet("font-size: 15px; font-weight: 600;")
        layout.addWidget(name)
        layout.addWidget(QLabel(f"{item.get('kind', 'File')}  •  {self._format_size(item.get('size', 0))}"))
        status_row = QHBoxLayout()
        status_row.addStretch()
        status_icon = CloudStatusIcon(status)
        status_row.addWidget(status_icon)
        layout.addLayout(status_row)
        if uploaded_at:
            try:
                stamp = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
                uploaded_at = stamp.astimezone().strftime("%b %d, %Y at %I:%M %p")
            except (ValueError, TypeError):
                pass
            layout.addWidget(QLabel(f"Uploaded {uploaded_at}"))

    def _add_video_preview(self, layout, item):
        if QVideoWidget is not None:
            video = QVideoWidget(self)
            video.setMinimumSize(360, 260)
            self.video_player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.video_player.setAudioOutput(self.audio_output)
            self.video_player.setVideoOutput(video)
            self.video_player.setSource(QUrl.fromLocalFile(item["path"]))
            layout.addWidget(video, 1)

            controls = QHBoxLayout()
            self.play_button = QPushButton("Play video")
            self.play_button.clicked.connect(self.toggle_video)
            controls.addWidget(self.play_button)
            controls.addStretch()
            open_button = QPushButton("Open in default player")
            open_button.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(item["path"]))
            )
            controls.addWidget(open_button)
            layout.addLayout(controls)
        else:
            note = QLabel("Use your default player to view this video.")
            note.setAlignment(Qt.AlignmentFlag.AlignCenter)
            note.setMinimumHeight(280)
            layout.addWidget(note, 1)
            open_button = QPushButton("Open video")
            open_button.clicked.connect(
                lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(item["path"]))
            )
            layout.addWidget(open_button)

    def toggle_video(self):
        if self.video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.video_player.pause()
            self.play_button.setText("Resume video")
        else:
            self.video_player.play()
            self.play_button.setText("Pause video")

    @staticmethod
    def _format_size(size):
        value = float(size or 0)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}"
            value /= 1024
