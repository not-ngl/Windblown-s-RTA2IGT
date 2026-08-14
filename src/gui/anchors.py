"""
anchors.py - Anchor input with spectrogram and frame preview
"""

import sys
import os
import tempfile
import subprocess
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QListWidget, QListWidgetItem, QMessageBox, QGraphicsView,
    QGraphicsScene, QGraphicsPixmapItem, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QWheelEvent
import numpy as np
from PIL import Image

try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    print("[warn] opencv-python not installed")

import scipy.signal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

class SpectrogramGenerator:
    """Offline spectrogram generation - returns PIL image."""
    
    @staticmethod
    def generate(video_path: str, width=1720, height=350):
        if not HAS_OPENCV:
            return None
        if not video_path or not os.path.exists(video_path):
            return None
            
        temp_wav = tempfile.mktemp(suffix='.wav')
        cmd = ['ffmpeg', '-y', '-i', video_path, '-vn', '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '1', temp_wav]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[spec] ffmpeg audio extract failed: {result.stderr}")
            return None
        
        try:
            from scipy.io.wavfile import read
            rate, data = read(temp_wav)
            os.remove(temp_wav)
        except Exception as e:
            print(f"[spec] Failed to load WAV: {e}")
            return None
        
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        
        audio = data.astype(np.float32) / 32768.0
        f, t, Zxx = scipy.signal.stft(audio, fs=rate, nperseg=2048, noverlap=1536)
        power_db = 10 * np.log10(np.abs(Zxx)**2 + 1e-10)
        
        p_min, p_max = np.percentile(power_db, [2, 98])
        img = np.clip((power_db - p_min) / (p_max - p_min + 1e-10), 0, 1)
        img = (img * 255).astype(np.uint8)
        img = np.flipud(img)
        img_resized = cv2.resize(img, (width, height), interpolation=cv2.INTER_LINEAR)
        img_color = cv2.applyColorMap(img_resized, cv2.COLORMAP_MAGMA)
        img_rgb = cv2.cvtColor(img_color, cv2.COLOR_BGR2RGB)
        
        pil_img = Image.fromarray(img_rgb)
        metadata = {
            'time_max': float(t[-1]) if len(t) > 0 else 10.0,
            'freq_max': float(f[-1]) if len(f) > 0 else 11025.0,
            'width': width,
            'height': height
        }
        
        return pil_img, metadata

class ZoomGraphicsView(QGraphicsView):
    """Custom QGraphicsView with X-axis only zoom."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._zoom_factor = 1.1
        self._min_scale_x = 0.1
        self._max_scale_x = 10.0
        self._current_scale_x = 1.0
        self.setMouseTracking(True)
        
    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            pos = event.position()
            delta = event.angleDelta().y()
            
            factor = self._zoom_factor if delta > 0 else 1.0 / self._zoom_factor
            new_scale = max(self._min_scale_x, min(self._max_scale_x, self._current_scale_x * factor))
            
            before = self.mapToScene(pos.toPoint())
            
            self.resetTransform()
            self.scale(new_scale, 1.0)
            
            after = self.mapToScene(pos.toPoint())
            offset = before - after
            self.translate(offset.x(), 0)
            
            self._current_scale_x = new_scale
            event.accept()
            return
        
        event.ignore()

    def set_horizontal_scale(self, scale: float):
        self._current_scale_x = max(self._min_scale_x, min(self._max_scale_x, scale))
        self.resetTransform()
        self.scale(self._current_scale_x, 1.0)

    def get_horizontal_scale(self) -> float:
        return self._current_scale_x

class FramePreviewWidget(QWidget):
    """Display video frame preview with timestamp label."""

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.last_timestamp = 0.0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.setLayout(layout)

        # Scroll area for frame
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMaximumHeight(400)
        self.scroll_area.setMinimumWidth(450)
        self.scroll_area.setStyleSheet("border: 2px solid #9432a1; border-radius: 0px; background-color: #0B0B28;")

        # Frame display widget
        self.frame_widget = QWidget()
        self.frame_layout = QVBoxLayout()
        self.frame_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame_widget.setLayout(self.frame_layout)

        self.frame_label = QLabel("Click spectrogram to load frame")
        self.frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.frame_label.setMinimumSize(320, 180)
        self.frame_label.setMaximumWidth(960)
        self.frame_label.setStyleSheet("color: #7e8791;")
        self.frame_layout.addWidget(self.frame_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.scroll_area.setWidget(self.frame_widget)
        layout.addWidget(self.scroll_area)

        # Timestamp label (compact)
        self.timestamp_label = QLabel("t = 0.000s")
        self.timestamp_label.setStyleSheet("color: #cc33ba; font-size: 11px; font-weight: 600;")
        self.timestamp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.timestamp_label)

    def set_frame(self, pixmap: QPixmap, timestamp: float):
        """Update displayed frame."""
        self.last_timestamp = timestamp

        if pixmap.isNull():
            self.frame_label.setText("Failed to load frame")
            self.frame_label.setStyleSheet("color: #7e8791;")
        else:
            # Scale to fit
            target_w = min(640, self.frame_label.maximumWidth())
            target_h = int(target_w * 9 / 16)
            scaled = pixmap.scaled(
                target_w, target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.frame_label.setPixmap(scaled)
            self.frame_label.setText("")

        self.timestamp_label.setText(f"t = {timestamp:.3f}s")

    def clear(self):
        """Clear preview."""
        self.frame_label.setText("Click spectrogram to load frame")
        self.timestamp_label.setText("t = 0.000s")


def extract_frame(video_path: str, timestamp: float, width=320, height=180) -> QPixmap:
    """Extract single frame from video at timestamp."""
    try:
        cmd = [
            'ffmpeg', '-y', '-ss', f'{timestamp:.3f}',
            '-i', video_path,
            '-vframes', '1',
            '-vf', f'scale={width}:{height},setsar=1',
            '-f', 'image2pipe', '-vcodec', 'ppm', '-'
        ]
        result = subprocess.run(cmd, capture_output=True)

        if result.returncode != 0 or len(result.stdout) == 0:
            print(f"[frame] Failed at {timestamp}: {result.stderr[:100]}")
            return QPixmap()

        # Qt handles PPM native
        pixmap = QPixmap()
        pixmap.loadFromData(result.stdout, 'PPM')

        if pixmap.isNull():
            print(f"[frame] QPixmap creation failed at {timestamp}")
            return QPixmap()

        return pixmap

    except Exception as e:
        print(f"[frame] Error at {timestamp}: {e}")
        return QPixmap()


class SpectrogramViewer(QWidget):
    """Display pre-rendered spectrogram image with clickable anchors."""
    
    anchor_added = Signal(float)
    anchor_clicked = Signal(float) 

    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.anchors = []
        self.image = None
        self.metadata = None
        self.selected_timestamp = 0.0
        
        self.setMinimumSize(800, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.setLayout(layout)
        
        self.scene = QGraphicsScene(self)
        self.view = ZoomGraphicsView(self.scene)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.view.setBackgroundBrush(QColor('#0B0B28'))
        self.view.mousePressEvent = self.on_mouse_click
        self.view.mouseMoveEvent = self.on_mouse_move
        
        layout.addWidget(self.view, stretch=1)
        
        # Compact status bar (removed zoom %, kept time + controls)
        self.status = QLabel("Click spectrogram to add anchor | Ctrl+Scroll to zoom X")
        self.status.setStyleSheet("color: #7e8791; padding: 5px; font-size: 11px;")
        self.status.setMinimumHeight(24)
        layout.addWidget(self.status)

    def set_video(self, video_path: str):
        if not video_path or not os.path.exists(video_path):
            self.status.setText("Invalid video path")
            return False
        
        self.video_path = video_path
        
        if not HAS_OPENCV:
            self.status.setText("OpenCV required for spectrogram")
            return False
            
        try:
            result = SpectrogramGenerator.generate(video_path)
            if not result:
                self.status.setText("Failed to generate spectrogram")
                return False
                
            self.image, self.metadata = result
            
            img_arr = np.array(self.image)
            h, w, d = img_arr.shape
            qimage = QImage(img_arr.data, w, h, d * w, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimage)
            
            self.scene.clear()
            self.pixmap_item = QGraphicsPixmapItem(pixmap)
            self.scene.addItem(self.pixmap_item)
            
            self.view.setSceneRect(0, 0, w, h)
            self.view.fitInView(0, 0, w, h, Qt.AspectRatioMode.IgnoreAspectRatio)
            self.view.set_horizontal_scale(1.0)
            
            self.status.setText("Loaded | Click to add anchor | Ctrl+Scroll to zoom X")
            return True
            
        except Exception as e:
            print(f"[spectrogram] Error: {e}")
            self.status.setText(f"Error: {str(e)[:80]}")
            return False

    def pixel_to_time(self, screen_x: int) -> float:
        if not self.metadata:
            return 0.0
        
        scene_point = self.view.mapToScene(screen_x, 0)
        scene_x = scene_point.x()
        scene_x = max(0, min(scene_x, self.metadata['width']))
        
        rel_x = scene_x / self.metadata['width']
        return rel_x * self.metadata['time_max']

    def on_mouse_click(self, event):
        pos = event.pos()
        ts = self.pixel_to_time(pos.x())
        self.selected_timestamp = ts
        self.anchors.append(ts)
        self.anchors.sort()
        self.anchor_added.emit(ts)
        self.anchor_clicked.emit(ts)

    def on_mouse_move(self, event):
        pos = event.pos()
        ts = self.pixel_to_time(pos.x())
        self.status.setText(f"t = {ts:.2f}s | Click to add anchor | Ctrl+Scroll to zoom X")

    def get_selected_timestamp(self) -> float:
        return self.selected_timestamp

    def get_anchors(self) -> list:
        return sorted(self.anchors)

    def remove_anchor(self, timestamp: float):
        if timestamp in self.anchors:
            self.anchors.remove(timestamp)
            self.anchors.sort()

    def clear_anchors(self):
        self.anchors = []


class AnchorInputWidget(QWidget):
    """Combined widget: spectrogram + frame preview + anchor controls."""
    
    anchors_confirmed = Signal(list)
    back_requested = Signal() 

    def __init__(self, video_path: str = ""):
        super().__init__()
        self.video_path = video_path
        self._setup_ui()
        
        if self.video_path and os.path.exists(self.video_path):
            self.set_video_path(self.video_path)

    def set_video_path(self, video_path: str):
        self.video_path = video_path
        self.spectrogram_viewer.set_video(video_path)
        self.frame_preview.video_path = video_path

    def reset_for_new_video(self):
        """Reset widget for starting a fresh video workflow."""
        self.spectrogram_viewer.clear_anchors()
        self.anchor_list.clear()
        self.confirm_btn.setEnabled(False)
        self.frame_preview.clear()
        self.status.setText("Click spectrogram to add anchors")

    def _setup_ui(self):
        """Layout: Title → Spectrogram (full width) → Preview (60%) + Anchors (40%) → Confirm"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        self.setLayout(layout)

        # ========== TITLE (Compact) ==========
        title = QLabel("Manual anchoring of relevant loading")
        title.setProperty("heading", "true")
        layout.addWidget(title)

        # ========== CREATE WIDGETS FIRST ==========
        self.spectrogram_viewer = SpectrogramViewer("")
        self.spectrogram_viewer.anchor_added.connect(self.on_anchor_added)
        self.spectrogram_viewer.anchor_clicked.connect(self.update_frame_preview)
        self.spectrogram_viewer.setMinimumHeight(300)
        
        self.frame_preview = FramePreviewWidget(self.video_path if os.path.exists(self.video_path) else "")

        # ========== SPECTROGRAM (FULL WIDTH) ==========
        layout.addWidget(self.spectrogram_viewer, stretch=1)

        # ========== BOTTOM ROW: Preview + Anchors ==========
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(15)
        bottom_row.setContentsMargins(0, 0, 0, 0)
        
        # --- LEFT: Frame Preview ---
        preview_container = QVBoxLayout()
        preview_container.setSpacing(8)
        preview_container.setContentsMargins(0, 0, 0, 0)
        preview_container.addWidget(self.frame_preview, stretch=1)
        
        # --- RIGHT: Anchor List Panel ---
        anchor_panel = QVBoxLayout()
        anchor_panel.setSpacing(8)
        anchor_panel.setContentsMargins(0, 0, 0, 0)
        
        # Anchor list widget
        self.anchor_list = QListWidget()
        self.anchor_list.itemClicked.connect(self.on_anchor_selected)
        self.anchor_list.setMinimumHeight(150)
        self.anchor_list.setStyleSheet(
            "QListWidget { background-color: #1A0B28; border: 2px solid #9432a1; border-radius: 0px; color: #D5F4F5; }"
            "QListWidget::item { padding: 6px; border-radius: 0px; color: #D5F4F5; }"
            "QListWidget::item:selected { background-color: rgba(242, 0, 157, 0.25); border: 0px solid #F2009D; color: #fff; font-weight: 600; }"
            "QListWidget::item:hover:!selected { background-color: rgba(242, 0, 157, 0.15); }"
        )
        anchor_panel.addWidget(self.anchor_list, stretch=1)
        
        # Button row (full width below list, aligned with preview buttons)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        
        rem_btn = QPushButton("Remove Selected")
        rem_btn.setProperty("secondary", "true")
        rem_btn.clicked.connect(self._remove_selected)
        rem_btn.setMinimumHeight(36)
        btn_layout.addWidget(rem_btn, stretch=1)
        
        clr_btn = QPushButton("Clear All")
        clr_btn.setProperty("secondary", "true")
        clr_btn.clicked.connect(self._clear_all)
        clr_btn.setMinimumHeight(36)
        btn_layout.addWidget(clr_btn, stretch=1)
        
        anchor_panel.addLayout(btn_layout)
        
        # Add both columns to bottom row with stretch factors for 60/40 split
        bottom_row.addLayout(preview_container, stretch=3)
        bottom_row.addLayout(anchor_panel, stretch=2)
        
        layout.addLayout(bottom_row, stretch=1)

        # ========== STATUS BAR ==========
        self.status = QLabel("Click spectrogram to add anchors")
        self.status.setStyleSheet(
            "color: #7e8791; font-size: 11px; padding: 8px 8px; "
            "border-top: 1px solid #444; border-bottom: 1px solid #444; "
            "background-color: #0B0B28;"
        )
        layout.addWidget(self.status)

        # ========== BUTTON ROW ==========
        btn_row = QHBoxLayout()
        
        # BACK BUTTON  (loader)
        self.back_btn = QPushButton("Back")
        self.back_btn.setProperty("secondary", "true")
        self.back_btn.clicked.connect(self.back_requested.emit)
        self.back_btn.setMinimumHeight(40)
        btn_row.addWidget(self.back_btn)
        
        btn_row.addStretch()
        
        # CONFIRM BUTTON (detection)
        self.confirm_btn = QPushButton("Confirm Anchors")
        self.confirm_btn.setProperty("primary", "true")
        self.confirm_btn.clicked.connect(self._confirm)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setMinimumHeight(44)
        btn_row.addWidget(self.confirm_btn, stretch=1)
        
        layout.addLayout(btn_row)

    def update_frame_preview(self, timestamp: float):
        """Update frame preview at clicked timestamp."""
        frame = extract_frame(self.video_path, timestamp, width=320, height=180)
        self.frame_preview.set_frame(frame, timestamp)

    def on_anchor_selected(self, item):
        """Load frame when anchor selected from list."""
        ts = item.data(Qt.ItemDataRole.UserRole)
        frame = extract_frame(self.video_path, ts, width=320, height=180)
        self.frame_preview.set_frame(frame, ts)

    def on_anchor_added(self, ts: float):
        self._update_list()
        self.confirm_btn.setEnabled(len(self.spectrogram_viewer.get_anchors()) > 0)
        self.status.setText(f"✓ Added anchor at {ts:.2f}s")

    def _update_list(self):
        self.anchor_list.clear()
        for i, ts in enumerate(self.spectrogram_viewer.get_anchors()):
            item = QListWidgetItem(f"#{i+1}  {format_timestamp_short(ts)}  ({ts:.2f}s)")
            item.setData(Qt.ItemDataRole.UserRole, ts)
            self.anchor_list.addItem(item)

    def _remove_selected(self):
        item = self.anchor_list.currentItem()
        if item:
            ts = item.data(Qt.ItemDataRole.UserRole)
            self.anchor_list.takeItem(self.anchor_list.currentRow())
            self.spectrogram_viewer.remove_anchor(ts)
            self.confirm_btn.setEnabled(len(self.spectrogram_viewer.get_anchors()) > 0)
            if not self.spectrogram_viewer.get_anchors():
                self.frame_preview.clear()
            self.status.setText(f"✗ Removed anchor at {ts:.2f}s")

    def _clear_all(self):
        if self.spectrogram_viewer.get_anchors():
            self.spectrogram_viewer.clear_anchors()
            self.anchor_list.clear()
            self.confirm_btn.setEnabled(False)
            self.frame_preview.clear()
            self.status.setText("✗ Cleared all anchors")

    def _confirm(self):
        anchors = self.spectrogram_viewer.get_anchors()
        if not anchors:
            QMessageBox.warning(self, "No Anchors", "Add at least one anchor point")
            return
        self.anchors_confirmed.emit(anchors)

    def get_anchors(self) -> list:
        return self.spectrogram_viewer.get_anchors()


def format_timestamp_short(sec: float) -> str:
    """Short time format for list display."""
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"
