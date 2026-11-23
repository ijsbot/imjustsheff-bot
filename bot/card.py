"""Render the branded 1080x1350 card - "broadcast" design matching the IMJUSTSHEFF NEWS logo.

Full-bleed photo graded towards navy (or, with no photo, a night-sky panel built from the
logo's own skyline), the logo across the top, a slanted pink "> TAG" ribbon like the logo's
"> NEWS" tab, a heavy italic headline with key words in hot pink, a neon pink rule, and a
slanted white footer strip like the logo's "SHEFFIELD NEWS / EVENTS / COMMUNITY" banner.
"""
import os
import re

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import config

W, H = 1080, 1350
M = 64
SLANT = 0.21  # parallelogram lean, matching the logo's italic

INK = (6, 10, 28)
NAVY = (14, 26, 70)
WHITE = (255, 255, 255)
# Sensitive mode (deaths, tributes, serious injuries, sexual offences, children): no hot pink.
SLATE = (52, 58, 78)
SOFT_GREY = (150, 156, 172)

FONT = os.path.join(config.FONTS_DIR, "Montserrat-Italic.ttf")
LOGO = os.path.join(config.ASSETS_DIR, "logo-news.png")
SKYLINE_BOX = (170, 0, 1620, 365)  # the skyline + pink arc part of logo-news.png

FOOTER_TOP = H - 132
FOOTER_H = 70


def _font(size, weight=b"Black Italic"):
    font = ImageFont.truetype(FONT, size)
    font.set_variation_by_name(weight)
    return font


