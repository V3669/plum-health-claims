import os
from pathlib import Path

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
UPLOAD_DIR: Path = Path("uploads")
TRACES_DIR: Path = Path("traces")
DB_PATH: Path = Path("claims.db")
POLICY_FILE: Path = Path(os.environ.get("POLICY_FILE", "policy_terms.json"))
