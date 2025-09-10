import time
from PyQt6.QtWidgets import QMessageBox
from youtube_api_core import get_comment_threads, service
from keywords_handler import spam_keywords


def process_comments(comment_ids, action_type, output_widget):
    if not service:
        return 0, "Please login first."

    count = 0
    for comment_id in comment_ids:
        try:
            if action_type == "delete":
                service.comments().delete(id=comment_id).execute()
                output_widget.append(f"Deleted comment (ID: {comment_id})")
            elif action_type == "ban":
                service.comments().setModerationStatus(
                    id=comment_id,
                    moderationStatus="rejected",
                    banAuthor=True
                ).execute()
                output_widget.append(f"Banned user and deleted comment (ID: {comment_id})")
            count += 1
            time.sleep(0.5)
        except Exception as e:
            output_widget.append(f"Error processing comment {comment_id}: {e}")
            return count, f"An error occurred while processing comments: {e}"
    return count, None


def delete_or_ban_comments(output_widget, video_id, channel_id, delete_only):
    output_widget.clear()
    output_widget.append(f"Using keywords: {', '.join(spam_keywords) if spam_keywords else 'None'}")
    output_widget.append("Processing auto-detected spam comments...")

    comments, error = get_comment_threads(video_id, channel_id)
    if error:
        output_widget.append(f"Error: {error}")
        return

    action_type = "delete" if delete_only else "ban"
    count = 0
    for item in comments:
        comment_snip = item["snippet"]["topLevelComment"]["snippet"]
        text = comment_snip["textDisplay"]
        comment_id = item["snippet"]["topLevelComment"]["id"]
        matched_keywords = [word for word in spam_keywords if word.lower() in text.lower()]
        if matched_keywords:
            try:
                if action_type == "delete":
                    service.comments().delete(id=comment_id).execute()
                    output_widget.append(f"Deleted comment (ID: {comment_id})")
                elif action_type == "ban":
                    service.comments().setModerationStatus(
                        id=comment_id,
                        moderationStatus="rejected",
                        banAuthor=True
                    ).execute()
                    output_widget.append(f"Banned user and deleted comment (ID: {comment_id})")
                count += 1
                time.sleep(0.5)
            except Exception as e:
                output_widget.append(f"Error processing comment {comment_id}: {e}")
    output_widget.append(f"\nDone: {count} spam comments processed ({action_type}).")