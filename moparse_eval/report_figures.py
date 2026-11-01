"""Shared font preparation and colors for the current expected-only report."""

from __future__ import annotations

from pathlib import Path

PIPELINE_COLORS = {
    "P01": "#4477AA", "P02": "#66AADD", "P03": "#228833", "P04": "#66AA55",
    "P05": "#CC6677", "P06": "#AA7733", "P07": "#AA4499", "P08": "#332288",
}


def _register_cjk_fonts(directory: Path) -> None:
    """Expose the SC face in system TTC collections to Matplotlib.

    Matplotlib may only discover the first face (JP) in a TTC.  Exporting the
    installed SC face is font preparation, not processing any report inputs.
    The files also make the selected Chinese fonts portable with the figures.
    """
    from fontTools.ttLib import TTCollection
    from matplotlib import font_manager

    font_directory = directory / "fonts"
    for style in ("Regular", "Bold"):
        output = font_directory / f"NotoSansCJKSC-{style}.otf"
        if output.is_file():
            font_manager.fontManager.addfont(str(output))
            continue
        sources = sorted(path for path in font_manager.findSystemFonts()
                         if Path(path).name == f"NotoSansCJK-{style}.ttc")
        if not sources:
            try:
                font_manager.findfont(font_manager.FontProperties(family="Noto Sans CJK SC",
                                                                  weight="bold" if style == "Bold" else "normal"),
                                      fallback_to_default=False)
            except ValueError as error:
                raise RuntimeError("Noto Sans CJK SC is required to export readable Chinese charts") from error
            continue
        with TTCollection(sources[0], lazy=True) as collection:
            candidates = [font for font in collection.fonts
                          if font["name"].getBestFamilyName() == "Noto Sans CJK SC"]
            if len(candidates) != 1:
                raise RuntimeError(f"Cannot select Noto Sans CJK SC face in {sources[0]}")
            font_directory.mkdir(parents=True, exist_ok=True)
            candidates[0].recalcTimestamp = False
            candidates[0].save(output)
        font_manager.fontManager.addfont(str(output))
    license_path = Path("/usr/share/doc/fonts-noto-cjk/copyright")
    if font_directory.is_dir() and license_path.is_file():
        (font_directory / "COPYRIGHT.txt").write_text(license_path.read_text(), encoding="utf-8")
