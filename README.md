# imjustsheff news bot

Every 10 minutes, GitHub runs this bot for free. It:

1. checks the police feed (through Inoreader) plus BBC, Met Office, Environment Agency, Rotherham Council and the local papers
2. merges the same story from different sources into one draft and spots updates to stories you've already posted
3. writes a caption with Claude AI and makes a branded headline card
4. sends you the draft on **Telegram**: **✅ Post / ✏️ Edit / ❌ Skip**
5. publishes to Instagram when you tap ✅

Nothing goes on Instagram until you approve it.

---

## Setup (about 45 minutes, one time only)

You'll collect 7 secrets. Keep them in a private note as you go and **never share them with anyone, including in chat.**

| Secret | Where it comes from |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Step 1 |
| `TELEGRAM_CHAT_ID` | Step 1 |
| `IG_USER_ID` | Step 2 |
| `IG_ACCESS_TOKEN` | Step 2 |
| `ANTHROPIC_API_KEY` | Step 3 |
| `IG_PAGE_ID` | Step 2 (only needed for DM tips) |
| `STATE_KEY` | Step 4 |

### Step 1 – Telegram bot
1. In Telegram, open **@BotFather** → send `/newbot` → pick a name (e.g. *imjustsheff drafts*) and a username ending in `bot`.
2. BotFather replies with a **token**. That's `TELEGRAM_BOT_TOKEN`.
3. Open your new bot and send it any message (e.g. `hi`).
4. In a browser, go to `https://api.telegram.org/bot<TOKEN>/getUpdates` (put your token in place of `<TOKEN>`).
   Find `"chat":{"id":123456789` in the text. That number is `TELEGRAM_CHAT_ID`.

### Step 2 – Instagram (via Meta)
Your Instagram account must be a **Business or Creator** account **linked to a Facebook Page**
(Instagram app → Settings → Account type and tools; then link a Page in the Professional dashboard).

1. Go to **developers.facebook.com** → My Apps → **Create app** → use case *Other* → type **Business**.
2. In the app, add the **Instagram** product and choose **API setup with Facebook login**.
3. Open **Tools → Graph API Explorer**:
   - Select your app. Under *User or Page*, choose **Get User Access Token**.
   - Tick these permissions: `instagram_basic`, `instagram_content_publish`, `pages_show_list`,
     `pages_read_engagement`, `business_management`, plus `instagram_manage_messages` and
     `pages_manage_metadata` for DM tips. Then click **Generate Access Token** and allow access.
4. Make that token long-lived: go to **Tools → Access Token Debugger**, paste the token, and click **Extend Access Token**.
   Copy the new token.
5. Back in Graph API Explorer, paste the long-lived token into the token box. Then run:
   - `me/accounts`: find your Page and copy its `access_token`. **That Page token is `IG_ACCESS_TOKEN`.**
     A Page token made from a long-lived user token doesn't expire.
   - `<your-page-id>?fields=instagram_business_account`: the `id` inside is **`IG_USER_ID`**.
     The page id you used here is **`IG_PAGE_ID`**.
6. For DM tips: in the Instagram app go to **Settings → Messages and story replies → Message controls →
   Connected tools → Allow access to messages** and turn it on.

You don't need App Review. In development mode the app can post to accounts you manage.

### Step 3 – Claude AI key
1. Go to **console.anthropic.com** → sign up → **Billing**: add a card and a small amount of credit (e.g. £5).
   Set a **monthly spend limit** too.
2. **API Keys** → Create key. That's `ANTHROPIC_API_KEY`.

**Cost:** the bot uses `claude-haiku-5-5`. At around 30–60 new stories a day, that's **under £1 a month**.
The monthly spend limit in the Anthropic console is a hard cap, so £5 of credit lasts months.
If you ever want richer captions, set the variable `CLAUDE_MODEL` to `claude-opus-5-5` in Step 4
(about £10–30 a month). If you leave the key out entirely, the bot still works with free template captions.

