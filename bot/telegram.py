"""Minimal Telegram Bot API client (polling with getUpdates - no webhook needed)."""
import json

import requests

from . import config

API = "https://api.telegram.org/bot{token}/{method}"


def _call(method, files=None, **params):
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    for key, value in list(params.items()):
        if isinstance(value, (dict, list)):
            params[key] = json.dumps(value)
    resp = requests.post(url, data=params, files=files, timeout=60)
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data.get('description')}")
    return data["result"]


def download_photo(message, path):
    """Save the largest size of a photo message to path."""
    file_id = message["photo"][-1]["file_id"]
    file_path = _call("getFile", file_id=file_id)["file_path"]
    url = f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN}/{file_path}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(resp.content)
    return path


def get_updates(offset):
    return _call("getUpdates", offset=offset, timeout=0,
                 allowed_updates=["message", "callback_query"])


def draft_buttons(story_id, photo_options=()):
    """photo_options: [(item_index, source_name)] for items that have an article photo."""
    rows = [[
        {"text": "✅ Post", "callback_data": f"post:{story_id}"},
        {"text": "✏️ Edit", "callback_data": f"edit:{story_id}"},
        {"text": "❌ Skip", "callback_data": f"skip:{story_id}"},
    ]]
    for index, source_name in photo_options:
        rows.append([{"text": f"📷 Use {source_name} photo", "callback_data": f"photo:{story_id}:{index}"}])
    return {"inline_keyboard": rows}


def download_url(url, path):
    resp = requests.get(url, timeout=60, headers={"User-Agent": "imjustsheff-news-bot/1.0"})
    resp.raise_for_status()
    with open(path, "wb") as fh:
        fh.write(resp.content)
    return path


def send_photo(path, caption, buttons=None, reply_to=None):
    params = {"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption[:1024]}
    if buttons:
        params["reply_markup"] = buttons
    if reply_to:
        params["reply_to_message_id"] = reply_to
    with open(path, "rb") as fh:
        return _call("sendPhoto", files={"photo": fh}, **params)


def send_text(text, reply_to=None, buttons=None):
    params = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text[:4096], "disable_web_page_preview": True}
    if reply_to:
        params["reply_to_message_id"] = reply_to
    if buttons:
        params["reply_markup"] = buttons
    return _call("sendMessage", **params)


def clear_buttons(message_id):
    try:
        _call("editMessageReplyMarkup", chat_id=config.TELEGRAM_CHAT_ID, message_id=message_id,
              reply_markup={"inline_keyboard": []})
    except RuntimeError:
        pass  # message too old or already cleared


def answer_callback(callback_id, text=""):
    try:
        _call("answerCallbackQuery", callback_query_id=callback_id, text=text)
    except RuntimeError:
        pass  # callbacks expire after a while; the action still runs
