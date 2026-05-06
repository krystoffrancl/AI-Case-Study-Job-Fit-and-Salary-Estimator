from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent.parent / ".env")

import os

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]