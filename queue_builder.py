
import json
import glob
import os
from datetime import datetime, timezone

DAILY_TARGET = 15
OUTPUT_FILE = "data/trend_queue.json"


def main():
    reports = sorted(glob.glob("reports/discovery_*.json"))

    if not reports:
        raise SystemExit("No discovery report found.")

    with open(reports[-1], encoding="utf-8") as f:
        report = json.load(f)

    videos = report.get("videos", [])

    videos.sort(
        key=lambda video: float(video.get("score", 0) or 0),
        reverse=True
    )

    queue = {
        "daily_target": DAILY_TARGET,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_discovered": len(videos),
        "selected_count": min(len(videos), DAILY_TARGET),
        "purpose": "trend_analysis_and_highlight_detection",
        "videos": videos[:DAILY_TARGET]
    }

    os.makedirs("data", exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)

    print("Total discovered:", len(videos))
    print("Top videos selected:", queue["selected_count"])
    print("Trend queue created:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
