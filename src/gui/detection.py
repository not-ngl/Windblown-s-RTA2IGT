"""
detection.py - Automatic detection with progress display (sequential and parallel)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QGroupBox, QProgressBar,
    QListWidget, QListWidgetItem, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QObject, QThread
from PySide6.QtGui import QFont, QColor
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from core import Config, detect_loading_from_anchor, format_timestamp

class DetectionWorker(QObject):
    """Background thread for auto-detection with optional parallelism."""
    progress = Signal(int, int, str)  # completed, total, status_text
    finished = Signal(list)           # List[LoadingSegment]
    error = Signal(str)

    def __init__(self, video_path, anchors, config, parallel=True):
        super().__init__()
        self.video_path = video_path
        self.anchors = anchors
        self.config = config
        self.parallel = parallel
        self.cancelled = False

    def run(self):
        all_segments = []
        total_tasks = len(self.anchors)
        
        try:
            if self.parallel:
                with ThreadPoolExecutor(max_workers=min(6, len(self.anchors))) as executor:
                    future_to_anchor = {
                        executor.submit(self._detect_anchor, i, anchor): i
                        for i, anchor in enumerate(self.anchors)
                    }
                    
                    for future in as_completed(future_to_anchor):
                        if self.cancelled:
                            break
                        
                        anchor_idx = future_to_anchor[future]
                        try:
                            segs = future.result()
                            if segs:
                                for seg in segs:
                                    seg.anchor_idx = anchor_idx
                                all_segments.extend(segs)
                            
                            completed = len([f for f in future_to_anchor if f.done()])
                            self.progress.emit(completed, total_tasks, f"Processing... {completed}/{total_tasks} anchors")
                        except Exception as e:
                            print(f"[detect] Anchor {anchor_idx} failed: {e}")
                            completed = len([f for f in future_to_anchor if f.done()])
                            self.progress.emit(completed, total_tasks, f"Warning: anchor {anchor_idx} failed")
            else:
                for i, anchor in enumerate(self.anchors):
                    if self.cancelled:
                        break
                    
                    self.progress.emit(i, total_tasks, f"Processing anchor {i+1}/{len(self.anchors)}...")
                    
                    segs = self._detect_anchor(i, anchor)
                    if segs:
                        for seg in segs:
                            seg.anchor_idx = i
                            all_segments.append(seg)
                    
                    self.progress.emit(i + 1, total_tasks, f"Anchor {i+1}/{len(self.anchors)} complete")

        except Exception as e:
            self.error.emit(f"Detection failed: {str(e)}")
            return

        all_segments.sort(key=lambda s: getattr(s, 'anchor_idx', 0))
        
        if not self.cancelled:
            self.finished.emit(all_segments)

    def _detect_anchor(self, anchor_idx, anchor_ts):
        seg = detect_loading_from_anchor(anchor_ts, self.video_path, self.config)
        if seg:
            return [seg] if not isinstance(seg, list) else seg
        return []

    def cancel(self):
        self.cancelled = True

class DetectionWidget(QWidget):
    """Detection screen with progress and results (parallel/sequential toggle + reset)."""
    
    detection_complete = Signal(list)
    back_requested = Signal()
    reset_requested = Signal()

    def __init__(self, video_path="", anchors=[], config=None):
        super().__init__()
        self.video_path = video_path
        self.anchors = anchors
        self.config = config or Config()
        self.segments = []
        self.worker = None
        self.thread = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(15, 15, 15, 15)
        self.setLayout(layout)

        # Title
        title = QLabel("Automatic expansion to find start and end of loading")
        title.setProperty("heading", "true")
        layout.addWidget(title)

        # ========== INPUT SUMMARY ==========
        info_group = QGroupBox("Input Summary")
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(8)
        info_layout.setContentsMargins(12, 12, 12, 12)
        
        self.info_label = QLabel()
        self.info_label.setOpenExternalLinks(True)
        self.info_label.setTextFormat(Qt.TextFormat.RichText)
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("""
            QLabel {
                color: #D5F4F5;
                font-size: 13px;
                padding: 0;
            }
        """)
        self.info_label.setMinimumHeight(120)
        info_layout.addWidget(self.info_label)
        
        info_layout.addStretch()
        
        self.parallel_checkbox = QCheckBox("Parallel mode")
        self.parallel_checkbox.setChecked(True)
        self.parallel_checkbox.setStyleSheet("color: #cc33ba; font-size: 13px; margin-top: 8px;")
        self.parallel_checkbox.setToolTip("Process all anchors simultaneously. Disable if you experience issues.")
        info_layout.addWidget(self.parallel_checkbox)
        
        layout.addWidget(info_group)

        # ========== DETECTION PROGRESS ==========
        progress_group = QGroupBox("Detection Progress")
        progress_layout = QVBoxLayout(progress_group)
        progress_layout.setSpacing(8)
        progress_layout.setContentsMargins(12, 12, 12, 12)
        
        self.status_label = QLabel("Ready to start detection")
        self.status_label.setStyleSheet("color: #D5F4F5; font-size: 13px;")
        progress_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        layout.addWidget(progress_group)

        # ========== DETECTED SEGMENTS ==========
        self.results_group = QGroupBox("Detected Segments")
        results_layout = QVBoxLayout(self.results_group)
        results_layout.setSpacing(8)
        results_layout.setContentsMargins(12, 12, 12, 12)
        
        self.segment_list = QListWidget()
        self.segment_list.setMinimumHeight(150)
        self.segment_list.setStyleSheet(
            "QListWidget { background-color: #1A0B28; color: #D5F4F5; border: 2px solid #9432a1; border-radius: 4px; }"
            "QListWidget::item { padding: 8px; border-bottom: 1px solid #444; }"
            "QListWidget::item:selected { background-color: rgba(242, 0, 157, 0.25); color: #fff; }"
        )
        results_layout.addWidget(self.segment_list)
        
        layout.addWidget(self.results_group)

        # ========== BUTTONS ==========
        btn_layout = QHBoxLayout()
        
        # BACK (anchor)
        self.back_btn = QPushButton("Back")
        self.back_btn.setProperty("secondary", "true")
        self.back_btn.clicked.connect(self.back_requested.emit)
        btn_layout.addWidget(self.back_btn)

        # RESET BUTTON (appears after detection completes)
        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setProperty("secondary", "true")
        self.reset_btn.setMinimumHeight(40)
        self.reset_btn.clicked.connect(self._reset_detection)
        self.reset_btn.setEnabled(False)  
        btn_layout.addWidget(self.reset_btn)
        
        btn_layout.addStretch()
        
        # START PROCESS
        self.start_btn = QPushButton("Start Detection")
        self.start_btn.setProperty("primary", "true")
        self.start_btn.clicked.connect(self.start_detection)
        self.start_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.start_btn, stretch=1)
        
        # CONTINUE (verify)
        self.continue_btn = QPushButton("Continue to Verification")
        self.continue_btn.setProperty("primary", "true")
        self.continue_btn.clicked.connect(lambda: self.detection_complete.emit(self.segments))
        self.continue_btn.setEnabled(False)
        self.continue_btn.setMinimumHeight(40)
        btn_layout.addWidget(self.continue_btn, stretch=1)
        
        layout.addLayout(btn_layout)

        self._update_info()

    def _update_info(self):
        video_name = os.path.basename(self.video_path) if self.video_path else "None"
        
        html = f"""
        <div style="text-align: left;">
            <b>Video:</b> {video_name}<br>
            <b>Number of Anchors:</b> {len(self.anchors)}<br><br>
            <span style="color: #cc33ba; font-weight: 600;">Anchor list:</span><br>
        """
        
        if self.anchors:
            for i, anchor in enumerate(self.anchors):
                html += f"&nbsp;&nbsp;&nbsp;&nbsp;• {format_timestamp(anchor)} ({anchor:.2f}s)<br>"
        
        html += "</div>"
        self.info_label.setText(html)

    def _reset_detection(self):
        """Reset detection state and allow re-running detection."""
        self.segments = []
        self.progress_bar.setValue(0)
        self.status_label.setText("Ready to start detection")
        self.segment_list.clear()
        
        # Re-enable start button, disable continue
        self.start_btn.setEnabled(True)
        self.start_btn.setText("Start Detection")
        self.continue_btn.setEnabled(False)
        self.reset_btn.setEnabled(False)
        self.parallel_checkbox.setEnabled(True)
        
        # Clear any running worker
        if self.worker:
            self.worker.cancel()
            self.worker = None

    def start_detection(self):
        parallel_mode = self.parallel_checkbox.isChecked()
        mode_text = "Parallel" if parallel_mode else "Sequential"
        
        self.start_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Initializing {mode_text} detection...")
        self.parallel_checkbox.setEnabled(False)
        self.reset_btn.setEnabled(False)

        self.thread = QThread()
        self.worker = DetectionWorker(
            self.video_path, 
            self.anchors, 
            self.config,
            parallel=parallel_mode
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker.deleteLater)

        self.thread.start()

    def on_progress(self, completed, total, status_text):
        self.status_label.setText(status_text)
        progress = int((completed / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)

    def on_finished(self, segments):
        self.segments = segments
        self.progress_bar.setValue(100)
        mode_text = "Parallel" if self.parallel_checkbox.isChecked() else "Sequential"
        self.status_label.setText(f"✓ {mode_text} detection complete - {len(segments)} segments found")
        
        self.start_btn.setEnabled(True)
        self.start_btn.setText("Run Detection Again")
        self.back_btn.setEnabled(True)
        self.parallel_checkbox.setEnabled(True)
        self.reset_btn.setEnabled(True)  # Enable reset button
        
        self.segment_list.clear()
        total_load = 0.0
        
        for i, seg in enumerate(segments):
            item_text = (f"#{i+1}  {format_timestamp(seg.start_sec)} → {format_timestamp(seg.end_sec)}  "
                        f"({seg.duration:.3f}s, conf={seg.confidence:.0%})")
            item = QListWidgetItem(item_text)
            self.segment_list.addItem(item)
            total_load += seg.duration
        
        summary_item = QListWidgetItem("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        summary_item.setForeground(QColor("#F2009D"))
        self.segment_list.addItem(summary_item)
        
        summary = QListWidgetItem(f"Total loading time: {total_load:.3f}s")
        summary.setForeground(QColor("#cc33ba"))
        summary.setFont(QFont("Sofia Sans", 11, QFont.Weight.Bold))
        self.segment_list.addItem(summary)

        self.continue_btn.setEnabled(True)

    def on_error(self, error_msg):
        QMessageBox.critical(self, "Detection Error", error_msg)
        self.start_btn.setEnabled(True)
        self.back_btn.setEnabled(True)
        self.parallel_checkbox.setEnabled(True)
        self.reset_btn.setEnabled(True)
        self.status_label.setText("Error occurred")
