import time
from googleapiclient.discovery import build
from login_handler import service

# YouTube API scopes
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

def get_comment_threads(video_id=None, channel_id=None):
    if video_id and channel_id:
        return None, "Please enter only one of Video ID or Channel ID."
    if not video_id and not channel_id:
        return None, "Please enter a Video ID or Channel ID."
    global service
    if not service:
        return None, "Please login first."

    comments = []
    page_token = None
    max_pages = 2
    page_count = 0

    while True:
        try:
            request = service.commentThreads().list(
                part="snippet",
                videoId=video_id if video_id else None,
                allThreadsRelatedToChannelId=channel_id if channel_id else None,
                maxResults=20,
                order="time",
                pageToken=page_token
            )
            response = request.execute()
            comments.extend(response.get("items", []))
            page_token = response.get("nextPageToken")
            page_count += 1
            if not page_token or page_count >= max_pages:
                break
            time.sleep(0.5)
        except Exception as e:
            return None, f"Failed to fetch comments: {e}"
    return comments, None