"""Publish a single image post through the Instagram Graph API (Facebook Login flavour)."""
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