def find_location_photo(*texts):
    """Your own area photo from photos/ whose file name appears in the location or headline,
    e.g. photos/sheffield.jpg or photos/page-hall.jpg. Falls back to photos/south-yorkshire.jpg."""
    if not os.path.isdir(config.PHOTOS_DIR):
        return None
    haystack = " ".join(t for t in texts if t).lower()
    files = [f for f in os.listdir(config.PHOTOS_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    # Longest names first so "page-hall" beats "sheffield" when both match.
    for name in sorted(files, key=len, reverse=True):
        place = os.path.splitext(name)[0].lower().replace("-", " ").replace("_", " ")
        if place and place in haystack:
            return os.path.join(config.PHOTOS_DIR, name)
    for name in files:
        if os.path.splitext(name)[0].lower() in ("south-yorkshire", "default"):
            return os.path.join(config.PHOTOS_DIR, name)
    return None


# --- backgrounds -----------------------------------------------------------------------

def _cover(photo, width, height):
    """Scale and crop to fill width x height (like CSS object-fit: cover)."""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    scale = max(width / photo.width, height / photo.height)
    photo = photo.resize((round(photo.width * scale), round(photo.height * scale)), Image.LANCZOS)
    left = (photo.width - width) // 2
    top = max(0, (photo.height - height) // 3)  # bias towards the top - faces are usually there
    return photo.crop((left, top, left + width, top + height))


def _vertical_fade(img, top, bottom, a0, a1, colour=INK):
    mask = Image.linear_gradient("L").resize((W, bottom - top)).point(lambda v: round(a0 + (a1 - a0) * v / 255))
    img.paste(Image.new("RGB", (W, bottom - top), colour), (0, top), mask)


def _photo_background(path):
    with Image.open(path) as photo:
        img = _cover(photo, W, H)
    # Grade towards the logo's night-time navy so every photo feels on-brand.
    img = Image.blend(img, Image.new("RGB", (W, H), NAVY), 0.18)
    return img


def _night_background(sensitive=False):
    """No photo: navy night sky, the logo's skyline enlarged and softened, pink glow."""
    sky = Image.linear_gradient("L").resize((W, H))
    img = Image.composite(Image.new("RGB", (W, H), INK), Image.new("RGB", (W, H), (16, 30, 82)), sky)

    glow = Image.radial_gradient("L").resize((W * 2, H)).crop((W // 2, 0, W * 3 // 2, H))
    glow_colour = (40, 50, 90) if sensitive else (120, 20, 110)
    img.paste(Image.new("RGB", (W, H), glow_colour), (0, 0), glow.point(lambda v: max(0, 200 - v) * 60 // 200))

    skyline = Image.open(LOGO).convert("RGBA").crop(SKYLINE_BOX)
    width = int(W * 1.25)
    skyline = skyline.resize((width, round(skyline.height * width / skyline.width)), Image.LANCZOS)
    skyline = skyline.filter(ImageFilter.GaussianBlur(1.2))
    # Fade the skyline out towards its base so it melts into the night instead of ending in a line.
    fade = Image.linear_gradient("L").resize(skyline.size).point(lambda v: 255 if v < 110 else max(0, 255 - (v - 110) * 2))
    alpha = Image.composite(skyline.getchannel("A"), Image.new("L", skyline.size, 0), fade)
    skyline.putalpha(alpha.point(lambda v: v * 170 // 255))
    base = img.convert("RGBA")
    base.alpha_composite(skyline, ((W - width) // 2, 330))
    return base.convert("RGB")


# --- pieces ----------------------------------------------------------------------------

def _parallelogram(d, x, y, w, h, fill, outline=None, width=0):
    lean = round(h * SLANT)
    d.polygon([(x + lean, y), (x + w + lean, y), (x + w, y + h), (x, y + h)], fill=fill,
              outline=outline, width=width)


def _shadowed_text(img, xy, text, font, fill, shadow=(0, 0, 0, 170), offset=(4, 6), blur=6):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((xy[0] + offset[0], xy[1] + offset[1]), text, font=font, fill=shadow)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=fill)
    img.alpha_composite(layer)


def _neon_rule(img, x, y, length, colour):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    _parallelogram(d, x, y, length, 8, colour + (255,))
    glow = layer.filter(ImageFilter.GaussianBlur(10))
    img.alpha_composite(glow)
    img.alpha_composite(layer)


def _tag_ribbon(img, x, y, tag, location, sensitive=False):
    d = ImageDraw.Draw(img)
    font = _font(40)
    h = 64
    text_w = d.textlength(tag, font=font)
    w = int(text_w + 96)
    # Sensitive: white tag with dark text and a slate location plate - respectful, still on-brand.
    tag_fill, tag_text = (WHITE, INK) if sensitive else (config.TAG_COLOURS.get(tag, config.PINK), WHITE)
    loc_fill, loc_text = (SLATE, WHITE) if sensitive else (WHITE, INK)
    _parallelogram(d, x, y, w, h, tag_fill)
    # Play-button triangle, like the logo's "> NEWS".
    tx, ty = x + 30, y + 18
    d.polygon([(tx, ty), (tx + 24, ty + 14), (tx, ty + 28)], fill=tag_text)
    d.text((x + 66, y + 9), tag, font=font, fill=tag_text)
    if location:
        loc_font = _font(34, b"ExtraBold Italic")
        lw = int(d.textlength(location.upper(), font=loc_font) + 52)
        _parallelogram(d, x + w + 10, y, lw, h, loc_fill)
        d.text((x + w + 36, y + 13), location.upper(), font=loc_font, fill=loc_text)


def _footer(img, source_name, photo_credit, sensitive=False, top=FOOTER_TOP, right=0, credit_word="IMAGE"):
    """right: extra space kept free on the right (Reels put their like/comment buttons there)."""
    d = ImageDraw.Draw(img)
    accent = SOFT_GREY if sensitive else config.PINK
    width = W - right
    # Slanted white strip with a coloured edge, like the logo's tagline banner.
    _parallelogram(d, M - 20, top - 6, width - 2 * M + 24, FOOTER_H + 12, accent)
    _parallelogram(d, M - 14, top, width - 2 * M + 12, FOOTER_H, WHITE)
    small = _font(24, b"ExtraBold Italic")
    text = f"SOURCE: {source_name.upper()}"
    if photo_credit and photo_credit.strip().lower() != source_name.strip().lower():
        if source_name.strip().lower() == config.BRAND_NAME.lower():  # the handle already says it's us
            text = f"{credit_word}: {photo_credit.upper()}"
        else:
            text += f"  /  {credit_word}: {photo_credit.upper()}"
    handle_font = _font(30)
    handle = config.BRAND_HANDLE.upper()
    handle_w = d.textlength(handle, font=handle_font)
    while d.textlength(text, font=small) > width - 2 * M - handle_w - 70 and len(text) > 10:
        text = text[:-2].rstrip() + "…"
    d.text((M + 18, top + 21), text, font=small, fill=INK)
    d.text((width - M - handle_w - 10, top + 16), handle, font=handle_font, fill=INK if sensitive else accent)


# --- headline --------------------------------------------------------------------------

def _wrap(d, words, font, width):
    lines, line = [], []
    for word in words:
        trial = line + [word]
        if d.textlength(" ".join(trial), font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = [word]
    return lines + ([line] if line else [])


def _fit(d, words, width, max_height):
    for size in range(100, 51, -4):
        font = _font(size)
        lines = _wrap(d, words, font, width)
        line_h = round(size * 1.08)
        if len(lines) * line_h <= max_height:
            return font, lines, line_h
    font = _font(52)
    return font, _wrap(d, words, font, width), 56


def _key(word):
    return re.sub(r"[^A-Z0-9]", "", word.upper())


def _highlight_positions(words, highlight, location):
    """Positions of the words to colour pink: the first exact run of the AI's phrase in the
    headline, else of the place name. Only that run - not every repeat of a word."""
    keys = [_key(w) for w in words]
    for phrase in (highlight, location):
        target = [k for k in (_key(w) for w in (phrase or "").split()) if k]
        n = len(target)
        for i in range(len(keys) - n + 1) if n else ():
            if keys[i:i + n] == target:
                return set(range(i, i + n))
    return set()


def _draw_headline(img, lines, font, line_h, top, pink_positions):
    d = ImageDraw.Draw(img)
    space = d.textlength(" ", font=font)
    y, index = top, 0
    for line in lines:
        x = M
        for word in line:
            colour = config.PINK if index in pink_positions else WHITE
            _shadowed_text(img, (x, y), word, font, colour)
            x += d.textlength(word, font=font) + space
            index += 1
        y += line_h
    return y


# --- render ----------------------------------------------------------------------------

def render(headline, tag, source_name, location, out_path, photo_path=None, photo_credit=None,
           highlight=None, sensitive=False):
    """sensitive=True: muted white/slate/grey styling with no hot pink, for tragic stories."""
    has_photo = bool(photo_path and os.path.exists(photo_path))
    img = (_photo_background(photo_path) if has_photo else _night_background(sensitive))

    # A light shade behind the corner logo, and a heavy one behind the headline.
    _vertical_fade(img, 0, 230, 150 if has_photo else 0, 0)
    _vertical_fade(img, 560, H, 0, 248)
    img = img.convert("RGBA")

    # Small logo tucked in the top-left corner so faces (e.g. police mugshots) stay visible.
    # Photo-less cards have nothing to cover, so the logo can be bigger there.
    logo = Image.open(LOGO).convert("RGBA")
    logo_w = 400 if has_photo else 640
    logo = logo.resize((logo_w, round(logo.height * logo_w / logo.width)), Image.LANCZOS)
    img.alpha_composite(logo, (24, 18) if has_photo else ((W - logo_w) // 2, 28))

    d = ImageDraw.Draw(img)
    words = headline.upper().split()
    font, lines, line_h = _fit(d, words, W - 2 * M - 10, 400)
    text_h = len(lines) * line_h
    head_top = FOOTER_TOP - 74 - text_h

    _tag_ribbon(img, M, head_top - 96, tag, location, sensitive)
    pink = set() if sensitive else _highlight_positions(words, highlight, location)
    bottom = _draw_headline(img, lines, font, line_h, head_top, pink)
    _neon_rule(img, M, bottom + 18, 300, SOFT_GREY if sensitive else config.PINK)
    _footer(img, source_name, photo_credit if has_photo else None, sensitive)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.convert("RGB").save(out_path, "JPEG", quality=93)
    return out_path


# --- video overlay ---------------------------------------------------------------------
# Reels are 1080x1920. Instagram draws its own header at the top, the caption/username at the
# bottom and like/comment/share buttons down the right, so everything sits inside those margins.
VIDEO_H = 1920
REEL_TOP, REEL_BOTTOM, REEL_RIGHT = 200, 400, 150


def _alpha_fade(img, top, bottom, a0, a1, colour=INK):
    alpha = Image.linear_gradient("L").resize((W, bottom - top)).point(lambda v: round(a0 + (a1 - a0) * v / 255))
    layer = Image.new("RGBA", (W, bottom - top), colour + (255,))
    layer.putalpha(alpha)
    img.alpha_composite(layer, (0, top))


def render_overlay(headline, tag, source_name, location, out_path, video_credit=None,
                   highlight=None, sensitive=False):
    """A transparent 1080x1920 PNG with the page's branding, laid over a video for a Reel."""
    img = Image.new("RGBA", (W, VIDEO_H), (0, 0, 0, 0))
    _alpha_fade(img, 0, 420, 150, 0)
    _alpha_fade(img, 900, VIDEO_H, 0, 235)

    logo = Image.open(LOGO).convert("RGBA")
    logo_w = 380
    logo = logo.resize((logo_w, round(logo.height * logo_w / logo.width)), Image.LANCZOS)
    img.alpha_composite(logo, (32, REEL_TOP - 60))

    footer_top = VIDEO_H - REEL_BOTTOM - FOOTER_H
    d = ImageDraw.Draw(img)
    words = headline.upper().split()
    font, lines, line_h = _fit(d, words, W - 2 * M - REEL_RIGHT, 380)
    head_top = footer_top - 74 - len(lines) * line_h
    _tag_ribbon(img, M, head_top - 96, tag, location, sensitive)
    pink = set() if sensitive else _highlight_positions(words, highlight, location)
    bottom = _draw_headline(img, lines, font, line_h, head_top, pink)
    _neon_rule(img, M, bottom + 18, 300, SOFT_GREY if sensitive else config.PINK)
    _footer(img, source_name, video_credit, sensitive, top=footer_top, right=REEL_RIGHT, credit_word="VIDEO")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
