"""Render the branded 1080x1350 headline card."""
import os

from PIL import Image, ImageDraw, ImageFont, ImageOps

from . import config

W, H = 1080, 1350
MARGIN = 80

FONT_CANDIDATES = [
    os.path.join(config.FONTS_DIR, "bold.ttf"),  # drop your own brand font here
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]
REGULAR_CANDIDATES = [
    os.path.join(config.FONTS_DIR, "regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/Library/Fonts/Arial.ttf",
]


def _font(candidates, size):
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _fit_headline(draw, text, width, max_height, largest=104):
    for size in range(largest, 43, -4):
        font = _font(FONT_CANDIDATES, size)
        lines = _wrap(draw, text, font, width)
        line_h = int(size * 1.15)
        if len(lines) * line_h <= max_height:
            return font, lines, line_h
    font = _font(FONT_CANDIDATES, 44)
    return font, _wrap(draw, text, font, width), int(44 * 1.15)


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
    """Scale and centre-crop to fill width x height (like CSS object-fit: cover)."""
    photo = ImageOps.exif_transpose(photo).convert("RGB")
    scale = max(width / photo.width, height / photo.height)
    photo = photo.resize((round(photo.width * scale), round(photo.height * scale)), Image.LANCZOS)
    left = (photo.width - width) // 2
    top = max(0, (photo.height - height) // 3)  # bias towards the top - faces are usually there
    return photo.crop((left, top, left + width, top + height))


def _fade(img, box, start_alpha, end_alpha):
    """Vertical fade of BLACK over img inside box=(top, bottom)."""
    top, bottom = box
    mask = Image.new("L", (1, bottom - top))
    for y in range(bottom - top):
        mask.putpixel((0, y), round(start_alpha + (end_alpha - start_alpha) * y / max(1, bottom - top - 1)))
    mask = mask.resize((W, bottom - top))
    img.paste(Image.new("RGB", (W, bottom - top), config.BLACK), (0, top), mask)


def _pill(d, x, y, text, colour, size=38):
    font = _font(FONT_CANDIDATES, size)
    w = int(d.textlength(text, font=font))
    d.rounded_rectangle([x, y, x + w + 56, y + 70], radius=35, fill=colour)
    d.text((x + 28, y + 13), text, font=font, fill=config.WHITE)


def _stripe(d):
    third = H // 3
    for i, colour in enumerate((config.RED, config.BLUE, config.PINK)):
        d.rectangle([0, i * third, 18, (i + 1) * third], fill=colour)


def _footer(d, source_name):
    small = _font(REGULAR_CANDIDATES, 36)
    d.rectangle([MARGIN, H - 190, W - MARGIN, H - 187], fill=(60, 60, 70))
    d.text((MARGIN, H - 160), f"Source: {source_name}", font=small, fill=config.GREY)
    d.text((MARGIN, H - 110), config.BRAND_HANDLE, font=_font(FONT_CANDIDATES, 40), fill=config.WHITE)


def render(headline, tag, source_name, location, out_path, photo_path=None, photo_credit=None):
    if photo_path and os.path.exists(photo_path):
        img = _render_photo(headline, tag, source_name, location, photo_path, photo_credit)
    else:
        img = _render_text(headline, tag, source_name, location)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return out_path


FOOTER_TOP = H - 215


def _render_photo(headline, tag, source_name, location, photo_path, photo_credit):
    img = Image.new("RGB", (W, H), config.BLACK)

    # Headline is anchored just above the footer; the photo fills everything above it,
    # so a short headline gets a bigger photo.
    font, lines, line_h = _fit_headline(ImageDraw.Draw(img), headline, W - 2 * MARGIN, 440, largest=84)
    head_top = FOOTER_TOP - len(lines) * line_h - 10
    pill_y = head_top - 100
    photo_h = pill_y + 140

    with Image.open(photo_path) as photo:
        img.paste(_cover(photo, W, photo_h), (0, 0))

    # Dark at the top for the wordmark, melting into black at the bottom so the
    # photo flows straight into the headline.
    _fade(img, (0, 240), 170, 0)
    _fade(img, (photo_h - 330, photo_h), 0, 255)

    if photo_credit:
        # Translucent dark pill so the credit reads on any photo.
        credit_font = _font(FONT_CANDIDATES, 24)
        text = f"Image: {photo_credit}"
        probe = ImageDraw.Draw(img)
        w = int(probe.textlength(text, font=credit_font))
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rounded_rectangle(
            [W - MARGIN - w - 32, 66, W - MARGIN, 112], radius=23, fill=(0, 0, 0, 150))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        ImageDraw.Draw(img).text((W - MARGIN - w - 16, 75), text, font=credit_font, fill=config.WHITE)

    d = ImageDraw.Draw(img)
    _stripe(d)

    mark = _font(FONT_CANDIDATES, 46)
    d.text((MARGIN, 60), config.BRAND_NAME, font=mark, fill=config.PINK, stroke_width=3, stroke_fill=config.BLACK)
    d.rectangle([MARGIN, 122, MARGIN + 120, 128], fill=config.RED)

    # Tag pill sits where the photo fades out - the eye lands here first.
    _pill(d, MARGIN, pill_y, tag, config.TAG_COLOURS.get(tag, config.PINK))
    if location:
        loc_font = _font(FONT_CANDIDATES, 30)
        tag_w = d.textlength(tag, font=_font(FONT_CANDIDATES, 38))
        d.text((MARGIN + tag_w + 86, pill_y + 19), f"• {location.upper()}", font=loc_font, fill=config.WHITE,
               stroke_width=2, stroke_fill=config.BLACK)

    y = head_top
    for line in lines:
        d.text((MARGIN, y), line, font=font, fill=config.WHITE)
        y += line_h

    _footer(d, source_name)
    return img


def _render_text(headline, tag, source_name, location):
    img = Image.new("RGB", (W, H), config.BLACK)
    d = ImageDraw.Draw(img)
    _stripe(d)

    # Wordmark.
    mark = _font(FONT_CANDIDATES, 46)
    d.text((MARGIN, 70), config.BRAND_NAME, font=mark, fill=config.PINK)
    d.rectangle([MARGIN, 132, MARGIN + 120, 138], fill=config.RED)

    top = 230
    _pill(d, MARGIN, top, tag, config.TAG_COLOURS.get(tag, config.PINK))

    # Headline.
    head_top = top + 120
    font, lines, line_h = _fit_headline(d, headline, W - 2 * MARGIN, 700)
    y = head_top
    for line in lines:
        d.text((MARGIN, y), line, font=font, fill=config.WHITE)
        y += line_h

    # Location under the headline.
    small = _font(REGULAR_CANDIDATES, 36)
    if location:
        d.text((MARGIN, y + 30), f"• {location.upper()}", font=small, fill=config.PINK)

    _footer(d, source_name)
    return img
