"""One run of the bot: handle Telegram taps, publish approved posts, draft new stories.

Run with:  python -m bot.main            (normal run - GitHub Actions does this every 10 min)
           python -m bot.main --dry-run  (fetch + draft, print only; nothing sent or saved)
           python -m bot.main --card "Some headline"   (render a test card to cards/test.jpg)
"""
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from . import card, config, instagram, sources, telegram, writer

HELP = (
    "👋 imjustsheff bot\n\n"
    "New stories arrive here as drafts. Tap ✅ Post, ✏️ Edit or ❌ Skip.\n\n"
    "Editing: tap ✏️ (or reply to a draft) and send the new caption. "
    "Start your message with 'headline:' to change the text on the image instead.\n\n"
    "Manual story: send a message with the headline on the first line, details below, "
    "an optional link, and optionally a last line like 'Source: South Yorkshire Police'."
)


def now():
    return datetime.now(timezone.utc)


def load_state():
    if os.path.exists(config.STATE_PATH):
        with open(config.STATE_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_state(state):
    with open(config.STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=1, ensure_ascii=False)


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
        self.rendered_this_run = set()  # these cards aren't online until the run's commit is pushed

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
            if message_id in st.get("msg_ids", []):
                return st
        return None

    def render_card(self, story):
        story["card_version"] = story.get("card_version", 0) + 1
        rel = f"cards/{story['id']}-{story['card_version']}.jpg"
        card.render(story["headline"], story["tag"], story["source_name"], story["location"],
                    os.path.join(config.ROOT, rel))
        story["card"] = rel
        self.rendered_this_run.add(story["id"])

    # --- drafts ------------------------------------------------------------
    def create_story(self, item, draft, update_of=None):
        sid = hashlib.sha1((item["uid"] + now().isoformat()).encode()).hexdigest()[:8]
        story = {
            "id": sid,
            "status": "pending",
            "created": now().isoformat(),
            "headline": draft["headline"],
            "tag": "UPDATE" if update_of else draft["tag"],
            "caption": draft["caption"],
            "location": draft["location"],
            "source_id": item["source_id"],
            "source_name": item["source_name"],
            "media": item["media"],
            "items": [item],
            "update_of": update_of,
            "msg_ids": [],
        }
        self.render_card(story)
        self.stories[sid] = story
        self.send_draft(story)
        return story

    def send_draft(self, story):
        src = sources.source_by_id(story["source_id"])
        lines = [f"{src.get('emoji', '📝')} {story['source_name']}"]
        if story["media"]:
            lines.append("📰 TIP from a news outlet - check the facts before posting")
        if story.get("update_of") and story["update_of"] in self.stories:
            old = self.stories[story["update_of"]]
            lines.append(f"🔁 UPDATE to: {old['headline']} ({old['status']})")
        others = {i["source_name"] for i in story["items"][1:]}
        if others:
            lines.append("➕ Also reported by: " + ", ".join(sorted(others)))
        if story["items"][0]["link"]:
            lines.append(story["items"][0]["link"])
        header = "\n".join(lines) + "\n\n"

        if not self.telegram_on:
            self.log(f"\n--- DRAFT {story['id']} [{story['tag']}] ---\n{header}{story['caption']}\n"
                     f"card: {story['card']}")
            return

        for mid in story.get("msg_ids", [])[:1]:
            telegram.clear_buttons(mid)
        buttons = telegram.draft_buttons(story["id"])
        path = os.path.join(config.ROOT, story["card"])
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
        updates = telegram.get_updates(self.s["tg_offset"])
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
        text = (msg.get("text") or "").strip()
        if not text:
            return
        if text.startswith("/"):
            telegram.send_text(HELP)
            return

        reply = msg.get("reply_to_message", {}).get("message_id")
        story = self.story_for_message(reply) if reply else None
        if not story and self.s["awaiting_edit"]:
            story = self.stories.get(self.s["awaiting_edit"])
        self.s["awaiting_edit"] = None

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

    def manual_story(self, text):
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
        self.create_story(item, draft)

    # --- publishing ----------------------------------------------------------
    def publish_approved(self):
        for story in self.stories.values():
            if story["status"] != "approved" or story["id"] in self.rendered_this_run:
                continue  # a card re-rendered this run gets posted on the next run
            if not (config.IG_USER_ID and config.IG_ACCESS_TOKEN and config.IMAGE_BASE_URL):
                story["status"] = "failed"
                telegram.send_text("⚠️ Instagram isn't set up yet (IG_USER_ID / IG_ACCESS_TOKEN missing).",
                                   reply_to=story["msg_ids"][0])
                continue
            image_url = f"{config.IMAGE_BASE_URL}/{story['card']}"
            try:
                link = instagram.publish(image_url, story["caption"])
                story.update(status="posted", posted=now().isoformat(), permalink=link)
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

    def process_item(self, item):
        self.log(f"  [{item['source_name']}] {item['title']}")
        draft = writer.draft_for(item, self.recent_stories(), self.log)
        match = self.stories.get(draft["duplicate_of"])

        if draft["relation"] == "same_story" and match:
            match["items"].append(item)
            self.log(f"    same story as {match['id']} ({match['status']})")
            if match["status"] == "pending" and self.telegram_on:
                telegram.send_text(f"➕ Also reported by {item['source_name']}: {item['title']}\n{item['link']}",
                                   reply_to=match["msg_ids"][0])
            return

        if not draft["newsworthy"] and not item["official"]:
            self.log("    not newsworthy - skipped")
            return

        update_of = match["id"] if draft["relation"] == "update" and match else None
        self.create_story(item, draft, update_of)

    # --- housekeeping --------------------------------------------------------
    def cleanup(self):
        card_cutoff = now() - timedelta(days=config.CARD_RETENTION_DAYS)
        for sid, story in list(self.stories.items()):
            if datetime.fromisoformat(story["created"]) < card_cutoff and story["status"] != "approved":
                del self.stories[sid]
        keep = {st["card"] for st in self.stories.values()}
        if os.path.isdir(config.CARDS_DIR):
            for name in os.listdir(config.CARDS_DIR):
                if f"cards/{name}" not in keep and name != ".gitkeep" and name != "test.jpg":
                    os.remove(os.path.join(config.CARDS_DIR, name))
        seen_cutoff = (now() - timedelta(days=config.SEEN_RETENTION_DAYS)).isoformat()
        self.s["seen"] = {k: v for k, v in self.s["seen"].items() if v >= seen_cutoff}

    def run(self):
        self.handle_updates()
        self.publish_approved()
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
    state = load_state()
    if dry_run:
        state = {"seeded": [s["id"] for s in config.SOURCES]}  # treat everything as new
    bot = Bot(state, dry_run=dry_run)
    bot.run()
    if not dry_run:
        save_state(state)


if __name__ == "__main__":
    main(sys.argv[1:])
