
import os
import re
import json
import math
from datetime import datetime, timezone, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

API_KEY = os.environ["YOUTUBE_API_KEY"]
youtube = build("youtube", "v3", developerKey=API_KEY)

SEARCH_QUERY = (
    '"GTA 6"|"GTA VI"|'
    '"Grand Theft Auto VI"|"Grand Theft Auto 6"'
)

GTA6_PATTERN = re.compile(
    r"\b(gta\s*6|gta\s*vi|grand theft auto\s*(6|vi))\b",
    re.IGNORECASE
)

HISTORY_FILE = "data/history.json"
MAX_SNAPSHOTS = 30


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

                if video_id not in candidates:
                    candidates[video_id] = {
                        "video_id": video_id,
                        "event_type": event_type,
                        "url": (
                            "https://www.youtube.com/watch?v="
                            + video_id
                        )
                    }

        except HttpError as error:
            print(f"Discovery error: {error}")

    return list(candidates.values())


def load_history():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        print("Warning: History file could not be read.")
        return {}


def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(history, file, indent=2)


def add_statistics(videos, history):
    now = datetime.now(timezone.utc)
    timestamp = now.isoformat()

    for start in range(0, len(videos), 50):
        batch = videos[start:start + 50]
        ids = ",".join(v["video_id"] for v in batch)

        response = youtube.videos().list(
            part="snippet,statistics,liveStreamingDetails",
            id=ids
        ).execute()

        for item in response.get("items", []):
            video = next(
                v for v in batch if v["video_id"] == item["id"]
            )

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
            comments = stats.get("commentCount")
            viewers = int(live.get("concurrentViewers", 0))

            video.update({
                "views": views,
                "likes": likes,
                "comments": (
                    int(comments) if comments is not None else None
                ),
                "concurrent_viewers": viewers
            })

            # Compare with the most recent saved snapshot.
            snapshots = history.get(video["video_id"], [])
            previous = snapshots[-1] if snapshots else None

            views_per_hour = 0.0
            growth_available = False

            if previous:
                previous_time = datetime.fromisoformat(
                    previous["timestamp"]
                )
                elapsed = (
                    now - previous_time
                ).total_seconds() / 3600

                if elapsed >= 0.1:
                    gained = max(
                        0,
                        views - int(previous["views"])
                    )
                    views_per_hour = gained / elapsed
                    growth_available = True

            # Save this run's snapshot.
            snapshots.append({
                "timestamp": timestamp,
                "views": views,
                "concurrent_viewers": viewers
            })

            history[video["video_id"]] = snapshots[-MAX_SNAPSHOTS:]

            # Calculate ranking components.
            published = datetime.fromisoformat(
                video["published_at"].replace("Z", "+00:00")
            )

            age_hours = max(
                0,
                (now - published).total_seconds() / 3600
            )

            popularity = min(
                math.log10(views + 1) / 7, 1
            )

            engagement = min(
                (likes / max(views, 1)) / 0.08, 1
            )

            live_score = min(
                math.log10(viewers + 1) / 5, 1
            )

            freshness = max(
                0,
                1 - age_hours / (30 * 24)
            )

            growth_score = min(
                math.log10(views_per_hour + 1) / 3, 1
            )

            if growth_available:
                score = (
                    popularity * 0.25
                    + engagement * 0.15
                    + live_score * 0.20
                    + freshness * 0.15
                    + growth_score * 0.25
                ) * 100
            else:
                # First snapshot: rank without growth data.
                score = (
                    popularity * 0.35
                    + engagement * 0.20
                    + live_score * 0.25
                    + freshness * 0.20
                ) * 100

            video["views_per_hour"] = round(
                views_per_hour, 2
            )
            video["growth_available"] = growth_available
            video["snapshot_count"] = len(snapshots)
            video["score"] = round(score, 2)

    save_history(history)

    return [
        v for v in videos
        if v.get("relevant") is True
    ]


def main():
    print("GTA 6 GLOBAL DISCOVERY V3")
    print("=" * 40)

    history = load_history()
    videos = collect()
    videos = add_statistics(videos, history)

    videos.sort(
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_discovered": len(videos),
        "ranking_method": (
            "Popularity 25%, Engagement 15%, "
            "Live Viewers 20%, Freshness 15%, "
            "Growth 25% when historical data is available"
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
    print(f"History entries: {len(history)}")
    print(f"Report saved: {filename}")

    for video in videos[:15]:
        print(
            video["score"],
            "growth:", video["views_per_hour"],
            "views/hour",
            video["event_type"],
            video["title"],
            video["url"]
        )


if __name__ == "__main__":
    main()
