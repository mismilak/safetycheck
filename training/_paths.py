from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def resolve(p: str | Path) -> Path:
    """Relative paths are normally given from the project root, but people often run scripts from inside training/."""
    p = Path(p).expanduser()
    if p.is_absolute() or p.exists():
        return p
    alt = ROOT / p
    return alt if alt.exists() else p
