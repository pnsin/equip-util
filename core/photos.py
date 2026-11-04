"""장비 사진을 구글 시트 한 칸(50,000자)에 들어가게 줄입니다.

사진은 JPEG 로 줄여 base64 글자로 저장합니다. 큰 사진(photo)은 40,000자 안,
카드에 쓰는 작은 사진(thumb)은 12,000자 안으로 맞춥니다.
"""
from __future__ import annotations

import base64
import io

PHOTO_MAX = 40000
THUMB_MAX = 12000


def _fit(img, long_side: int, limit: int) -> str:
    from PIL import Image
    side = long_side
    while True:
        im = img.copy()
        im.thumbnail((side, side), Image.LANCZOS)
        for q in (82, 74, 66, 58, 50):
            bio = io.BytesIO()
            im.save(bio, "JPEG", quality=q, optimize=True, progressive=True)
            b = base64.b64encode(bio.getvalue()).decode()
            if len(b) <= limit:
                return b
        side = int(side * 0.8)
        if side < 80:
            return b


def shrink(data: bytes) -> tuple[str, str]:
    """(작은 사진, 큰 사진) base64. 사진이 아니면 ValueError."""
    from PIL import Image, ImageOps
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
    except Exception as e:  # noqa: BLE001
        raise ValueError("사진 파일이 아니에요") from e
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    return _fit(img, 360, THUMB_MAX), _fit(img, 1100, PHOTO_MAX)


def data_uri(b64: str) -> str:
    return f"data:image/jpeg;base64,{b64}" if b64 else ""
