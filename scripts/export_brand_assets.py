#!/usr/bin/env python3
"""Export MO-Parse logo, favicon and self-contained workspace scenes."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import cairosvg
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
LOGO_MASTER = ROOT / "assets" / "moparse-logo-3d-master.png"
FAVICON_MASTER = ROOT / "assets" / "moparse-favicon-master.png"
WORKSPACE_SCENES = ("input", "markdown", "text", "pages", "loading", "info", "error")


def png(master: Path, size: int, *, trim_transparency: bool = False) -> bytes:
    with Image.open(master) as source:
        source_rgba = source.convert("RGBA")
        if source_rgba.getextrema()[3][0] == 255:
            raise ValueError(f"{master.name} must have a transparent background")
        margin = 0
        if trim_transparency:
            content = source_rgba.getchannel("A").point(lambda alpha: 255 if alpha >= 128 else 0)
            bounds = content.getbbox()
            if bounds is None:
                raise ValueError(f"{master.name} has no visible content")
            left, top, right, bottom = bounds
            # Keep the original antialiasing just outside the visible-content bounds.
            source_rgba = source_rgba.crop(
                (
                    max(0, left - 4),
                    max(0, top - 4),
                    min(source_rgba.width, right + 4),
                    min(source_rgba.height, bottom + 4),
                )
            )
            margin = round(size * 0.03) if size > 16 else 0
        inner_size = size - 2 * margin
        resized = ImageOps.contain(
            source_rgba, (inner_size, inner_size), Image.Resampling.LANCZOS
        )
        canvas = Image.new("RGBA", (size, size))
        canvas.alpha_composite(resized, ((size - resized.width) // 2, (size - resized.height) // 2))
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()


def ico(png_images: dict[int, bytes]) -> bytes:
    frames = []
    for size in (16, 32, 48, 64):
        with Image.open(io.BytesIO(png_images[size])) as source:
            frames.append(source.copy())
    buffer = io.BytesIO()
    frames[-1].save(
        buffer,
        format="ICO",
        sizes=[frame.size for frame in frames],
        append_images=frames[:-1],
    )
    return buffer.getvalue()


def write(path: Path, content: bytes) -> None:
    if path.suffix == ".svg":
        content = (
            "\n".join(line.rstrip() for line in content.decode("utf-8").splitlines()) + "\n"
        ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def workspace_scene(logo_master: bytes, kind: str) -> bytes:
    """Keep the selected mascot unchanged inside self-contained document scenes."""
    titles = {
        "input": "A paper document ready for MO-Parse",
        "markdown": "MO-Parse organizes a document into readable structure",
        "text": "MO-Parse preserves readable document text",
        "pages": "MO-Parse preserves source pages and their structure",
        "loading": "MO-Parse is processing a document",
        "info": "Document information is available in MO-Parse",
        "error": "A document in MO-Parse needs attention",
    }
    title = titles[kind]
    logo_x = 32 if kind in {"markdown", "pages"} else 248
    document_x = 414 if kind in {"markdown", "pages"} else 88
    details = {
        "input": """
      <path d="M20 50h55m-55 20h92m-92 20h92m-92 20h64"/>
      <rect x="20" y="137" width="25" height="20" rx="3" fill="#d3e5f5" stroke="none"/>
      <path d="M58 147h54"/>""",
        "markdown": """
      <path d="M20 48h57m-57 19h92"/>
      <rect x="20" y="88" width="92" height="54" rx="3" fill="#e6f0fa" stroke="#649ac8"/>
      <path d="M20 106h92m-92 18h92m-62-36v54m31-54v54" stroke="#649ac8"/>
      <path d="M20 160h66"/>""",
        "text": """
      <path d="M20 48h57m-57 22h92m-92 18h92m-92 18h70m-70 28h92m-92 18h63"/>""",
        "pages": """
      <rect x="20" y="48" width="32" height="29" rx="3" fill="#d3e5f5" stroke="none"/>
      <path d="M65 51h47m-47 18h47m-92 28h92"/>
      <rect x="20" y="116" width="92" height="42" rx="3" fill="#e6f0fa" stroke="#649ac8"/>
      <path d="M20 137h92m-60-21v42" stroke="#649ac8"/>""",
        "info": """
      <circle cx="66" cy="73" r="26" fill="#e6f0fa" stroke="#649ac8"/>
      <circle cx="66" cy="61" r="2" fill="#649ac8" stroke="none"/>
      <path d="M66 73v14" stroke="#649ac8"/>
      <path d="M20 124h92m-92 20h92m-92 20h64"/>""",
        "error": """
      <path d="m66 44 32 28-32 28-32-28z" fill="#e6f0fa" stroke="#649ac8"/>
      <path d="M66 58v18" stroke="#649ac8"/>
      <circle cx="66" cy="86" r="2" fill="#649ac8" stroke="none"/>
      <path d="M20 126h92m-92 20h64"/>""",
    }
    if kind == "loading":
        logo_x = 140
        document = """
  <g fill="#649ac8">
    <circle cx="296" cy="460" r="6" opacity=".4"/>
    <circle cx="320" cy="460" r="6" opacity=".7"/>
    <circle cx="344" cy="460" r="6"/>
  </g>"""
    else:
        stack = """
    <rect x="14" y="14" width="132" height="180" rx="12" fill="#dcebf7" stroke="none"/>
    <rect x="7" y="7" width="132" height="180" rx="12" fill="#e6f0fa" stroke="none"/>
