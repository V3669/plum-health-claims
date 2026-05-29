import os
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
UPLOAD_DIR: Path = Path("uploads")
TRACES_DIR: Path = Path("traces")
DB_PATH: Path = Path("claims.db")
POLICY_FILE: Path = Path(os.environ.get("POLICY_FILE", "policy_terms.json"))
