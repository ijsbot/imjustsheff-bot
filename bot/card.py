"""Render the branded 1080x1350 card ("design C").

Top: the photo (or, with no photo, a dark panel with the Sheffield skyline from the logo).
A brand stripe (grey -> black -> navy -> blue -> pink, like the logo lettering) splits it from
a white panel holding the tag, a Bebas Neue headline, the source and the logo.
"""
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import config

W, H = 1080, 1350
M = 70
SPLIT = 700  # where the photo ends and the white panel starts

INK = (10, 10, 18)
WHITE = (255, 255, 255)
NAVY = (18, 38, 105)
SOURCE_GREY = (110, 110, 120)

BEBAS = os.path.join(config.FONTS_DIR, "BebasNeue-Regular.ttf")
OSWALD = os.path.join(config.FONTS_DIR, "Oswald.ttf")
LOGO = os.path.join(config.ASSETS_DIR, "logo-transparent.png")
SKYLINE_BOX = (575, 0, 1155, 172)  # the skyline part of logo-transparent.png


def _bebas(size):
    return ImageFont.truetype(BEBAS, size)


def _oswald(size, weight=b"Regular"):
    font = ImageFont.truetype(OSWALD, size)
    font.set_variation_by_name(weight)
    return font


def _logo(height):
    im = Image.open(LOGO).convert("RGBA")
    return im.resize((round(im.width * height / im.height), height), Image.LANCZOS)


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


def _cover(photo, width, height):
    """Scale and crop to fill width x height (like CSS object-fit: cover)."""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    scale = max(width / photo.width, height / photo.height)
    photo = photo.resize((round(photo.width * scale), round(photo.height * scale)), Image.LANCZOS)
    left = (photo.width - width) // 2
    top = max(0, (photo.height - height) // 3)  # bias towards the top - faces are usually there
    return photo.crop((left, top, left + width, top + height))


def _brand_stripe(img, y, height):
    stops = [(95, 95, 100), INK, NAVY, config.BLUE, config.PINK]
    stripe = Image.new("RGB", (W, height))
    d = ImageDraw.Draw(stripe)
    for x in range(W):
        t = x / (W - 1) * (len(stops) - 1)
        i = min(int(t), len(stops) - 2)
        f = t - i
        d.line([(x, 0), (x, height)], fill=tuple(round(stops[i][k] + (stops[i + 1][k] - stops[i][k]) * f)
                                                 for k in range(3)))
    img.paste(stripe, (0, y))


def _skyline_panel(img):
    """No photo: dark panel with a soft navy glow and the logo's skyline, faded."""
    panel = Image.new("RGB", (W, SPLIT), INK)
    glow = Image.radial_gradient("L").resize((W * 2, SPLIT * 2)).crop((W // 2, SPLIT // 2, W * 3 // 2, SPLIT * 3 // 2))
    panel.paste(Image.new("RGB", (W, SPLIT), NAVY), (0, 0), glow.point(lambda v: (255 - v) * 120 // 255))
    skyline = Image.open(LOGO).convert("RGBA").crop(SKYLINE_BOX)
    skyline = skyline.resize((W, round(skyline.height * W / skyline.width)), Image.LANCZOS)
    alpha = skyline.getchannel("A").point(lambda v: v * 110 // 255)
    skyline.putalpha(alpha)
    base = panel.convert("RGBA")
    base.alpha_composite(skyline, (0, SPLIT - skyline.height))
    img.paste(base.convert("RGB"), (0, 0))


def _credit(img, text):
    d = ImageDraw.Draw(img, "RGBA")
    font = _oswald(22, b"Medium")
    w = d.textlength(text, font=font)
    d.rounded_rectangle([W - M - w - 28, 30, W - M, 68], radius=19, fill=(0, 0, 0, 150))
    d.text((W - M - w - 14, 35), text, font=font, fill=WHITE)


def _pill(d, x, y, text, fill, size=46):
    font = _bebas(size)
    w = d.textlength(text, font=font)
    d.rounded_rectangle([x, y, x + w + 44, y + size + 14], radius=8, fill=fill)
    d.text((x + 22, y + 9), text, font=font, fill=WHITE)
    return x + w + 44


def _wrap(d, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if d.textlength(trial, font=font) <= width or not line:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + ([line] if line else [])


def _fit_headline(d, text, width, max_height):
    for size in range(124, 55, -4):
        font = _bebas(size)
        lines = _wrap(d, text.upper(), font, width)
        line_h = round(size * 0.95)
        if len(lines) * line_h <= max_height:
            return font, lines, line_h
    font = _bebas(56)
    return font, _wrap(d, text.upper(), font, width), 53


def render(headline, tag, source_name, location, out_path, photo_path=None, photo_credit=None):
    img = Image.new("RGB", (W, H), WHITE)

    if photo_path and os.path.exists(photo_path):
        with Image.open(photo_path) as photo:
            img.paste(_cover(photo, W, SPLIT), (0, 0))
        if photo_credit:
            _credit(img, f"IMAGE: {photo_credit.upper()}")
    else:
        _skyline_panel(img)

    _brand_stripe(img, SPLIT, 12)
    d = ImageDraw.Draw(img)

    # Tag + location pills sit on the seam between photo and panel.
    x = _pill(d, M, SPLIT - 40, tag, config.TAG_COLOURS.get(tag, config.PINK))
    if location:
        _pill(d, x + 14, SPLIT - 40, location.upper(), INK)

    font, lines, line_h = _fit_headline(d, headline, W - 2 * M, 400)
    y = SPLIT + 70
    for line in lines:
        d.text((M, y), line, font=font, fill=INK)
        y += line_h

    logo = _logo(100)
    img.paste(logo, (W - M - logo.width, H - 36 - logo.height), logo)
    d.text((M, H - 100), f"SOURCE: {source_name.upper()}", font=_oswald(26), fill=SOURCE_GREY)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return out_path
