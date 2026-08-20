#!/usr/bin/env python3
"""
cli.py - Auto-detection only (Phase 1 CLI)

Usage:
    python src/cli.py --file video.mp4 --anchors 83.5 --output auto.json
"""

import argparse
import json
import os
import sys
import tempfile
import subprocess
from typing import List
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from core import (
    Config, LoadingSegment, AnalysisResult,
    detect_loading_from_anchor, get_video_duration,
    format_timestamp, parse_timestamp
)

def download_video(url: str, output_path: str, fmt: str = "18", browser: str = "firefox") -> str:
    """Download video via yt-dlp. Returns path to downloaded file."""
    cmd = [
        "yt-dlp",
        "-f", fmt,
        "-o", output_path,
        "--no-playlist",
        "--cookies-from-browser", browser,
        "--js-runtimes", "deno:/usr/bin/deno",
        "--remote-components", "ejs:npm",
        url
    ]
    print(f"[download] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[download] stderr: {result.stderr}", file=sys.stderr)
        print("[download] Retrying without format specifier...", file=sys.stderr)
        cmd_fallback = ["yt-dlp", "-o", output_path, "--no-playlist", url, "--cookies-from-browser", browser]
        result = subprocess.run(cmd_fallback, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {result.stderr}")

    base, _ = os.path.splitext(output_path)
    for ext in [".mp4", ".webm", ".mkv"]:
        candidate = base + ext
        if os.path.exists(candidate):
            return candidate
    if os.path.exists(output_path):
        return output_path
    dir_name = os.path.dirname(output_path) or "."
    for f in os.listdir(dir_name):
        if f.startswith(os.path.basename(base)):
            return os.path.join(dir_name, f)
    raise FileNotFoundError(f"Could not find downloaded file at {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Loading time detector (CLI mode)"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Path to local video file")
    group.add_argument("--url", help="Video URL (downloaded via yt-dlp)")

    parser.add_argument("--anchors", nargs="+", required=False,
                        help="Loading region anchor timestamps")
    parser.add_argument("--expected-loads", type=int, default=0,
                        help="Expected number of loading segments")
    parser.add_argument("--rta-time", type=str, default=None,
                        help="RTA submitted time")

    parser.add_argument("--purple-hue-min", type=float, default=250.0)
    parser.add_argument("--purple-hue-max", type=float, default=275.0)
    parser.add_argument("--purple-dominance", type=float, default=0.60)
    parser.add_argument("--search-window", type=float, default=25.0)
    parser.add_argument("--frame-fps", type=float, default=30.0)

    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON report path")
    parser.add_argument("--download-dir", default=tempfile.gettempdir(),
                        help="Directory for downloaded videos")

    args = parser.parse_args()

    config = Config(
        purple_hue_min=args.purple_hue_min,
        purple_hue_max=args.purple_hue_max,
        purple_dominance_ratio=args.purple_dominance,
        search_window_sec=args.search_window,
        frame_extraction_fps=args.frame_fps,
    )

    # Acquire video
    if args.url:
        timestr = time.strftime("%Y%m%d-%H%M%S")
        video_filename = "cached_" + timestr
        video_path = os.path.join(args.download_dir, video_filename)
        print(f"[main] Downloading from URL: {args.url}")
        video_path = download_video(args.url, video_path)
        print(f"[main] Downloaded to: {video_path}")
    else:
        video_path = args.file
        if not os.path.exists(video_path):
            print(f"[error] File not found: {video_path}", file=sys.stderr)
            sys.exit(1)
        print(f"[main] Using local file: {video_path}")

    # Probe duration
    try:
        duration = get_video_duration(video_path)
        print(f"[main] Video duration: {duration:.2f}s ({format_timestamp(duration)})")
    except Exception as e:
        print(f"[warn] Could not determine video duration: {e}", file=sys.stderr)
        duration = 0.0

    # Parse anchors
    anchors = []
    if args.anchors:
        anchors = [parse_timestamp(a) for a in args.anchors]
    else:
        print("\n[main] Enter anchor timestamps (one per line, empty line to finish):")
        while True:
            line = input(f"  Anchor #{len(anchors)+1} (or empty): ").strip()
            if not line:
                break
            try:
                anchors.append(parse_timestamp(line))
            except ValueError:
                print(f"    Invalid format: {line}")

    if not anchors:
        print("[main] No anchors provided. Nothing to do.")
        sys.exit(0)

    print(f"\n[main] {len(anchors)} anchor(s) provided:")
    for i, a in enumerate(anchors):
        print(f"  [{i+1}] {format_timestamp(a)} ({a:.2f}s)")

    if args.expected_loads:
        if len(anchors) != args.expected_loads:
            print(f"[warn] Expected {args.expected_loads} loads but got {len(anchors)} anchors!")

    # Run detection
    segments = []
    for i, anchor in enumerate(anchors):
        print(f"\n{'='*60}")
        print(f"[main] Processing anchor {i+1}/{len(anchors)}: {format_timestamp(anchor)}")
        print(f"{'='*60}")

        seg = detect_loading_from_anchor(anchor, video_path, config)
        if seg:
            segments.append(seg)

    # Build result
    result = AnalysisResult(
        video_path=video_path,
        total_duration_sec=duration,
        segments=segments,
    )

    if args.rta_time:
        result.rta_time_sec = parse_timestamp(args.rta_time)

    print(f"\n{'='*60}")
    print(f"[main] DETECTION RESULTS")
    print(f"{'='*60}")
    print(f"Video: {result.video_path}")
    print(f"Duration: {format_timestamp(result.total_duration_sec)}")
    print(f"Segments found: {len(result.segments)} / {args.expected_loads or '?'} expected")
    print()

    for i, seg in enumerate(segments):
        print(f"  [{i+1}] {format_timestamp(seg.start_sec)} → "
              f"{format_timestamp(seg.end_sec)} "
              f"({seg.duration:.3f}s, conf={seg.confidence:.0%})")

    total_load = result.total_loading_time
    print(f"\n  Total loading time: {total_load:.3f}s")

    if result.rta_time_sec > 0:
        print(f"  RTA time:           {format_timestamp(result.rta_time_sec)}")
        print(f"  Adjusted time:      {format_timestamp(result.adjusted_time)}")
        print(f"  Time removed:       {total_load:.3f}s")

    # Output report
    report = result.to_report()
    report_json = json.dumps(report, indent=2)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report_json)
        print(f"\n[main] Report written to: {args.output}")
    else:
        print(f"\n[main] Report:\n{report_json}")

    print(f"\n[main] Done.")


if __name__ == "__main__":
    main()
