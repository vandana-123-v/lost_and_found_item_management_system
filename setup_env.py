"""Initialize a local .env without overwriting existing configuration."""

from pathlib import Path
import secrets

root = Path(__file__).resolve().parent
target = root / ".env"
if target.exists():
    raise SystemExit(
        ".env already exists. Edit it manually; no settings were overwritten."
    )
content = (root / ".env.example").read_text(encoding="utf-8")
content = content.replace(
    "replace-with-a-long-random-secret", secrets.token_urlsafe(64)
)
target.write_text(content, encoding="utf-8")
print(
    "Created .env with a unique secret. Set your MySQL credentials before running migrations."
)
