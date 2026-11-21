
import json
import subprocess
import re
from pathlib import Path

INPUT_DIR = Path("input_videos")
OUTPUT_DIR = Path("output_shorts")
CANDIDATES_FILE = Path("data/highlight_candidates.json")

DAILY_TARGET = 15
WIDTH = 1080
HEIGHT = 1920


def safe_name(name):
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def create_short(video, candidate, output):
    start = float(candidate["start_seconds"])
    duration = float(candidate["end_seconds"]) - start

    if duration <= 0:
        raise ValueError("Invalid clip duration")

    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", str(video),
        "-t", str(duration),
        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        ),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(output)
    ]

    subprocess.run(command, check=True)


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not CANDIDATES_FILE.exists():
        raise SystemExit("Highlight candidates file not found.")

    with open(CANDIDATES_FILE, encoding="utf-8") as f:
        report = json.load(f)

    generated = 0

    for item in report.get("results", []):
        if generated >= DAILY_TARGET:
            break

        filename = Path(item["filename"])

        # Only process files inside input_videos.
        if filename.name != item["filename"]:
            continue

        video = INPUT_DIR / filename.name

        if not video.is_file():
            print("Source not found:", filename.name)
            continue

        for index, candidate in enumerate(item.get("candidates", []), 1):
            if generated >= DAILY_TARGET:
                break

            output_name = (
                f"{safe_name(video.stem)}_short_{index:02d}.mp4"
            )
            output = OUTPUT_DIR / output_name

            try:
                create_short(video, candidate, output)
                generated += 1
                print("Created:", output)
            except Exception as error:
                print("Failed:", output_name, error)

    print("Shorts generated:", generated)
    print("Daily target:", DAILY_TARGET)


if __name__ == "__main__":
    main()
