"""Read news tips that followers send to the page by Instagram DM.

Uses the Graph API conversations endpoint on the linked Facebook Page. Needs the
instagram_manage_messages permission on the page token and, in the Instagram app,
"Allow access to messages" switched on.

Asking for a whole inbox with messages in one request times out on Meta's side, so this
works in two small steps: list which chats changed since the last check, then fetch
recent messages for only those chats.
"""
from datetime import datetime

import requests

from . import config

MESSAGE_FIELDS = "messages.limit(10){id,created_time,from,message,attachments{image_data,file_url,mime_type}}"


def _url(path):
    return f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{path}"


def _get(path, params, tries=2):
    params = dict(params, access_token=config.IG_ACCESS_TOKEN)
    for attempt in range(tries):
        try:
            data = requests.get(_url(path), params=params, timeout=40).json()
        except requests.RequestException as exc:
            if attempt == tries - 1:
                raise RuntimeError(str(exc))
            continue
        if "error" not in data:
            return data
        if attempt == tries - 1:
            raise RuntimeError(data["error"].get("message", str(data["error"])))


def _time(stamp):
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S%z")


def changed_conversations(since):
    """IDs of chats with activity after `since` (a datetime), newest first."""
    data = _get(f"{config.IG_PAGE_ID}/conversations",
                {"platform": "instagram", "fields": "id,updated_time", "limit": 25})
    return [c["id"] for c in data.get("data", []) if _time(c["updated_time"]) > since]


def _image_urls(message):
    urls = []
    for att in (message.get("attachments") or {}).get("data", []):
        image = att.get("image_data") or {}
        url = image.get("url") or image.get("preview_url")
        if not url and str(att.get("mime_type", "")).startswith("image/"):
            url = att.get("file_url")
        if url:
            urls.append(url)
    return urls


def new_tips(seen, since):
    """Group unseen incoming messages (newer than `since`) per sender into one tip each.

    Returns [{"msg_ids", "username", "text", "images"}].
    """
    tips = []
    for conv_id in changed_conversations(since):
        messages = (_get(conv_id, {"fields": MESSAGE_FIELDS}).get("messages") or {}).get("data", [])
        fresh = [m for m in reversed(messages)  # API gives newest first
                 if str((m.get("from") or {}).get("id")) != str(config.IG_USER_ID)
                 and _time(m["created_time"]) > since
                 and "dm:" + m["id"] not in seen]
        if not fresh:
            continue
        texts = [m["message"].strip() for m in fresh if (m.get("message") or "").strip()]
        tips.append({
            "msg_ids": [m["id"] for m in fresh],
            "username": (fresh[0].get("from") or {}).get("username") or "a follower",
            "text": "\n".join(texts),
            "images": [url for m in fresh for url in _image_urls(m)],
        })
    return tips
