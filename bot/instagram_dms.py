"""Read news tips that followers send to the page by Instagram DM.

Uses the Graph API conversations endpoint on the linked Facebook Page. Needs the
instagram_manage_messages permission on the page token and, in the Instagram app,
Settings > Messages > Connected tools > "Allow access to messages" switched on.
"""
import requests

from . import config

FIELDS = ("participants,messages.limit(15){id,created_time,from,message,"
          "attachments{image_data,file_url,mime_type}}")


def _url(path):
    return f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{path}"


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


def fetch_conversations():
    resp = requests.get(_url(f"{config.IG_PAGE_ID}/conversations"), timeout=30, params={
        "platform": "instagram", "fields": FIELDS, "limit": 20, "access_token": config.IG_ACCESS_TOKEN,
    })
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data.get("data", [])


def new_tips(seen):
    """Group unseen incoming messages per sender into one tip each.

    Returns [{"msg_ids", "username", "text", "images"}], oldest messages first.
    """
    tips = []
    for conv in fetch_conversations():
        messages = (conv.get("messages") or {}).get("data", [])
        incoming = [m for m in reversed(messages)  # API gives newest first
                    if str((m.get("from") or {}).get("id")) != str(config.IG_USER_ID)]
        fresh = [m for m in incoming if "dm:" + m["id"] not in seen]
        if not fresh:
            continue
        texts = [m["message"].strip() for m in fresh if (m.get("message") or "").strip()]
        images = [url for m in fresh for url in _image_urls(m)]
        tips.append({
            "msg_ids": [m["id"] for m in fresh],
            "username": (fresh[0].get("from") or {}).get("username") or "a follower",
            "text": "\n".join(texts),
            "images": images,
        })
    return tips


def all_message_ids():
    return ["dm:" + m["id"] for conv in fetch_conversations()
            for m in (conv.get("messages") or {}).get("data", [])]
