"""Normalize shell scripts to LF (fixes Docker exec on Linux from Windows checkouts)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    ROOT / "docker" / "entrypoint.sh",
]


def to_lf(path: Path) -> None:
    raw = path.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    path.write_bytes(text.encode("utf-8"))
    if b"\r" in path.read_bytes():
        raise SystemExit(f"{path}: still contains CR bytes")
    print(f"LF OK: {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


def main() -> None:
    for p in SCRIPTS:
        if not p.is_file():
            raise SystemExit(f"Missing: {p}")
        to_lf(p)


if __name__ == "__main__":
    main()
