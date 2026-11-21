
import os
import re
import json
import math
from datetime import datetime, timezone, timedelta

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

API_KEY = os.environ["YOUTUBE_API_KEY"]

youtube = build("youtube", "v3", developerKey=API_KEY)

SEARCH_QUERY = '"GTA 6"|"GTA VI"|"Grand Theft Auto VI"'

GTA6_PATTERN = re.compile(
    r"\b(gta\s*6|gta\s*vi|grand theft auto\s*vi)\b",
    re.IGNORECASE
)


def is_relevant(video):
    title = video.get("snippet", {}).get("title", "")
    description = video.get("snippet", {}).get("description", "")
    tags = video.get("snippet", {}).get("tags", [])

    text = " ".join([title, description, " ".join(tags)])

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
        published_after = (
            datetime.now(timezone.utc) - timedelta(days=30)
        ).isoformat()

        params["publishedAfter"] = published_after

    response = youtube.search().list(**params).execute()

    return response.get("items", [])


def collect():
    candidates = {}

    for event_type in ["live", "completed"]:
        try:
            results = discover(event_type)

            for item in results:
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


def add_statistics(videos):
    for start in range(0, len(videos), 50):
        batch = videos[start:start + 50]
        ids = ",".join(v["video_id"] for v in batch)

        response = youtube.videos().list(
            part="snippet,statistics,liveStreamingDetails",
            id=ids
        ).execute()

        for item in response.get("items", []):
            video = next(
                v for v in batch
                if v["video_id"] == item["id"]
            )

            snippet = item.get("snippet", {})

            video["title"] = snippet.get("title", "")
            video["description"] = snippet.get("description", "")
            video["channel"] = snippet.get("channelTitle", "")
            video["channel_id"] = snippet.get("channelId", "")
            video["published_at"] = snippet.get("publishedAt", "")
            video["language"] = (
                snippet.get("defaultAudioLanguage")
                or snippet.get("defaultLanguage")
                or "unknown"
            )

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

            engagement = min(
                ((likes + comments * 2) / max(views, 1)) / 0.08,
                1
            )

            live_score = min(
                math.log10(viewers + 1) / 5,
                1
            )

            freshness = max(
                0,
                1 - age_hours / (30 * 24)
            )

            score = (
                popularity * 0.35
                + engagement * 0.20
                + live_score * 0.25
                + freshness * 0.20
            ) * 100

            video["score"] = round(score, 2)
            video["growth_tracking"] = "Pending historical snapshots"

    return [
        v for v in videos
        if v.get("relevant") is True
    ]


def main():
    print("GTA 6 GLOBAL DISCOVERY V2")
    print("=" * 40)

    videos = collect()
    videos = add_statistics(videos)

    videos.sort(
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_discovered": len(videos),
        "ranking_method": (
            "Popularity 35%, Engagement 20%, "
            "Live Viewers 25%, Freshness 20%"
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
            video["title"],
            video["url"]
        )


if __name__ == "__main__":
    main()
