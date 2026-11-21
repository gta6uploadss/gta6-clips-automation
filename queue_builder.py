
import json
import glob
import os

SOURCE_FILE = "data/authorized_sources.json"
OUTPUT_FILE = "data/approved_queue.json"
DAILY_TARGET = 15


def main():
    with open(SOURCE_FILE, encoding="utf-8") as f:
        source_data = json.load(f)

    approved = {}

    for source in source_data.get("authorized_sources", []):
        required = [
            "channel_id",
            "permission_reference",
            "explicit_permission",
            "commercial_reuse",
            "editing_permission",
            "shorts_upload_permission"
        ]

        if all(source.get(key) for key in required):
            approved[source["channel_id"]] = source

    reports = sorted(glob.glob("reports/discovery_*.json"))

    if not reports:
        raise SystemExit("No discovery report found.")

    with open(reports[-1], encoding="utf-8") as f:
        report = json.load(f)

    eligible = []

    for video in report.get("videos", []):
        if video.get("channel_id") in approved:
            eligible.append(video)

    eligible.sort(
        key=lambda video: video.get("score", 0),
        reverse=True
    )

    queue = {
        "daily_target": DAILY_TARGET,
        "approved_count": len(eligible),
        "videos": eligible[:DAILY_TARGET],
        "status": "ready" if eligible else "waiting_for_authorized_sources"
    }

    os.makedirs("data", exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2, ensure_ascii=False)

    print("Approved videos:", len(eligible))
    print("Videos queued:", len(queue["videos"]))
    print("Status:", queue["status"])


if __name__ == "__main__":
    main()
