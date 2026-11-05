"""Settings for the imjustsheff news bot.

Secrets come from environment variables (GitHub Actions secrets).
Everything else - sources, filters, branding - lives here so it is easy to tweak.
"""
import os

# --- Branding --------------------------------------------------------------
BRAND_NAME = "IMJUSTSHEFF"
BRAND_HANDLE = "@imjustsheff"

BLACK = (11, 11, 15)
WHITE = (255, 255, 255)
GREY = (160, 160, 170)
RED = (230, 20, 40)
BLUE = (30, 90, 255)
PINK = (255, 30, 150)

# Colour of the tag pill on each card (tag is chosen per story).
TAG_COLOURS = {
    "BREAKING": RED,
    "APPEAL": BLUE,
    "MISSING": PINK,
    "WANTED": RED,
    "UPDATE": PINK,
    "COURT": BLUE,
    "WARNING": RED,
    "NEWS": PINK,
}

# --- Sources ---------------------------------------------------------------
# kind: "rss" (normal feed), "inoreader_html" (Inoreader free HTML clip), "ea_floods" (Environment Agency JSON)
# official: public-sector source - safe to base a post on.
# media: news outlet - used as a TIP only; captions are rewritten and credited.
# local_only: only keep items mentioning a South Yorkshire place (for site-wide feeds).
SOURCES = [
    {
        "id": "syp",
        "name": "South Yorkshire Police",
        "kind": "inoreader_html",
        "url": "https://www.inoreader.com/stream/user/1003682447/tag/SYP/view/html",
        "official": True,
        "emoji": "🚓",
    },
    {
        "id": "metoffice",
        "name": "Met Office",
        "kind": "rss",
        "url": "https://www.metoffice.gov.uk/public/data/PWSCache/WarningsRSS/Region/yh",
        "official": True,
        "emoji": "🌧️",
    },
    {
        "id": "ea_floods",
        "name": "Environment Agency",
        "kind": "ea_floods",
        "url": "https://environment.data.gov.uk/flood-monitoring/id/floods?county=Sheffield",
        "official": True,
        "emoji": "🌊",
    },
    {
        "id": "rotherham_council",
        "name": "Rotherham Council",
        "kind": "rss",
        "url": "https://www.rotherham.gov.uk/rss/news",
        "official": True,
        "emoji": "🏛️",
    },
    {
        "id": "bbc",
        "name": "BBC News",
        "kind": "rss",
        "url": "https://feeds.bbci.co.uk/news/england/south_yorkshire/rss.xml",
        "media": True,
        "emoji": "📰",
    },
    {
        "id": "star",
        "name": "The Star",
        "kind": "rss",
        "url": "https://www.thestar.co.uk/rss",
        "media": True,
        "local_only": True,
        "emoji": "📰",
    },
    {
        "id": "tribune",
        "name": "Sheffield Tribune",
        "kind": "rss",
        "url": "https://www.sheffieldtribune.co.uk/rss/",
        "media": True,
        "emoji": "📰",
    },
    {
        "id": "dfp",
        "name": "Doncaster Free Press",
        "kind": "rss",
        "url": "https://www.doncasterfreepress.co.uk/rss",
        "media": True,
        "local_only": True,
        "emoji": "📰",
    },
    {
        "id": "advertiser",
        "name": "Rotherham Advertiser",
        "kind": "rss",
        "url": "https://www.rotherhamadvertiser.co.uk/rss",
        "media": True,
        "emoji": "📰",
    },
    {
        "id": "ypost",
        "name": "Yorkshire Post",
        "kind": "rss",
        "url": "https://www.yorkshirepost.co.uk/rss",
        "media": True,
        "local_only": True,
        "emoji": "📰",
    },
]

# Items from local_only sources must mention one of these.
LOCAL_PLACES = [
    "sheffield", "doncaster", "rotherham", "barnsley", "south yorkshire",
    "hillsborough", "crookes", "ecclesall", "walkley", "darnall", "page hall",
    "firth park", "meadowhall", "stocksbridge", "dronfield", "mexborough",
    "conisbrough", "wombwell", "darfield", "penistone", "maltby", "dinnington",
    "wath", "swinton", "rawmarsh", "bentley", "balby", "hexthorpe", "thorne",
    "armthorpe", "edlington", "askern", "goldthorpe", "hoyland", "cudworth",
]

# Media items containing any of these are dropped before any AI call.
SKIP_WORDS = [
    "sheffield united", "sheffield wednesday", "doncaster rovers", "rotherham united",
    "barnsley fc", "transfer", "match report", "player ratings", "fixtures",
    "recipe", "quiz", "horoscope", "crossword", "property of the week", "for sale",
    "best restaurants", "review:", "in pictures", "nostalgia", "retro",
]

# --- Behaviour ---------------------------------------------------------------
DEDUPE_WINDOW_HOURS = 72          # compare new items against stories from this long ago
MAX_NEW_ITEMS_PER_RUN = 15        # the rest wait for the next run
CARD_RETENTION_DAYS = 14          # old card images are deleted from the repo
SEEN_RETENTION_DAYS = 60

# --- Secrets / environment -------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

IG_USER_ID = os.environ.get("IG_USER_ID", "")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
# Facebook Page linked to the Instagram account - needed to read Instagram DMs (tips from followers).
IG_PAGE_ID = os.environ.get("IG_PAGE_ID", "")
GRAPH_API_VERSION = os.environ.get("GRAPH_API_VERSION") or "v23.0"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# claude-opus-5-5 writes the best captions. claude-haiku-5-5 costs ~40x less.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL") or "claude-opus-5-5"

# Public base URL where card images are reachable (Instagram downloads them from here).
# On GitHub Actions this is worked out automatically from the repo name and branch.
_repo = os.environ.get("GITHUB_REPOSITORY", "")
_branch = os.environ.get("GITHUB_REF_NAME", "main")
IMAGE_BASE_URL = os.environ.get("IMAGE_BASE_URL") or (
    f"https://raw.githubusercontent.com/{_repo}/{_branch}" if _repo else ""
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "state.json")
CARDS_DIR = os.path.join(ROOT, "cards")
FONTS_DIR = os.path.join(ROOT, "fonts")
PHOTOS_DIR = os.path.join(ROOT, "photos")  # your own area photos, e.g. photos/sheffield.jpg
