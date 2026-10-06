from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import Qt

from app.ui.photo_tile import MediaDetailsDialog, PhotoTile


class ReviewFilesDialog(QDialog):
    """Choose media for upload from a thumbnail grid."""

    def __init__(self, items, large_file_checker, parent=None):
        super().__init__(parent)
        self.items = items
        self.large_file_checker = large_file_checker
        self.upload_items = []
        self.skip_items = []
        self.tiles = []
        self._details_dialog = None

        self.setWindowTitle("Review Files")
        self.setMinimumSize(760, 600)
        self.setStyleSheet("""
            QDialog { background: #f7f8fa; color: #202124; }
            QLabel { color: #202124; background: transparent; }
            QLabel#dialogTitle { font-size: 22px; font-weight: 600; }
            QLabel#dialogSubtitle, QLabel#summary { font-size: 13px; color: #5f6368; }
            QPushButton { background: #202124; color: white; border: none; border-radius: 9px; padding: 9px 16px; font-size: 13px; }
            QPushButton:hover { background: #303134; }
            QPushButton#secondaryButton { background: #e8eaed; color: #202124; }
            QPushButton#secondaryButton:hover { background: #dadce0; }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)
        title = QLabel("Review Files")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("Select photos and videos to upload. Click a thumbnail to view its details.")
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        action_row = QHBoxLayout()
        select_all_button = QPushButton("Select All")
        select_all_button.setObjectName("secondaryButton")
        select_all_button.clicked.connect(self.select_all)
        deselect_button = QPushButton("Deselect All")
        deselect_button.setObjectName("secondaryButton")
        deselect_button.clicked.connect(self.deselect_all)
        action_row.addWidget(select_all_button)
        action_row.addWidget(deselect_button)
        action_row.addStretch()
        root.addLayout(action_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        grid_host = QWidget()
        self.grid = QGridLayout(grid_host)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        for index, item in enumerate(items):
            tile = PhotoTile(item, status="pending", selectable=True)
            tile.details_requested.connect(self.show_details)
            checkbox = tile.selection
            checkbox.setAccessibleName(f"Select {item.get('name', 'file')} for upload")
            checkbox.toggled.connect(self.update_summary)
            self.tiles.append((tile, checkbox, item))
            self.grid.addWidget(tile, index, 0)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(grid_host)
        root.addWidget(scroll, 1)

        self.summary_label = QLabel()
        self.summary_label.setObjectName("summary")
        root.addWidget(self.summary_label)

        button_row = QHBoxLayout()
        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)
        skip_button = QPushButton("Skip Selected")
        skip_button.setObjectName("secondaryButton")
        skip_button.clicked.connect(self.skip_selected)
        upload_button = QPushButton("Upload Selected")
        upload_button.clicked.connect(self.upload_selected)
        button_row.addWidget(cancel_button)
        button_row.addStretch()
        button_row.addWidget(skip_button)
        button_row.addWidget(upload_button)
        root.addLayout(button_row)
        self._grid_host = grid_host
        self.update_summary()
        self.reflow_tiles()

    def reflow_tiles(self):
        if not hasattr(self, "grid") or not hasattr(self, "tiles"):
            return
        columns = max(1, min(8, (self.width() - 72) // 102))
        for index, (tile, _, _) in enumerate(self.tiles):
            self.grid.addWidget(tile, index // columns, index % columns)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow_tiles()

    def show_details(self, item):
        self._details_dialog = MediaDetailsDialog(item, status="pending", parent=self)
        self._details_dialog.open()

    def select_all(self):
        for _, selection, _ in self.tiles:
            selection.setChecked(True)

    def deselect_all(self):
        for _, selection, _ in self.tiles:
            selection.setChecked(False)

    def update_summary(self, *_args):
        selected = sum(1 for _, selection, _ in self.tiles if selection.isChecked())
        skipped = len(self.tiles) - selected
        self.summary_label.setText(
            f"{selected} selected for upload  •  {skipped} will be skipped"
        )

    def _collect(self):
        upload_items = []
        skip_items = []
        for _, selection, item in self.tiles:
            (upload_items if selection.isChecked() else skip_items).append(item)
        return upload_items, skip_items

    def upload_selected(self):
        upload_items, skip_items = self._collect()
        if not upload_items:
            QMessageBox.warning(self, "No Files Selected", "Please select at least one file to upload.")
            return
        self.upload_items, self.skip_items = upload_items, skip_items
        self.accept()

    def skip_selected(self):
        upload_items, skip_items = self._collect()
        if not skip_items:
            QMessageBox.warning(self, "No Files Selected", "Deselect at least one file to skip it.")
            return
        self.upload_items, self.skip_items = upload_items, skip_items
        self.accept()

    def selected_files(self):
        return self.upload_items, self.skip_items
