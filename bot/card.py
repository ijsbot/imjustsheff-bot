"""Render the branded 1080x1350 headline card."""
import os

from PIL import Image, ImageDraw, ImageFont

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


def _fit_headline(draw, text, width, max_height):
    for size in range(104, 47, -4):
        font = _font(FONT_CANDIDATES, size)
        lines = _wrap(draw, text, font, width)
        line_h = int(size * 1.15)
        if len(lines) * line_h <= max_height:
            return font, lines, line_h
    font = _font(FONT_CANDIDATES, 48)
    return font, _wrap(draw, text, font, width), int(48 * 1.15)


def render(headline, tag, source_name, location, out_path):
    img = Image.new("RGB", (W, H), config.BLACK)
    d = ImageDraw.Draw(img)

    # Tri-colour stripe down the left edge.
    third = H // 3
    for i, colour in enumerate((config.RED, config.BLUE, config.PINK)):
        d.rectangle([0, i * third, 18, (i + 1) * third], fill=colour)

    # Wordmark.
    mark = _font(FONT_CANDIDATES, 46)
    d.text((MARGIN, 70), config.BRAND_NAME, font=mark, fill=config.PINK)
    d.rectangle([MARGIN, 132, MARGIN + 120, 138], fill=config.RED)

    # Tag pill.
    tag_font = _font(FONT_CANDIDATES, 38)
    tag_w = int(d.textlength(tag, font=tag_font))
    top = 230
    d.rounded_rectangle([MARGIN, top, MARGIN + tag_w + 56, top + 70], radius=35,
                        fill=config.TAG_COLOURS.get(tag, config.PINK))
    d.text((MARGIN + 28, top + 13), tag, font=tag_font, fill=config.WHITE)

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

    # Footer.
    d.rectangle([MARGIN, H - 190, W - MARGIN, H - 187], fill=(60, 60, 70))
    d.text((MARGIN, H - 160), f"Source: {source_name}", font=small, fill=config.GREY)
    d.text((MARGIN, H - 110), config.BRAND_HANDLE, font=_font(FONT_CANDIDATES, 40), fill=config.WHITE)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    img.save(out_path, "JPEG", quality=92)
    return out_path
