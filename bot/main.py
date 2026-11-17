"""One run of the bot: handle Telegram taps, publish approved posts, draft new stories.

Run with:  python -m bot.main            (normal run - GitHub Actions does this every 10 min)
           python -m bot.main --dry-run  (fetch + draft, print only; nothing sent or saved)
           python -m bot.main --card "Some headline"   (render a test card to cards/test.jpg)
"""
import hashlib
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

from . import card, config, instagram, instagram_dms, sources, telegram, vault, writer

HELP = (
    "👋 imjustsheff bot\n\n"
    "New stories arrive here as drafts. Tap ✅ Post, ✏️ Edit or ❌ Skip.\n\n"
    "Editing: tap ✏️ (or reply to a draft) and send the new caption. "
    "Start your message with 'headline:' to change the text on the image instead.\n\n"
    "Photos: reply to a draft with a photo (e.g. a police appeal or CCTV image) and the card is rebuilt "
    "around it. Add a caption to set the image credit. Drafts use the article's own photo automatically (credited on the card). Reply 'no photo' for a text-only card.\n\n"
    "Sensitive stories (deaths, sexual offences, children) get a muted card without pink. Reply "
    "'sensitive' or 'not sensitive' to a draft to switch it.\n\n"
    "Manual story: send a message (or a photo with a caption) with the headline on the first line, "
    "details below, an optional link, and optionally a last line like 'Source: South Yorkshire Police'."
)


PHOTO_TRIES = 12  # one try per run - a few hours of retries


