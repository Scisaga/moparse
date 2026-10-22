#!/usr/bin/env python3
"""Export MO-Parse logo, favicon and self-contained workspace scenes."""

from __future__ import annotations

import io
from pathlib import Path
from xml.etree import ElementTree as ET

import cairosvg
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
LOGO_MASTER = ROOT / "assets" / "moparse-logo-3d-master.png"
FAVICON_MASTER = ROOT / "assets" / "moparse-favicon-master.png"
ILLUSTRATION_MASTER = ROOT / "assets" / "illustrations" / "document-terminal-outline.svg"
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


def terminal_geometry(kind: str) -> str:
    """Keep the chassis shared while giving the two main scenes distinct poses."""
    poses = {
        "input": {
            "terminal-paper": '''<path d="M108 96V50q0-8 8-8h80l16 16v38zM196 42v16h16"/><path d="M126 63h48m-48 16h66"/>''',
            "terminal-face": '''<circle cx="120" cy="190" r="3"/><circle cx="188" cy="190" r="3"/><path d="M143 208q11 9 22 0"/>''',
            "terminal-arms": '''<path d="M64 205c-13 7-14 25-23 35s-18 11-26 7M15 247q-5-6-11-3m11 3q-6 5-12 2M256 205c13 11 21 28 25 48M279 253c8-3 15 3 16 10s-4 14-10 14c-4 0-7-3-7-7"/>''',
        },
        "markdown": {
            "terminal-paper": '''<path d="M108 96V16q0-8 8-8h74l22 22v66zM190 8v22h22"/><circle cx="124" cy="38" r="2"/><circle cx="136" cy="57" r="2"/><circle cx="136" cy="76" r="2"/><path d="M135 38h52m-40 19h40m-40 19h29"/>''',
            "terminal-face": '''<circle cx="130" cy="190" r="3"/><circle cx="198" cy="190" r="3"/><path d="M150 207q12 10 24 0"/>''',
            "terminal-arms": '''<path d="M64 205c-13 11-21 28-25 48M41 253c-8-3-15 3-16 10s4 14 10 14c4 0 7-3 7-7M256 207c22-4 29-21 29-37"/><ellipse cx="285" cy="158" rx="9" ry="12"/>''',
        },
    }
    master = ET.fromstring(ILLUSTRATION_MASTER.read_bytes())
    selected = poses.get(kind, {})
    geometry = []
    for group in master:
        if not group.tag.endswith("g"):
            continue
        identity = group.get("id", "")
        if identity in selected:
            geometry.append(f'<g id="{identity}">{selected[identity]}</g>')
        else:
            geometry.append(ET.tostring(group, encoding="unicode"))
    return "".join(geometry)


def workspace_scene(kind: str) -> bytes:
    """Compose transparent line art with no raster, filled area or shadow."""
    titles = {
        "input": "A paper document ready for MO-Parse",
        "markdown": "MO-Parse organizes a document into readable structure",
        "text": "MO-Parse preserves readable document text",
        "pages": "MO-Parse preserves source pages and their structure",
        "loading": "MO-Parse is processing a document",
        "info": "Document information is available in MO-Parse",
        "error": "A document in MO-Parse needs attention",
    }
    terminal_x = 62 if kind in {"markdown", "pages"} else 252
    paper_x = 422 if kind in {"markdown", "pages"} else 80
    details = {
        "input": '<path d="M20 50h55m-55 22h90m-90 20h90m-90 20h60"/><rect x="20" y="138" width="22" height="18" rx="2"/><path d="M56 147h54"/>',
        "markdown": '<path d="M20 48h57m-57 20h90m-74 26h74m-62 24h62m-62 24h47"/><circle cx="23" cy="94" r="3"/><circle cx="35" cy="118" r="3"/><circle cx="35" cy="142" r="3"/>',
        "text": '<path d="M20 48h57m-57 22h90m-90 20h90m-90 20h68m-68 28h90m-90 20h63"/>',
        "pages": '<rect x="20" y="48" width="31" height="28" rx="2"/><path d="M64 50h46m-46 20h46m-90 28h90"/><rect x="20" y="118" width="90" height="38" rx="2"/><path d="M20 137h90m-58-19v38"/>',
        "info": '<circle cx="66" cy="72" r="24"/><circle cx="66" cy="61" r="2"/><path d="M66 73v14M20 124h90m-90 22h90m-90 20h62"/>',
        "error": '<path d="m66 44 30 28-30 28-30-28zM66 58v17"/><circle cx="66" cy="86" r="2"/><path d="M20 126h90m-90 22h62"/>',
    }
    if kind == "loading":
        terminal_x = 160
        document = '<g stroke="#a4b2bb"><circle cx="296" cy="457" r="5"/><circle cx="320" cy="457" r="5"/><circle cx="344" cy="457" r="5"/></g>'
    else:
        stack = (
            '<path d="M142 36v134q0 20-20 20H22m130-144v134q0 20-20 20H32"/>'
            if kind == "pages" else ""
        )
        connector = (
            '<path d="M362 331h106q10 0 10-10v-12" stroke-dasharray="6 9"/><path d="m470 318 8-9 8 9"/>'
            if kind in {"markdown", "pages"} else
            '<path d="M146 309v12q0 10 10 10h105" stroke-dasharray="6 9"/><path d="m252 323 9 8-9 8"/>'
        )
        if kind == "input":
            connector = '<path d="M146 309v8q0 14 14 14h64q13 0 21-8" stroke-dasharray="6 9"/><path d="m234 324 11-1-2 11"/>'
        document = f"""
  <g stroke="#adbac2" stroke-width="3">{connector}</g>
  <g transform="translate({paper_x} 132)" stroke="#9caeb8" stroke-width="3.2">
    {stack}
    <path d="M12 0h90l28 28v140q0 12-12 12H12q-12 0-12-12V12Q0 0 12 0zM102 0v28h28"/>
    {details[kind]}
  </g>"""
    geometry = terminal_geometry(kind)
    if kind == "markdown":
        geometry = f'<g transform="rotate(-5 160 306)">{geometry}</g>'
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="512" viewBox="0 0 640 512" role="img" aria-labelledby="title" fill="none" stroke="#8b9fa9" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
  <title id="title">{titles[kind]}</title>
{document}
  <g transform="translate({terminal_x} 68)" data-pose="{kind if kind in {'input', 'markdown'} else 'neutral'}">{geometry}</g>
</svg>
""".encode()


def main() -> int:
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
        scene = workspace_scene(kind)
        directory = ROOT / "frontend" / "public" / "illustrations"
        write(directory / f"workspace-{kind}.svg", scene)
        write(
            directory / f"workspace-{kind}.png",
            cairosvg.svg2png(bytestring=scene, output_width=640, output_height=512),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
