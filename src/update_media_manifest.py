"""Rebuild the public media path index after importing website assets."""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path


def build_index(root: Path, prune_missing: bool = False) -> str:
    media = root / "media"
    index = media / "README.md"
    paths: set[str] = set()
    # A workstation may have only part of the archived media. Preserve registered
    # URLs unless the caller explicitly says this is a complete synchronized copy.
    if index.exists() and not prune_missing:
        paths.update(re.findall(r"^- `([^`]+)`$", index.read_text(encoding="utf-8-sig"), re.M))
    for path in media.rglob("*"):
        if not path.is_file() or path == index:
            continue
        paths.add(path.relative_to(root).as_posix())
    grouped: dict[str, list[str]] = defaultdict(list)
    canonical = {p.replace("media/pages/projects/personal-blog/", "media/pages/projects/web/", 1) for p in paths}
    for relative in canonical:
        grouped[relative.rsplit("/", 1)[0]].append(relative)
    count = sum(map(len, grouped.values()))
    lines = [
        "# 媒体文件路径清单",
        "",
        f"共 {count} 个文件，按目录分组。路径相对于项目根目录；网站访问路径在前面加 `/`。",
        "",
    ]
    for directory in sorted(grouped, key=str.casefold):
        paths = sorted(grouped[directory], key=str.casefold)
        lines.extend([f"## `{directory}/`（{len(paths)} 个）", ""])
        lines.extend(f"- `{path}`" for path in paths)
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--prune-missing", action="store_true", help="Remove missing entries; use only with a complete media copy.")
    parser.add_argument("--check", action="store_true", help="Check the index without writing it.")
    args = parser.parse_args()
    root = args.root.resolve()
    content = build_index(root, args.prune_missing)
    destination = root / "media" / "README.md"
    if args.check:
        if not destination.exists() or destination.read_text(encoding="utf-8") != content:
            raise SystemExit("Media index is out of date; run python -m src.update_media_manifest.")
        print("Media index is up to date, including registered archive entries.")
    else:
        destination.write_text(content, encoding="utf-8")
        print(f"Updated {destination}")


if __name__ == "__main__":
    main()
