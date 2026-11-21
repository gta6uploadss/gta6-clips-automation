
import os
import json
from datetime import datetime, timezone
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

API_KEY = os.environ["YOUTUBE_API_KEY"]

youtube = build(
    "youtube",
    "v3",
    developerKey=API_KEY
)

LANGUAGES = {
    "English": ("en", "GTA 6"),
    "Hindi": ("hi", "GTA 6 Hindi"),
    "Malayalam": ("ml", "GTA 6 Malayalam"),
    "Tamil": ("ta", "GTA 6 Tamil"),
    "Spanish": ("es", "GTA 6 español"),
    "Portuguese": ("pt", "GTA 6 português"),
    "Japanese": ("ja", "GTA 6"),
    "Korean": ("ko", "GTA 6"),
    "Arabic": ("ar", "GTA 6"),
    "Indonesian": ("id", "GTA 6 Indonesia")
}

def discover(language, lang_code, query, event_type):
    print(f"Searching: {language} | {event_type}")

    response = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        eventType=event_type,
        order="viewCount",
        relevanceLanguage=lang_code,
        maxResults=10
    ).execute()

    return response.get("items", [])

def collect():
    candidates = {}

    for language, (code, query) in LANGUAGES.items():
        for event in ["live", "completed"]:
            try:
                results = discover(
                    language, code, query, event
                )

                for item in results:
                    video_id = item["id"]["videoId"]

                    if video_id not in candidates:
                        candidates[video_id] = {
                            "video_id": video_id,
                            "title": item["snippet"]["title"],
                            "channel": item["snippet"]["channelTitle"],
                            "channel_id": item["snippet"]["channelId"],
                            "published_at": item["snippet"]["publishedAt"],
                            "language_search": language,
                            "event_type": event,
                            "url": (
                                "https://www.youtube.com/watch?v="
                                + video_id
                            )
                        }

            except HttpError as error:
                print(f"API error: {error}")

    return list(candidates.values())

def add_statistics(videos):
    for start in range(0, len(videos), 50):
        batch = videos[start:start + 50]
        ids = ",".join(v["video_id"] for v in batch)

        response = youtube.videos().list(
            part="statistics,liveStreamingDetails,snippet",
            id=ids
        ).execute()

        for item in response.get("items", []):
            video = next(
                v for v in batch
                if v["video_id"] == item["id"]
            )

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

            # Popularity, engagement and live audience proxy.
            engagement = (
                (likes + comments * 2) / max(views, 1)
            )

            import math

            popularity = math.log10(views + 1) / 10
            engagement_score = min(engagement * 100, 1)
            live_score = min(
                math.log10(viewers + 1) / 5, 1
            )

            video["score"] = round(
                (
                    popularity * 0.35
                    + engagement_score * 0.20
                    + live_score * 0.15
                    + 0.30 * 0.5
                ) * 100,
                2
            )

            video["growth_tracking"] = "Not yet measured"

    return videos

def main():
    print("GTA 6 GLOBAL DISCOVERY ENGINE")
    print("=" * 40)

    videos = collect()
    videos = add_statistics(videos)

    videos.sort(
        key=lambda x: x.get("score", 0),
        reverse=True
    )

    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_discovered": len(videos),
        "ranking_method": "Initial popularity and engagement proxy",
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

    print(f"Discovered: {len(videos)} videos")
    print(f"Report saved: {filename}")

    for video in videos[:10]:
        print(
            video["score"],
            video["title"],
            video["url"]
        )

if __name__ == "__main__":
    main()
