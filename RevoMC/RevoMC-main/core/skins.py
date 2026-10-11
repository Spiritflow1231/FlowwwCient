"""Validation and per-account storage for local skin and cape images."""

import shutil
from pathlib import Path

from PIL import Image


def account_cosmetic_dir(account_id: str) -> Path:
    if not account_id or any(char not in "0123456789abcdef-" for char in account_id.lower()):
        raise ValueError("The account has an invalid identifier.")
    root = Path.home() / ".revomc" / "cosmetics" / account_id
    if root.is_symlink():
        raise ValueError("The account cosmetic folder cannot be a symbolic link.")
    root.mkdir(parents=True, exist_ok=True)
    return root


def validate_cosmetic_image(path: Path, cosmetic: str) -> tuple[int, int]:
    if cosmetic not in {"skin", "cape"}:
        raise ValueError("Choose either a skin or a cape image.")
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".png":
        raise ValueError("Choose a regular PNG image file.")
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("The PNG image exceeds the 4 MiB size limit.")
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise ValueError("The selected image is not a PNG.")
            width, height = image.size
            image.verify()
    except (OSError, ValueError) as exc:
        raise ValueError(f"The selected PNG could not be decoded: {exc}") from exc
    if not (64 <= width <= 256 and 32 <= height <= 256 and width % 64 == 0):
        raise ValueError("Use a standard 64-pixel Minecraft skin or cape canvas, up to 256 pixels.")
    if cosmetic == "skin" and width not in (height, height * 2):
        raise ValueError("A skin must use a square or classic 2:1 skin canvas.")
    if cosmetic == "cape" and width != height * 2:
        raise ValueError("A cape must use a 2:1 canvas (for example, 64 × 32).")
    return width, height


def store_cosmetic(account_id: str, source: Path, cosmetic: str) -> Path:
    validate_cosmetic_image(source, cosmetic)
    destination = account_cosmetic_dir(account_id) / f"{cosmetic}.png"
    shutil.copyfile(source, destination)
    return destination


def cosmetic_preview(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        image = source.convert("RGBA")
        image.thumbnail(size)
        return image.copy()
