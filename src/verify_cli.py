#!/usr/bin/env python3
"""
verify_cli.py - Interactive verification using nomacs

Usage:
    python src/verify_cli.py --file video.mp4 --auto-result auto.json --output corrected.json

Controls:
    [j]         : Step one frame earlier (-1/30s)
    [k]         : Step one frame later (+1/30s)
    [h]         : Step 5 frames earlier
    [l]         : Step 5 frames later
    [c] / ENTER : Confirm current timestamp
    [q]         : Quit session
    [r]         : Re-extract frame (if nomacs crashed)
"""

import argparse
import json
import os
import sys
import tempfile
from typing import List, Tuple
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from core import (
    Config, LoadingSegment, extract_frame_rgb, format_timestamp
)
from viewer import get_viewer, ImageViewerConfig


def save_frame(frame: np.ndarray, output_dir: str, timestamp: float) -> str:
    """Save frame as PNG to temp directory."""
    path = os.path.join(output_dir, f"frame_{timestamp:.6f}.png")
    import matplotlib.pyplot as plt
    plt.imsave(path, frame)
    return path


def load_keyart(video_path: str, anchor_sec: float, config: Config):
    """Extract reference KeyArt frame for comparison."""
    return extract_frame_rgb(video_path, anchor_sec)


class VerificationSession:
    def __init__(self, video_path: str, auto_segments: List[dict], 
                 config: Config, output_dir: str):
        self.video_path = video_path
        self.config = config
        self.output_dir = output_dir
        self.segments = [
                LoadingSegment(
                    start_sec=s['start_sec'],
                    end_sec=s['end_sec'],
                    confidence=s.get('confidence', 0.0)
                    )
                for s in auto_segments
                ]
        self.viewer = get_viewer("nomacs")
        self.view_config = ImageViewerConfig(fullscreen=False, keep_alive=True)
        self.fps = config.frame_extraction_fps
        self.step = 1.0 / self.fps

    def show_frame_at(self, timestamp: float, label: str = "") -> str:
        """Extract, save, and display frame with nomacs."""
        frame = extract_frame_rgb(self.video_path, timestamp)
        if frame is None:
            raise RuntimeError(f"Could not extract frame at {format_timestamp(timestamp)}")

        path = save_frame(frame, self.output_dir, timestamp)
        
        print(f"[{label}] Viewing: {format_timestamp(timestamp)}")
        self.viewer.show_image(path, self.view_config)
        
        return path

    def verify_boundary(self, segment_idx: int, boundary_type: str, 
                        initial_ts: float) -> float:
        """
        Interactive verification for one boundary (start or end).
        Returns confirmed timestamp.
        """
        current_ts = initial_ts
        mode_label = "START" if boundary_type == "start" else "END"

        while True:
            try:
                self.show_frame_at(current_ts, f"Segment {segment_idx+1} [{mode_label}]")
            except Exception as e:
                print(f"[error] Failed to display frame: {e}")
                resp = input("[r]etry / [q]uit / <skip>: ").lower().strip()
                if resp == 'q':
                    sys.exit(1)
                elif resp == 'r':
                    continue
                else:
                    return current_ts  # Skip

            # Read single character input
            try:
                import termios
                import tty
                
                fd = sys.stdin.fileno()
                old_settings = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    resp = sys.stdin.read(1)
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except (ImportError, OSError):
                # Fallback for Windows or non-interactive terminals
                resp = input("Action (arrowsj/k/h/l/c/q): ").lower().strip()

            if resp == 'q' or resp == 'exit':
                print("[abort] Session terminated by user")
                sys.exit(1)
            elif resp == 'c' or resp == '\n' or resp == 'enter':
                break
            elif resp == 'j':
                current_ts -= self.step
                print(f"  → Stepped earlier: {format_timestamp(current_ts)} ({-self.step:.4f}s)")
            elif resp == 'k':
                current_ts += self.step
                print(f"  → Stepped later: {format_timestamp(current_ts)} ({self.step:.4f}s)")
            elif resp == 'h':
                current_ts -= 5 * self.step
                print(f"  → Jumped earlier: {format_timestamp(current_ts)} ({-5*self.step:.4f}s)")
            elif resp == 'l':
                current_ts += 5 * self.step
                print(f"  → Jumped later: {format_timestamp(current_ts)} ({5*self.step:.4f}s)")
            else:
                print(f"  Invalid key '{resp}' - use j/k/h/l/c/q")

        return current_ts

    def verify_segment(self, idx: int, segment: LoadingSegment) -> Tuple[float, float]:
        """Interactive verification for one entire segment."""
        print(f"\n{'='*70}")
        print(f"SEGMENT {idx+1}/{len(self.segments)}")
        print(f"Auto-detected: {format_timestamp(segment.start_sec)} → {format_timestamp(segment.end_sec)}")
        print(f"Controls: a/d (±1 frame), j/k (±5 frames), c (confirm), q (quit)")
        print(f"{'='*70}\n")

        # Verify start boundary
        print("--- VERIFY START BOUNDARY ---")
        start_ts = self.verify_boundary(idx, "start", segment.start_sec)

        # Verify end boundary
        print("\n--- VERIFY END BOUNDARY ---")
        end_ts = self.verify_boundary(idx, "end", segment.end_sec)

        return start_ts, end_ts

    def run_all(self) -> List[LoadingSegment]:
        """Verify all segments interactively."""
        corrected = []

        for i, seg in enumerate(self.segments):
            start, end = self.verify_segment(i, seg)
            corrected.append(LoadingSegment(start_sec=start, end_sec=end))
            
            duration = end - start
            print(f"\n✓ Segment {i+1}: {format_timestamp(start)} → {format_timestamp(end)} ({duration:.3f}s)\n")

        return corrected

    def close(self):
        self.viewer.cleanup()


