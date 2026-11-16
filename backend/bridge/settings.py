"""Settings from the environment and .env (placeholders live in .env.example; never commit .env)."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    env = path or ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class Settings:
    api_key: str | None
    model: str
    database_path: Path
    runtime_dir: Path

    @property
    def outputs_dir(self) -> Path:
        return self.runtime_dir / "outputs"

    @property
    def uploads_dir(self) -> Path:
        return self.runtime_dir / "uploads"


def get_settings() -> Settings:
    load_dotenv()
    db = ROOT / os.environ.get("DATABASE_PATH", "data/runtime/bridge.db")
    return Settings(
        api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        database_path=db,
        runtime_dir=db.parent,
    )
