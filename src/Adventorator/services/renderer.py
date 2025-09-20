from __future__ import annotations

import time
from dataclasses import dataclass

from Adventorator.metrics import inc_counter, observe_histogram


@dataclass(frozen=True)
class Token:
    name: str
    x: int
    y: int
    color: tuple[int, int, int] = (64, 128, 255)  # default blue-ish
    active: bool = False


@dataclass(frozen=True)
class RenderInput:
    encounter_id: int
    last_event_id: int | None
    width: int = 512
    height: int = 512
    grid_size: int = 10  # squares per side
    cell_px: int = 48
    background: tuple[int, int, int] = (245, 245, 245)  # light gray
    tokens: list[Token] = None  # type: ignore[assignment]


_cache: dict[tuple[int, int | None], bytes] = {}


def reset_cache() -> None:
    _cache.clear()


def _cache_key(inp: RenderInput) -> tuple[int, int | None]:
    """Keyed by (encounter_id, last_event_id)."""
    return (inp.encounter_id, inp.last_event_id)


def render_map(inp: RenderInput) -> bytes:
    """Return a PNG (bytes). Uses a simple in-process cache by encounter/event.

    Implementation note: This placeholder produces a minimal deterministic PNG using
    only the Python stdlib to avoid adding dependencies now. It can be replaced
    with a Pillow/matplotlib implementation later.
    """
    key = _cache_key(inp)
    if key in _cache:
        inc_counter("renderer.cache.hit")
        return _cache[key]

    start = time.perf_counter()

    # Try to draw a visible placeholder using Pillow if available; otherwise tiny PNG fallback
    try:
        from PIL import Image, ImageDraw  # type: ignore[import-not-found]

        width = max(128, inp.width)
        height = max(128, inp.height)
        img = Image.new("RGB", (width, height), inp.background)
        draw = ImageDraw.Draw(img)

        # Grid
        cell = max(24, inp.cell_px)
        # vertical lines
        for x in range(0, width + 1, cell):
            draw.line([(x, 0), (x, height)], fill=(200, 200, 200), width=1)
        # horizontal lines
        for y in range(0, height + 1, cell):
            draw.line([(0, y), (width, y)], fill=(200, 200, 200), width=1)

        # Border
        draw.rectangle([(0, 0), (width - 1, height - 1)], outline=(100, 100, 100), width=2)

        # Tokens (optional)
        tokens = inp.tokens or []
        for t in tokens:
            # Token center in pixels (grid coords scaled by cell size)
            cx = int((t.x + 0.5) * cell)
            cy = int((t.y + 0.5) * cell)
            r = max(8, cell // 3)
            bbox = [(cx - r, cy - r), (cx + r, cy + r)]
            color = t.color
            draw.ellipse(bbox, fill=color, outline=(0, 0, 0))
            if t.active:
                # Highlight ring for active token
                draw.ellipse(
                    [(cx - r - 3, cy - r - 3), (cx + r + 3, cy + r + 3)],
                    outline=(255, 215, 0),
                    width=2,
                )

        # Encode PNG
        import io as _io

        buf = _io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        png = buf.getvalue()
    except Exception:
        # Minimal PNG: 1x1 transparent image header (valid PNG). Replace later with real draw.
        # Using a small deterministic placeholder keeps tests and integration paths simple.
        png = _tiny_png()

    duration_ms = int((time.perf_counter() - start) * 1000)
    observe_histogram("renderer.render_ms", duration_ms)
    _cache[key] = png
    return png


def _tiny_png() -> bytes:
    """Return a valid, minimal PNG (1x1 transparent)."""
    # Precomputed 1x1 transparent PNG bytes
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"  # noqa: E501