def main():
    parser = argparse.ArgumentParser(
        description="Interactive frame verification (using nomacs and VI navigation)"
    )
    parser.add_argument("--file", required=True, help="Video file path")
    parser.add_argument("--auto-result", required=True, 
                        help="JSON output from auto-detection (cli.py)")
    parser.add_argument("--output", "-o", required=True, 
                        help="Output corrected JSON path")
    parser.add_argument("--fps", type=float, default=30.0,
                        help="Frame stepping FPS (default: 30.0)")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress verbose output")

    args = parser.parse_args()

    # Load auto-detection results
    if not os.path.exists(args.auto_result):
        print(f"[error] Auto-result file not found: {args.auto_result}", file=sys.stderr)
        sys.exit(1)

    with open(args.auto_result) as f:
        auto_data = json.load(f)

    if "segments" not in auto_data or len(auto_data["segments"]) == 0:
        print("[error] No segments found in auto-result. Run cli.py first.", file=sys.stderr)
        sys.exit(1)

    config = Config(frame_extraction_fps=args.fps)

    # Create temp directory for frame previews
    output_dir = tempfile.mkdtemp(prefix="hybrid_verification_")
    print(f"[verify] Frame preview directory: {output_dir}")
    print(f"[verify] Press Ctrl+C to abort at any time\n")

    session = VerificationSession(
        args.file,
        auto_data["segments"],
        config,
        output_dir
    )

    try:
        corrected = session.run_all()
    except KeyboardInterrupt:
        print("\n[abort] Session interrupted by user")
        sys.exit(1)
    finally:
        session.close()

    # Build corrected report
    report = {
        "video": args.file,
        "total_duration_sec": auto_data.get("total_duration_sec", 0),
        "rta_time_sec": auto_data.get("rta_time_sec", 0),
        "segments": [s.to_dict() for s in corrected],
        "segment_count": len(corrected),
        "total_loading_sec": round(sum(s.duration for s in corrected), 3),
        "adjusted_time_sec": None,  # User can compute separately
        "verification_mode": "manual",
        "backend": "nomacs",
        "preview_dir": output_dir,
        "original_auto": args.auto_result,
        "correction_notes": ""
    }

    if auto_data.get("rta_time_sec"):
        total_load = sum(s.duration for s in corrected)
        report["adjusted_time_sec"] = round(auto_data["rta_time_sec"] - total_load, 3)

    # Write output
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*70}")
    print("[verify] VERIFICATION COMPLETE")
    print(f"{'='*70}")
    print(f"Segments corrected: {len(corrected)}")
    print(f"Total loading time: {report['total_loading_sec']:.3f}s")
    print(f"Corrected report:   {args.output}")
    print(f"Preview frames:     {output_dir}")

    if report.get("adjusted_time_sec") is not None:
        print(f"Adjusted RTA:       {format_timestamp(report['adjusted_time_sec'])}")

    print(f"\n[verify] Done.")


if __name__ == "__main__":
    main()
