"""Publish image posts and Reels through the Instagram Graph API (Facebook Login flavour)."""
import os
import time

import requests

from . import config


def _url(path):
    return f"https://graph.facebook.com/{config.GRAPH_API_VERSION}/{path}"


def _check(resp):
    data = resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def publish(image_url, caption):
    """Returns the post's permalink (or media id if the permalink lookup fails)."""
    token = config.IG_ACCESS_TOKEN
    container = _check(requests.post(_url(f"{config.IG_USER_ID}/media"), timeout=60, data={
        "image_url": image_url, "caption": caption, "access_token": token,
    }))["id"]

    for _ in range(20):  # Instagram downloads and processes the image first
        status = _check(requests.get(_url(container), timeout=30, params={
            "fields": "status_code", "access_token": token,
        })).get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError("Instagram could not process the image")
        time.sleep(3)

    media_id = _check(requests.post(_url(f"{config.IG_USER_ID}/media_publish"), timeout=60, data={
        "creation_id": container, "access_token": token,
    }))["id"]
    try:
        return _check(requests.get(_url(media_id), timeout=30, params={
            "fields": "permalink", "access_token": token,
        })).get("permalink", media_id)
    except RuntimeError:
        return media_id


class StillProcessing(Exception):
    """Instagram hasn't finished processing a Reel yet - try publishing the same container later."""

    def __init__(self, container):
        super().__init__(f"Instagram is still processing the video ({container})")
        self.container = container


def _permalink(media_id, token):
    try:
        return _check(requests.get(_url(media_id), timeout=30, params={
            "fields": "permalink", "access_token": token,
        })).get("permalink", media_id)
    except RuntimeError:
        return media_id


def publish_reel(video_path, caption, container=None, wait_seconds=240):
    """Upload a video straight to Instagram (no public hosting needed) and publish it as a Reel.

    Pass container= to carry on with one that was still processing on an earlier run.
    Raises StillProcessing if Instagram needs longer than wait_seconds.
    """
    token = config.IG_ACCESS_TOKEN
    if not container:
        created = _check(requests.post(_url(f"{config.IG_USER_ID}/media"), timeout=60, data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption,
            "share_to_feed": "true", "access_token": token,
        }))
        container = created["id"]
        size = os.path.getsize(video_path)
        with open(video_path, "rb") as fh:
            upload = requests.post(
                created.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{config.GRAPH_API_VERSION}/{container}",
                headers={"Authorization": f"OAuth {token}", "offset": "0", "file_size": str(size)},
                data=fh, timeout=600)
        result = upload.json() if upload.content else {}
        if upload.status_code != 200 or not result.get("success", True) or "error" in result:
            raise RuntimeError(f"video upload to Instagram failed: {result or upload.status_code}")

    deadline = time.time() + wait_seconds
    while True:
        info = _check(requests.get(_url(container), timeout=30, params={
            "fields": "status_code,status", "access_token": token,
        }))
        if info.get("status_code") == "FINISHED":
            break
        if info.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram couldn't process the video: {info.get('status', info['status_code'])}")
        if time.time() > deadline:
            raise StillProcessing(container)
        time.sleep(10)

    media_id = _check(requests.post(_url(f"{config.IG_USER_ID}/media_publish"), timeout=60, data={
        "creation_id": container, "access_token": token,
    }))["id"]
    return _permalink(media_id, token)
