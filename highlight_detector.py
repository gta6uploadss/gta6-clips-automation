
import json
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone

INPUT_DIR = Path("input_videos")
OUTPUT_FILE = Path("data/highlight_candidates.json")

SCENE_THRESHOLD = "0.30"
CLIP_BEFORE = 12
CLIP_AFTER = 18
MAX_CANDIDATES_PER_VIDEO = 5


def get_duration(video):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video)
        ],
        capture_output=True,
        text=True,
        check=True
    )
    return float(result.stdout.strip())


def detect_scenes(video):
    command = [
        "ffmpeg",
        "-hide_banner",
        "-i", str(video),
        "-vf",
        f"select='gt(scene,{SCENE_THRESHOLD})',showinfo",
        "-an",
        "-f", "null",
        "-"
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    timestamps = re.findall(
        r"pts_time:([0-9.]+)",
        result.stderr
    )

    return [float(value) for value in timestamps]


def analyse_video(video):
    duration = get_duration(video)
    scenes = detect_scenes(video)

    candidates = []

    for timestamp in scenes:
        start = max(0, timestamp - CLIP_BEFORE)
        end = min(duration, timestamp + CLIP_AFTER)

        if end - start < 15:
            continue

        candidates.append({
            "start_seconds": round(start, 2),
            "end_seconds": round(end, 2),
            "scene_change_seconds": round(timestamp, 2),
            "duration_seconds": round(end - start, 2),
            "detection_type": "visual_scene_change"
        })

    candidates.sort(
        key=lambda item: item["scene_change_seconds"]
    )

    return candidates[:MAX_CANDIDATES_PER_VIDEO]


def main():
    INPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    results = []

    for video in INPUT_DIR.iterdir():
        if video.suffix.lower() not in {
            ".mp4", ".mkv", ".mov", ".webm"
        }:
            continue

        print("Analysing:", video.name)

        try:
            candidates = analyse_video(video)

            results.append({
                "filename": video.name,
                "candidate_count": len(candidates),
                "candidates": candidates
            })

        except Exception as error:
            print("Failed:", video.name, error)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "detection_method": "ffmpeg_scene_change",
        "videos_analysed": len(results),
        "results": results
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(output, file, indent=2)

    print("Videos analysed:", len(results))
    print("Report saved:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
