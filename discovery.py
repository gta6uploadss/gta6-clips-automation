
import os
import re
import json
import math
from datetime import datetime, timezone, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

API_KEY = os.environ["YOUTUBE_API_KEY"]
youtube = build("youtube", "v3", developerKey=API_KEY)

HISTORY_FILE = "data/history.json"
SEARCH_QUERY = '"GTA 6"|"GTA VI"|"Grand Theft Auto VI"'

GTA6_PATTERN = re.compile(
    r"\b(gta\s*6|gta\s*vi|grand theft auto\s*(vi|6))\b",
    re.IGNORECASE
)


def is_relevant(video):
    snippet = video.get("snippet", {})
    text = " ".join([
        snippet.get("title", ""),
        snippet.get("description", ""),
        " ".join(snippet.get("tags", []))
    ])
    return bool(GTA6_PATTERN.search(text))


def discover(event_type):
    print(f"Searching globally: {event_type}")

    params = {
        "part": "snippet",
        "q": SEARCH_QUERY,
        "type": "video",
        "eventType": event_type,
        "order": "viewCount",
        "maxResults": 50
    }

    if event_type == "completed":
        params["publishedAfter"] = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).isoformat()

    response = youtube.search().list(**params).execute()
    return response.get("items", [])


def collect():
    candidates = {}

    for event_type in ["live", "completed"]:
        try:
            for item in discover(event_type):
                video_id = item["id"]["videoId"]

                candidates.setdefault(video_id, {
                    "video_id": video_id,
                    "event_type": event_type,
                    "url": f"https://www.youtube.com/watch?v={video_id}"
                })

        except HttpError as error:
            print(f"Discovery error: {error}")

    return list(candidates.values())


def add_statistics(videos):
    for start in range(0, len(videos), 50):
        batch = videos[start:start + 50]
        ids = ",".join(v["video_id"] for v in batch)

        response = youtube.videos().list(
            part="snippet,statistics,liveStreamingDetails",
            id=ids
        ).execute()

        batch_lookup = {v["video_id"]: v for v in batch}

        for item in response.get("items", []):
            video = batch_lookup.get(item["id"])
            if not video:
                continue

            snippet = item.get("snippet", {})
            video.update({
                "title": snippet.get("title", ""),
                "description": snippet.get("description", ""),
                "channel": snippet.get("channelTitle", ""),
                "channel_id": snippet.get("channelId", ""),
                "published_at": snippet.get("publishedAt", ""),
                "language": (
                    snippet.get("defaultAudioLanguage")
                    or snippet.get("defaultLanguage")
                    or "unknown"
                )
            })

            if not is_relevant(item):
                video["relevant"] = False
                continue

            video["relevant"] = True

            stats = item.get("statistics", {})
            live = item.get("liveStreamingDetails", {})

            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            viewers = int(live.get("concurrentViewers", 0))

            video.update({
                "views": views,
                "likes": likes,
                "comments": comments,
                "concurrent_viewers": viewers
            })

            published = datetime.fromisoformat(
                video["published_at"].replace("Z", "+00:00")
            )

            age_hours = max(
                0,
                (datetime.now(timezone.utc) - published).total_seconds()
                / 3600
            )

            popularity = min(math.log10(views + 1) / 7, 1)

            # Missing comments are not treated as proof of zero engagement.
            engagement = min(
                ((likes + comments * 2) / max(views, 1)) / 0.08,
                1
            )

            live_score = min(math.log10(viewers + 1) / 5, 1)
            freshness = max(0, 1 - age_hours / (30 * 24))

            base_score = (
                popularity * 0.35
                + engagement * 0.20
                + live_score * 0.25
                + freshness * 0.20
            ) * 100

            video["base_score"] = round(base_score, 2)
            video["score"] = round(base_score, 2)

    return [v for v in videos if v.get("relevant") is True]


def load_history():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        print("History file unreadable. Starting a fresh history.")
        return {}


def update_history(videos):
    history = load_history()
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()

    for video in videos:
        video_id = video["video_id"]
        snapshots = history.setdefault(video_id, [])

        # Keep only the last 30 days.
        cutoff = now - timedelta(days=30)
        snapshots = [
            s for s in snapshots
            if datetime.fromisoformat(s["timestamp"]) >= cutoff
        ]

        previous = snapshots[-1] if snapshots else None

        current_snapshot = {
            "timestamp": timestamp,
            "views": video["views"],
            "concurrent_viewers": video["concurrent_viewers"]
        }

        if previous:
            previous_time = datetime.fromisoformat(previous["timestamp"])
            elapsed_hours = (
                now - previous_time
            ).total_seconds() / 3600

            if elapsed_hours > 0:
                views_gained = max(
                    0, video["views"] - previous["views"]
                )

                views_per_hour = views_gained / elapsed_hours

                growth_score = min(
                    math.log10(views_per_hour + 1) / 4,
                    1
                ) * 100

                video["previous_views"] = previous["views"]
                video["views_gained"] = views_gained
                video["views_per_hour"] = round(views_per_hour, 2)
                video["growth_score"] = round(growth_score, 2)

                # Combine existing popularity score with measured growth.
                video["score"] = round(
                    video["base_score"] * 0.75
                    + growth_score * 0.25,
                    2
                )

                video["growth_tracking"] = "Historical comparison available"
            else:
                video["growth_tracking"] = "Waiting for next snapshot"
        else:
            video["growth_tracking"] = "Baseline saved; awaiting next run"

        snapshots.append(current_snapshot)

        # Retain a maximum of 20 snapshots per video.
        history[video_id] = snapshots[-20:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=2)

    print(f"Historical data updated for {len(videos)} videos.")


def main():
    print("GTA 6 GLOBAL DISCOVERY V3")
    print("=" * 40)

    videos = collect()
    videos = add_statistics(videos)

    update_history(videos)

    videos.sort(
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_discovered": len(videos),
        "ranking_method": (
            "Base score 75%, historical views-per-hour growth 25% "
            "when historical data is available"
        ),
        "videos": videos
    }

    os.makedirs("reports", exist_ok=True)

    filename = (
        "reports/discovery_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        + ".json"
    )

    with open(filename, "w", encoding="utf-8") as file:
        json.dump(report, file, indent=2, ensure_ascii=False)

    print(f"Total relevant videos: {len(videos)}")
    print(f"Report saved: {filename}")

    for video in videos[:15]:
        print(
            video["score"],
            video["event_type"],
            video.get("views_per_hour", "Awaiting history"),
            video["title"],
            video["url"]
        )


if __name__ == "__main__":
    main()
