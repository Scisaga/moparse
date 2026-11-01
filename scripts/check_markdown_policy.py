"""Reject U+FF0F in maintained Markdown and documentation generator source.

Git's tracked and non-ignored new files define maintained inputs. Corpus
materials are permanently excluded, including when explicitly requested.
"""

from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = "\uff0f"
CORPUS_DIRECTORIES = frozenset({"pdf_sample", "pdf_sample_extra", "pdf_page_images", "datasets"})


def corpus_path(path: Path) -> bool:
    """Corpus review is visual only; never inspect these files mechanically."""
    parts = path.parts
    return any(part in CORPUS_DIRECTORIES for part in parts) or any(
        parts[index : index + 2] in {
            ("benchmark", "reports"), ("benchmark", "runs"), ("benchmark", "reference-decisions"),
        }
        for index in range(len(parts) - 1)
    )


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    column: int
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.message}"


def text_violations(text: str, label: str) -> list[Violation]:
    return [
        Violation(label, line_number, match.start() + 1, "U+FF0F is forbidden; use ASCII /")
        for line_number, line in enumerate(text.splitlines(), 1)
        for match in re.finditer(FORBIDDEN, line)
    ]


def assert_markdown_text(text: str, label: str = "generated Markdown") -> None:
    """Validate Markdown before writing it, including fenced examples and tables."""
    violations = text_violations(text, label)
    if violations:
        raise ValueError("\n".join(map(str, violations)))


def generator_source(path: Path) -> bool:
    """Include maintained documentation scripts in the authoring policy."""
    return path.suffix == ".py" and path.parts[0] == "scripts"


def maintained_paths(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = {Path(item.decode()) for item in result.stdout.split(b"\0") if item}
    return sorted(
        path
        for path in paths
        if not corpus_path(path)
        and (root / path).is_file()
        and (path.suffix.lower() in {".md", ".markdown"} or generator_source(path))
    )


def check_paths(paths: list[Path], root: Path) -> list[Violation]:
    violations = []
    for path in paths:
        absolute = (root / path).resolve()
        try:
            relative = absolute.relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise ValueError(f"checked path escapes repository: {path}") from exc
        if corpus_path(Path(relative)):
            continue
        violations.extend(text_violations(absolute.read_text(encoding="utf-8"), relative))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="explicit non-corpus files, including ignored outputs")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    paths = [path for path in (args.paths or maintained_paths(root)) if not corpus_path(path)]
    violations = check_paths(paths, root)
    for violation in violations:
        print(violation)
    print(f"Markdown policy: {len(paths)} files checked, {len(violations)} violations")
    return int(bool(violations))


if __name__ == "__main__":
    raise SystemExit(main())
