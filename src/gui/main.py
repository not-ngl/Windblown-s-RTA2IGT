"""
main.py - Main application window
"""

import sys
import os
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QStackedWidget, QMessageBox
from PySide6.QtCore import Qt

from .loader import VideoLoaderWidget
from .anchors import AnchorInputWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Windblown-s-RTA2IGT")
        self.setMinimumSize(900, 700)
        
        stack = QStackedWidget()
        self.setCentralWidget(stack)
        self.stack = stack
        
        # Stage 1: Video Loader
        self.loader_widget = VideoLoaderWidget()
        self.loader_widget.video_loaded.connect(self.on_video_loaded)
        self.stack.addWidget(self.loader_widget)
        
        # Stage 2: Anchors
        self.anchor_widget = AnchorInputWidget(video_path="")
        self.anchor_widget.anchors_confirmed.connect(self.on_anchors_confirmed)
        self.anchor_widget.back_requested.connect(self._handle_anchor_back)  # Connect back signal
        self.stack.addWidget(self.anchor_widget)
        
        # Stages 3+ created later (not upfront)
        self.detect_widget = None
        self.verify_widget = None

        self.current_video_path = None

    def on_video_loaded(self, video_path: str):
        self.current_video_path = video_path
        self.anchor_widget.set_video_path(video_path)
        self.stack.setCurrentIndex(1)

    def on_anchors_confirmed(self, anchors: list):
        from .detection import DetectionWidget
        from core import Config
        
        self.detect_widget = DetectionWidget(
            video_path=self.current_video_path,
            anchors=anchors,
            config=Config()
        )
        self.detect_widget.detection_complete.connect(self.on_detection_complete)
        self.detect_widget.back_requested.connect(lambda: self.stack.setCurrentIndex(1))
        self.stack.addWidget(self.detect_widget)
        self.stack.setCurrentIndex(2)

    def on_detection_complete(self, segments: list):
        from .verify import VerificationWidget
        
        self.verify_widget = VerificationWidget(
            video_path=self.current_video_path,
            segments=segments
        )
        self.verify_widget.back_requested.connect(lambda: self.stack.setCurrentIndex(2))
        self.verify_widget.restart_requested.connect(self._handle_full_restart)
        self.stack.addWidget(self.verify_widget)
        self.stack.setCurrentIndex(3)

    def _handle_anchor_back(self):
        """Handle back signal from Anchor screen - return to video loader (index 0)."""
        self.stack.setCurrentIndex(0)

    def _handle_full_restart(self):
        """Handle restart signal from Verification screen - reset to index 0."""
        if self.detect_widget:
            self.detect_widget.deleteLater()
            self.detect_widget = None
        
        if self.verify_widget:
            self.verify_widget.deleteLater()
            self.verify_widget = None
        
        self.anchor_widget.reset_for_new_video()
        self.stack.setCurrentIndex(0)

def main():
    app = QApplication(sys.argv)
    
    theme_path = os.path.join(os.path.dirname(__file__), '..', '..', 'theme.qss')
    if os.path.exists(theme_path):
        with open(theme_path, 'r') as f:
            app.setStyleSheet(f.read())
    else:
        app.setStyleSheet("""
            QGroupBox { font-weight: bold; margin-top: 10px; padding-top: 10px; }
            QLineEdit { padding: 5px; }
            QPushButton { padding: 8px 16px; }
        """)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
