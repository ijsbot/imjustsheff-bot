"""Encrypted storage for the bot's memory and private photos.

The GitHub repo is public, so anything saved there unencrypted is readable by anyone -
including followers' DM tips. state.enc and private/*.enc are encrypted with STATE_KEY,
a secret only you (and GitHub Actions) have.

Make a key:  python -m bot.vault --new-key
"""
import json
import os
import sys

from cryptography.fernet import Fernet

from . import config


def _fernet():
    if not config.STATE_KEY:
        raise RuntimeError("STATE_KEY is not set - add it as a GitHub secret (python -m bot.vault --new-key)")
    return Fernet(config.STATE_KEY.encode())


def load_state():
    if not os.path.exists(config.STATE_PATH):
        return {}
    with open(config.STATE_PATH, "rb") as fh:
        return json.loads(_fernet().decrypt(fh.read()))


def save_state(state):
    data = json.dumps(state, ensure_ascii=False).encode("utf-8")
    with open(config.STATE_PATH, "wb") as fh:
        fh.write(_fernet().encrypt(data))


def store_photo(plain_path, story_id):
    """Encrypt a downloaded photo into private/ and delete the plain copy. Returns the stored path."""
    rel = f"private/{story_id}-photo.enc"
    os.makedirs(os.path.join(config.ROOT, "private"), exist_ok=True)
    with open(plain_path, "rb") as fh:
        data = fh.read()
    with open(os.path.join(config.ROOT, rel), "wb") as fh:
        fh.write(_fernet().encrypt(data))
    os.remove(plain_path)
    return rel


def open_photo(rel):
    """Decrypt a stored photo into the (never committed) work folder; returns its path."""
    out = os.path.join(config.WORK_DIR, os.path.basename(rel).replace(".enc", ".jpg"))
    if not os.path.exists(out):
        os.makedirs(config.WORK_DIR, exist_ok=True)
        with open(os.path.join(config.ROOT, rel), "rb") as fh:
            data = _fernet().decrypt(fh.read())
        with open(out, "wb") as fh:
            fh.write(data)
    return out


if __name__ == "__main__":
    if "--new-key" in sys.argv:
        print(Fernet.generate_key().decode())