def _short_error(exc):
    """'403 Client Error: Forbidden for url: ...' -> 'site said 403 Forbidden'."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        return f"site said {resp.status_code} {resp.reason}"
    return type(exc).__name__


def now():
    return datetime.now(timezone.utc)


def work_path(name):
    os.makedirs(config.WORK_DIR, exist_ok=True)
    return os.path.join(config.WORK_DIR, name)


def make_public(path):
    """Commit and push one card image so Instagram can download it from the public repo."""
    if not os.environ.get("GITHUB_ACTIONS"):
        return
    rel = os.path.relpath(path, config.ROOT).replace(os.sep, "/")
    subprocess.run(["git", "add", rel], cwd=config.ROOT, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"bot: card {os.path.basename(rel)}"], cwd=config.ROOT, check=True)
    # GitHub refuses the push if the repo changed since this run started (e.g. you pushed an
    # update mid-run). Catch up with the latest version and try again.
    for attempt in range(3):
        if subprocess.run(["git", "push", "-q"], cwd=config.ROOT).returncode == 0:
            return
        subprocess.run(["git", "pull", "-q", "--rebase", "--autostash"], cwd=config.ROOT)
    raise RuntimeError("couldn't upload the card image to GitHub - tap Try again in a few minutes")


def wait_until_online(url, seconds=90):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if requests.head(url, timeout=10).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(5)
    raise RuntimeError("card image didn't come online in time")


class Bot:
    def __init__(self, state, dry_run=False):
        self.dry_run = dry_run
        self.s = state
        state.setdefault("tg_offset", 0)
        state.setdefault("awaiting_edit", None)
        state.setdefault("seeded", [])
        state.setdefault("seen", {})
        state.setdefault("stories", {})
        self.telegram_on = bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID) and not dry_run

    # --- helpers -----------------------------------------------------------
    def log(self, msg):
        print(msg, flush=True)

    @property
    def stories(self):
        return self.s["stories"]

    def recent_stories(self):
        cutoff = now() - timedelta(hours=config.DEDUPE_WINDOW_HOURS)
        recent = [st for st in self.stories.values() if datetime.fromisoformat(st["created"]) >= cutoff]
        return sorted(recent, key=lambda st: st["created"])

    def story_for_message(self, message_id):
        for st in self.stories.values():
            if message_id in st.get("msg_ids", []) or message_id in st.get("extra_ids", []):
                return st
        return None

    def render_card(self, story, out_path=None):
        """Draft previews go to the private work folder; only approved posts get a public card."""
        story["card_version"] = story.get("card_version", 0) + 1
        out_path = out_path or work_path(f"{story['id']}-{story['card_version']}.jpg")
        # A photo you sent for this story wins; otherwise one of your own area photos.
        photo, credit = None, None
        if story.get("photo"):
            photo, credit = vault.open_photo(story["photo"]), story.get("photo_credit")
        elif story.get("use_area_photo", True):
            photo = card.find_location_photo(story["location"], story["headline"])
        card.render(story["headline"], story["tag"], story["source_name"], story["location"],
                    out_path, photo, credit, highlight=story.get("highlight"),
                    sensitive=story.get("sensitive", False))
        story["card"] = out_path
        return out_path

    def store_photo(self, story, download, credit, photo_from=None):
        """download(path) saves the photo; it is then kept encrypted, never in the clear."""
        plain = work_path(f"{story['id']}-download.jpg")
        download(plain)
        story.update(photo=vault.store_photo(plain, story["id"]), photo_credit=credit, photo_from=photo_from)

    # --- drafts ------------------------------------------------------------
    def create_story(self, item, draft, update_of=None, photo_msg=None, photo_url=None):
        sid = hashlib.sha1((item["uid"] + now().isoformat()).encode()).hexdigest()[:8]
        story = {
            "id": sid,
            "status": "pending",
            "created": now().isoformat(),
            "headline": draft["headline"],
            "tag": "UPDATE" if update_of else draft["tag"],
            "caption": draft["caption"],
            "location": draft["location"],
            "highlight": draft.get("highlight", ""),
            "sensitive": draft.get("sensitive", False),
            "source_id": item["source_id"],
            "source_name": item["source_name"],
            "media": item["media"],
            "items": [item],
            "update_of": update_of,
            "msg_ids": [],
        }
        if photo_msg:
            self.attach_photo(story, photo_msg, credit=item["source_name"])  # also renders the card
        elif photo_url:
            try:
                credit = "Reader photo" if item.get("reader") else item["source_name"]
                self.store_photo(story, lambda p: telegram.download_url(photo_url, p), credit, photo_from=0)
            except Exception as exc:
                self.log(f"    photo download failed: {exc}")
                story["photo_failed"] = _short_error(exc)
                story["photo_tries"] = 1
            self.render_card(story)
        else:
            self.render_card(story)
        self.stories[sid] = story
        self.send_draft(story)
        return story

    def send_draft(self, story):
        src = sources.source_by_id(story["source_id"])
        lines = [f"{src.get('emoji', '📝')} {story['source_name']}"]
        if story.get("sensitive"):
            lines.append("🕊️ Sensitive style (no pink) - reply 'not sensitive' to switch")
        if story["media"]:
            lines.append("📰 TIP from a news outlet - check the facts before posting")
        first = story["items"][0]
        if first.get("reader"):
            lines.append(f"💬 DM from @{first['sender']} - UNVERIFIED, check before posting")
            if first["summary"]:
                lines.append(f"Their message: {first['summary'][:300]}")
            if first.get("extra_images"):
                lines.append(f"(+{first['extra_images']} more photo(s) in the DM)")
        if story.get("update_of") and story["update_of"] in self.stories:
            old = self.stories[story["update_of"]]
            lines.append(f"🔁 UPDATE to: {old['headline']} ({old['status']})")
        others = {i["source_name"] for i in story["items"][1:]}
        if others:
            lines.append("➕ Also reported by: " + ", ".join(sorted(others)))
        if story.get("photo_failed") and not story.get("photo"):
            tries = story.get("photo_tries", 1)
            retry = " - I'll keep trying for a few hours" if tries < PHOTO_TRIES else ""
            lines.append(f"📷 Couldn't get the article photo yet ({story['photo_failed']}){retry}. "
                         "Or reply to this draft with one.")
        if story["items"][0]["link"]:
            lines.append(story["items"][0]["link"])
        header = "\n".join(lines) + "\n\n"

        if not story.get("card") or not os.path.exists(story["card"]):
            self.render_card(story)  # the work folder is wiped between runs
        if not self.telegram_on:
            self.log(f"\n--- DRAFT {story['id']} [{story['tag']}] ---\n{header}{story['caption']}\n"
                     f"card: {story['card']}")
            return

        for mid in story.get("msg_ids", [])[:1]:
            telegram.clear_buttons(mid)
        photo_options = [(i, it["source_name"]) for i, it in enumerate(story["items"])
                         if it.get("image") and story.get("photo_from") != i]
        buttons = telegram.draft_buttons(story["id"], photo_options)
        path = story["card"]
        full = header + story["caption"]
        if len(full) <= 1024:
            msg = telegram.send_photo(path, full, buttons)
            story["msg_ids"] = [msg["message_id"]]
        else:
            msg = telegram.send_photo(path, header.strip(), buttons)
            text = telegram.send_text(story["caption"], reply_to=msg["message_id"])
            story["msg_ids"] = [msg["message_id"], text["message_id"]]

    # --- telegram ----------------------------------------------------------
    def handle_updates(self):
        if not self.telegram_on:
            return
        try:
            updates = telegram.get_updates(self.s["tg_offset"])
        except Exception as exc:
            # Keep checking feeds/DMs even if Telegram is misconfigured; drafts just won't send.
            self.log(f"TELEGRAM ERROR: {exc} - check the TELEGRAM_BOT_TOKEN secret")
            self.telegram_on = False
            return
        for upd in updates:
            self.s["tg_offset"] = upd["update_id"] + 1
            try:
                if "callback_query" in upd:
                    self.on_callback(upd["callback_query"])
                elif "message" in upd:
                    self.on_message(upd["message"])
            except Exception as exc:
                self.log(f"Update {upd['update_id']} failed: {exc}")

    def from_owner(self, chat):
        return str(chat.get("id")) == str(config.TELEGRAM_CHAT_ID)

    def on_callback(self, cq):
        if not self.from_owner(cq.get("message", {}).get("chat", {})):
            return
        action, _, sid = cq.get("data", "").partition(":")
        sid, _, extra = sid.partition(":")
        story = self.stories.get(sid)
        if not story:
            telegram.answer_callback(cq["id"], "That draft has expired.")
            return
        if action == "post" and story["status"] in ("pending", "failed"):
            story["status"] = "approved"
            telegram.answer_callback(cq["id"], "Posting…")
        elif action == "skip" and story["status"] in ("pending", "failed"):
            story["status"] = "skipped"
            telegram.answer_callback(cq["id"], "Skipped")
            telegram.clear_buttons(cq["message"]["message_id"])
        elif action == "photo" and story["status"] in ("pending", "failed"):
            telegram.answer_callback(cq["id"], "Adding photo…")
            item = story["items"][int(extra)]
            try:
                self.store_photo(story, lambda p: telegram.download_url(item["image"], p),
                                 item["source_name"], photo_from=int(extra))
            except Exception as exc:
                note = telegram.send_text("⚠️ That site blocked its photo. Save it from the article and "
                                          "reply to this message (or the draft) with it.",
                                          reply_to=story["msg_ids"][0])
                story.setdefault("extra_ids", []).append(note["message_id"])
                return
            story["status"] = "pending"
            self.render_card(story)
            self.send_draft(story)
        elif action == "edit" and story["status"] in ("pending", "failed"):
            self.s["awaiting_edit"] = sid
            telegram.answer_callback(cq["id"])
            telegram.send_text("✏️ Send the new caption now.\nStart with 'headline:' to change the image text instead.",
                               reply_to=story["msg_ids"][0])
        else:
            telegram.answer_callback(cq["id"], f"Already {story['status']}")

    def on_message(self, msg):
        if not self.from_owner(msg.get("chat", {})):
            return
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if text.startswith("/"):
            telegram.send_text(HELP)
            return

        reply = msg.get("reply_to_message", {}).get("message_id")
        story = self.story_for_message(reply) if reply else None
        if not story and self.s["awaiting_edit"] and not msg.get("photo"):
            story = self.stories.get(self.s["awaiting_edit"])
        self.s["awaiting_edit"] = None

        if msg.get("photo"):
            if story and story["status"] in ("pending", "failed"):
                self.attach_photo(story, msg, credit=text or story["source_name"])
                story.pop("photo_failed", None)
                story["status"] = "pending"
                self.send_draft(story)
            elif reply:
                telegram.send_text("⚠️ I couldn't match that photo to a draft (it may have been posted, "
                                   "skipped or expired). Reply to the draft's card image with it.")
            elif text:
                self.manual_story(text, photo_msg=msg)
            else:
                telegram.send_text("To add a photo, reply to a draft with it. To start a new story, "
                                   "send the photo with the headline as its caption.")
            return

        if not text:
            return
        if text.lower() in ("no photo", "nophoto", "remove photo") and story:
            story.pop("photo", None)
            story["use_area_photo"] = False
            self.render_card(story)
            self.send_draft(story)
            return
        if text.lower() in ("sensitive", "not sensitive") and story:
            story["sensitive"] = text.lower() == "sensitive"
            self.render_card(story)
            self.send_draft(story)
            return

        if story and story["status"] in ("pending", "failed"):
            if text.lower().startswith("headline:"):
                story["headline"] = text.split(":", 1)[1].strip()
                self.render_card(story)
            else:
                story["caption"] = text
            story["status"] = "pending"
            self.send_draft(story)
            return

        self.manual_story(text)

    def attach_photo(self, story, msg, credit):
        self.store_photo(story, lambda p: telegram.download_photo(msg, p), credit)
        self.render_card(story)

    def manual_story(self, text, photo_msg=None):
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        source_name = "imjustsheff"
        if len(lines) > 1 and lines[-1].lower().startswith("source:"):
            source_name = lines.pop().split(":", 1)[1].strip() or source_name
        link_match = re.search(r"https?://\S+", text)
        link = link_match.group(0) if link_match else ""
        body = [l for l in lines if l != link]
        item = {
            "uid": "manual:" + hashlib.sha1(text.encode()).hexdigest()[:16],
            "source_id": "manual", "source_name": source_name,
            "title": body[0] if body else link, "summary": " ".join(body[1:]),
            "link": link, "published": None, "official": True, "media": False,
        }
        draft = writer.draft_for(item, self.recent_stories(), self.log)
        self.create_story(item, draft, photo_msg=photo_msg)

    # --- publishing ----------------------------------------------------------
    def publish_approved(self):
        posted = 0
        for story in self.stories.values():
            if story["status"] != "approved":
                continue
            if posted >= config.MAX_POSTS_PER_RUN:
                break  # keeps each run well inside GitHub's time limit; the rest go next run
            if not (config.IG_USER_ID and config.IG_ACCESS_TOKEN and config.IMAGE_BASE_URL):
                story["status"] = "failed"
                telegram.send_text("⚠️ Instagram isn't set up yet (IG_USER_ID / IG_ACCESS_TOKEN missing).",
                                   reply_to=story["msg_ids"][0])
                continue
            try:
                # Only now does the card go online - Instagram downloads it from the public repo.
                public = self.render_card(story, os.path.join(config.CARDS_DIR, f"{story['id']}.jpg"))
                make_public(public)
                image_url = f"{config.IMAGE_BASE_URL}/cards/{story['id']}.jpg"
                wait_until_online(image_url)
                link = instagram.publish(image_url, story["caption"])
                story.update(status="posted", posted=now().isoformat(), permalink=link)
                posted += 1
                # Remember it straight away, so a run cut short can never post this one twice.
                if not self.dry_run:
                    vault.save_state(self.s)
                telegram.clear_buttons(story["msg_ids"][0])
                telegram.send_text(f"✅ Posted: {link}", reply_to=story["msg_ids"][0])
                self.log(f"Posted {story['id']}: {link}")
            except Exception as exc:
                story.update(status="failed", error=str(exc))
                telegram.send_text(f"⚠️ Posting failed: {exc}", reply_to=story["msg_ids"][0],
                                   buttons={"inline_keyboard": [[
                                       {"text": "🔁 Try again", "callback_data": f"post:{story['id']}"},
                                       {"text": "❌ Skip", "callback_data": f"skip:{story['id']}"}]]})
                self.log(f"Post {story['id']} failed: {exc}")

    # --- feeds ---------------------------------------------------------------
    def check_sources(self):
        self.log("Checking sources:")
        results = sources.fetch_all(self.log)
        new_items = []
        for source_id, items in results.items():
            if source_id not in self.s["seeded"]:
                # First time we see this source: remember what's there, don't flood Telegram.
                for item in items:
                    self.s["seen"][item["uid"]] = now().isoformat()
                self.s["seeded"].append(source_id)
                self.log(f"  {source_id}: first run - {len(items)} existing items marked as seen")
                continue
            new_items += [i for i in reversed(items) if i["uid"] not in self.s["seen"]]

        # Official sources first so outlet reports attach to the official story.
        new_items.sort(key=lambda i: not i["official"])
        self.log(f"{len(new_items)} new items")
        for item in new_items[: config.MAX_NEW_ITEMS_PER_RUN]:
            self.s["seen"][item["uid"]] = now().isoformat()
            try:
                self.process_item(item)
            except Exception as exc:
                self.log(f"  Failed on '{item['title']}': {exc}")

    def check_dms(self):
        if not (config.IG_PAGE_ID and config.IG_ACCESS_TOKEN):
            return
        started = now()
        if not self.s.get("dm_since"):
            # First run: only messages that arrive from now on count as tips.
            self.s["dm_since"] = started.isoformat()
            self.log("Instagram DMs: first run - only new messages from now on will become drafts")
            return
        try:
            tips = instagram_dms.new_tips(self.s["seen"], datetime.fromisoformat(self.s["dm_since"]))
        except Exception as exc:
            self.log(f"Instagram DMs: FAILED ({exc})")
            return
        self.s["dm_since"] = started.isoformat()
        self.log(f"Instagram DMs: {len(tips)} new tip(s)")
        for tip in tips:
            for mid in tip["msg_ids"]:
                self.s["seen"]["dm:" + mid] = now().isoformat()
            text = tip["text"]
            first_line = text.splitlines()[0] if text else "Photo sent in by a follower"
            item = {
                "uid": "dm:" + tip["msg_ids"][0], "source_id": "ig_dms", "source_name": "Reader tip",
                "title": first_line[:150], "summary": text[:1500], "link": "", "published": None,
                "official": False, "media": False, "reader": True, "sender": tip["username"],
                "image": tip["images"][0] if tip["images"] else "",
                "extra_images": max(0, len(tip["images"]) - 1),
            }
            try:
                draft = writer.draft_for(item, self.recent_stories(), self.log)
                self.create_story(item, draft, photo_url=tip["images"][0] if tip["images"] else None)
            except Exception as exc:
                self.log(f"  Failed on DM tip: {exc}")

    def process_item(self, item):
        self.log(f"  [{item['source_name']}] {item['title']}")
        draft = writer.draft_for(item, self.recent_stories(), self.log)
        match = self.stories.get(draft["duplicate_of"])

        if draft["relation"] == "same_story" and match:
            match["items"].append(item)
            self.log(f"    same story as {match['id']} ({match['status']})")
            # A police/council draft with no photo borrows the first outlet photo that turns up.
            if (match["status"] == "pending" and not match.get("photo") and item.get("image")
                    and match.get("use_area_photo", True)):  # not after you said "no photo"
                try:
                    self.store_photo(match, lambda p: telegram.download_url(item["image"], p),
                                     item["source_name"], photo_from=len(match["items"]) - 1)
                    match.pop("photo_failed", None)
                    self.render_card(match)
                    self.log(f"    added {item['source_name']} photo to {match['id']}")
                    if self.telegram_on:
                        self.send_draft(match)
                        telegram.send_text(f"📷 Added a photo from {item['source_name']} (also reporting this). "
                                           "Reply 'no photo' to remove it.", reply_to=match["msg_ids"][0])
                    return
                except Exception as exc:
                    self.log(f"    outlet photo failed: {exc}")
            if match["status"] == "pending" and self.telegram_on:
                buttons = None
                if item.get("image"):
                    index = len(match["items"]) - 1
                    buttons = {"inline_keyboard": [[{"text": f"📷 Use {item['source_name']} photo",
                                                     "callback_data": f"photo:{match['id']}:{index}"}]]}
                note = telegram.send_text(f"➕ Also reported by {item['source_name']}: {item['title']}\n{item['link']}",
                                          reply_to=match["msg_ids"][0], buttons=buttons)
                match.setdefault("extra_ids", []).append(note["message_id"])
            return

        if not draft["newsworthy"] and not item["official"]:
            self.log("    not newsworthy - skipped")
            return

        update_of = match["id"] if draft["relation"] == "update" and match else None
        # Every draft uses its own article's photo (credited on the card) when the feed has one.
        self.create_story(item, draft, update_of, photo_url=item.get("image"))

    # --- housekeeping --------------------------------------------------------
    def cleanup(self):
        card_cutoff = now() - timedelta(days=config.CARD_RETENTION_DAYS)
        for sid, story in list(self.stories.items()):
            if datetime.fromisoformat(story["created"]) < card_cutoff and story["status"] != "approved":
                del self.stories[sid]
        keep_photos = {os.path.basename(st["photo"]) for st in self.stories.values() if st.get("photo")}
        if os.path.isdir(config.PRIVATE_DIR):
            for name in os.listdir(config.PRIVATE_DIR):
                if name.endswith(".enc") and name not in keep_photos:
                    os.remove(os.path.join(config.PRIVATE_DIR, name))
        # Instagram keeps its own copy once posted, so public cards only need to live briefly.
        public_cutoff = (now() - timedelta(days=config.PUBLIC_CARD_DAYS)).isoformat()
        keep_cards = {f"{st['id']}.jpg" for st in self.stories.values()
                      if st["status"] in ("approved", "failed") or st.get("posted", "") >= public_cutoff}
        if os.path.isdir(config.CARDS_DIR):
            for name in os.listdir(config.CARDS_DIR):
                if name.endswith(".jpg") and name not in keep_cards and not name.startswith("test"):
                    os.remove(os.path.join(config.CARDS_DIR, name))
        seen_cutoff = (now() - timedelta(days=config.SEEN_RETENTION_DAYS)).isoformat()
        self.s["seen"] = {k: v for k, v in self.s["seen"].items() if v >= seen_cutoff}

    def retry_photos(self):
        """News sites sometimes refuse GitHub's servers for a while - try waiting drafts again."""
        for story in list(self.stories.values()):
            if (story["status"] != "pending" or story.get("photo")
                    or not story.get("use_area_photo", True) or story.get("photo_tries", 0) >= PHOTO_TRIES):
                continue
            index, item = next(((i, it) for i, it in enumerate(story["items"]) if it.get("image")), (None, None))
            if item is None:
                continue
            story["photo_tries"] = story.get("photo_tries", 0) + 1
            try:
                self.store_photo(story, lambda p: telegram.download_url(item["image"], p),
                                 item["source_name"], photo_from=index)
            except Exception as exc:
                story["photo_failed"] = _short_error(exc)
                self.log(f"  photo retry {story['photo_tries']} for {story['id']} failed: {exc}")
                continue
            story.pop("photo_failed", None)
            self.log(f"  photo retry worked for {story['id']}")
            self.render_card(story)
            if self.telegram_on:
                self.send_draft(story)
                telegram.send_text(f"📷 Got the photo from {item['source_name']} on a retry - updated card above.",
                                   reply_to=story["msg_ids"][0])

    def run(self):
        self.handle_updates()
        self.publish_approved()
        self.check_dms()
        self.retry_photos()
        self.check_sources()
        self.cleanup()


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")  # emoji in logs on Windows consoles
    if "--card" in argv:
        headline = argv[argv.index("--card") + 1]
        path = card.render(headline, "APPEAL", "South Yorkshire Police", "Sheffield",
                           os.path.join(config.CARDS_DIR, "test.jpg"))
        print("Saved", path)
        return

    dry_run = "--dry-run" in argv
    if dry_run:
        from cryptography.fernet import Fernet
        config.STATE_KEY = config.STATE_KEY or Fernet.generate_key().decode()  # throwaway; nothing is saved
        state = {"seeded": [s["id"] for s in config.SOURCES]}  # treat everything as new
    else:
        state = vault.load_state()
    bot = Bot(state, dry_run=dry_run)
    bot.run()
    if not dry_run:
        vault.save_state(state)


if __name__ == "__main__":
    main(sys.argv[1:])