""" if kind == "pages" else ""
        if kind in {"markdown", "pages"}:
            connector = """
    <path d="M350 328h104q12 0 12-12v-14" stroke-dasharray="7 9"/>
    <path d="m454 314 12-12 12 12"/>"""
        else:
            connector = """
    <path d="M154 302v14q0 12 12 12h92" stroke-dasharray="7 9"/>
    <path d="m246 316 12 12-12 12"/>"""
        document = f"""
  <g fill="none" stroke="#649ac8" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
{connector}
  </g>
  <g transform="translate({document_x} 112)" stroke="#245266" stroke-width="3" stroke-linejoin="round">
{stack}
    <path d="M12 0h92l28 28v140q0 12-12 12H12q-12 0-12-12V12Q0 0 12 0z" fill="#f4f8fb"/>
    <path d="M104 0v28h28" fill="#d3e5f5"/>
    <g fill="none" stroke="#7a9eaa" stroke-width="3" stroke-linecap="round">
{details[kind]}
    </g>
  </g>"""
    emblem = base64.b64encode(logo_master).decode("ascii")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="512" viewBox="0 0 640 512" role="img" aria-labelledby="title">
  <title id="title">{title}</title>
  <ellipse cx="320" cy="441" rx="220" ry="18" fill="#b9d2e8" opacity=".32"/>
{document}
  <image x="{logo_x}" y="64" width="360" height="360" preserveAspectRatio="xMidYMid meet" href="data:image/png;base64,{emblem}"/>
</svg>
""".encode()


def main() -> int:
    logo_master = LOGO_MASTER.read_bytes()
    image_1024 = png(LOGO_MASTER, 1024)
    image_256 = png(LOGO_MASTER, 256)
    # The frontal small-size artwork has its own master, separate from the main logo.
    favicon_images = {
        size: png(FAVICON_MASTER, size, trim_transparency=True) for size in (16, 32, 48, 64, 180)
    }
    write(ROOT / "assets" / "moparse-logo-1024.png", image_1024)
    write(ROOT / "assets" / "moparse-logo-256.png", image_256)
    write(ROOT / "logo.png", image_1024)
    write(ROOT / "frontend" / "public" / "logo.png", image_256)
    favicon_ico = ico(favicon_images)
    for directory in (ROOT / "assets" / "icons", ROOT / "frontend" / "public"):
        write(directory / "favicon.png", favicon_images[64])
        for size in (16, 32, 48):
            write(directory / f"favicon-{size}.png", favicon_images[size])
        write(directory / "favicon.ico", favicon_ico)
        write(directory / "apple-touch-icon.png", favicon_images[180])
    for kind in WORKSPACE_SCENES:
        scene = workspace_scene(logo_master, kind)
        directory = ROOT / "frontend" / "public" / "illustrations"
        write(directory / f"workspace-{kind}.svg", scene)
        write(
            directory / f"workspace-{kind}.png",
            cairosvg.svg2png(bytestring=scene, output_width=640, output_height=512),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