### Step 4 – GitHub (runs the bot for free)
1. Create a free account at **github.com**.
2. Click **New repository**. Name it `imjustsheff-bot` and set it to **Public**.
   It must be public: the free unlimited running time and the card image links Instagram needs both depend on it.
   Your secrets stay private either way.
3. Upload this folder. Easiest: install **GitHub Desktop** → *File → Add local repository* → choose this folder → **Publish**.
   (Or click **uploading an existing file** on the repo page and drag in everything except `.venv`.)
4. In the repo: **Settings → Secrets and variables → Actions**:
   - Make your `STATE_KEY`: in this folder run `.venv\Scripts\python -m bot.vault --new-key`
     (or ask a friend with Python). It encrypts the bot's memory, so followers' DMs are never readable in the
     public repo. **If you lose it, the bot just starts fresh. Never post it anywhere.**
   - **Secrets** tab → *New repository secret*, once for each of the 7 secrets above.
   - **Variables** tab (optional): `CLAUDE_MODEL` only if you want a different AI model. `GRAPH_API_VERSION` is only needed
     if Meta deprecates the default (`v23.0`); use the newest version shown in Graph API Explorer.
5. **Actions** tab → enable workflows → **imjustsheff bot** → **Run workflow**.

The **first run** just records what's already in every feed, so you don't get 200 old drafts.
From the next run on (within 10 minutes), new stories arrive in Telegram.

---

## Using it

- **✅ Post:** it goes live on the next check (within about 10 minutes) and you get the Instagram link.
- **✏️ Edit:** send the new caption. Start your message with `headline:` to change the text on the image instead.
  You can also just **reply** to any draft with new text.
- **❌ Skip:** the draft is dropped.
- **📷 Use … photo:** shown when a news outlet's article has a photo. It puts that photo on the card with
  "Image: <outlet>" printed on it. Credit is good practice but **not permission**. UK fair dealing for news doesn't
  cover photographs, and agency photos (PA, Getty) are actively enforced, so it's your call each time.
- **Your own photo:** reply to a draft with a photo, e.g. a police appeal or CCTV image (released for sharing).
  Add a caption to set the credit (default: the story's source). Reply `no photo` for a text-only card.
- **Area photos:** put your own photos in `photos/` named after places (`sheffield.jpg`, `page-hall.jpg`,
  `south-yorkshire.jpg` as the default). They're used automatically when a story has no other photo.
- **💬 DM tips:** when a follower DMs the page (text, photos or both), the bot turns it into a draft. It's labelled
  **UNVERIFIED** and shows their @username and message to you only. The caption is written as "reports of…",
  never names the sender, and credits "Sent in by a follower". Their photo goes on the card as "Image: Reader photo".
  Several messages from the same person since the last check are combined into one draft.
  Check tips before posting. If you can, confirm with the police, council or a second source.
- **Manual post:** send the bot a message (or a photo with the story as its caption). Put the headline on the first line and the details underneath. You can add a link
  and a last line like `Source: South Yorkshire Police`. Use this for stories you see on Facebook.
- **📰 TIP** drafts come from newspapers. The caption is rewritten in your own words and credited, but check the facts.
- **🔁 UPDATE** drafts are new developments on a story you've already covered.
- **➕ Also reported by** messages mean another outlet covered a story you already have a draft for. No new draft is made.

## Changing things

Everything is in `bot/config.py`: sources, colours, local place names, words that get a story skipped.
To use your own font, put `bold.ttf` and `regular.ttf` in `fonts/`.

Test locally:
```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m bot.main --card "Test headline"   # makes cards/test.jpg
.venv\Scripts\python -m bot.main --dry-run                # prints drafts, sends nothing
```

## Good to know
- GitHub's 10-minute schedule can run a few minutes late at busy times.
- Instagram's API allows up to about 50 posts a day per account.
- If posting fails (e.g. an expired token), you get a ⚠️ message with a **Try again** button.
- Legal: the AI is told never to imply guilt for people who are only arrested or charged. You're still the editor,
  so read each draft before you tap ✅, especially court and crime stories. Turn comments off on posts about live court cases.
