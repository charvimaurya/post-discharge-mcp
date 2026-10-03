"""Create a live Titan embedding and print its length and first five values."""

from pathlib import Path
import sys

# Direct execution puts this script folder on the import path; include project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.embeddings import (
    embed_text,
)


embedding = embed_text(
    "Do not drive for seven days."
)

print(
    "Embedding length:",
    len(embedding),
)

print(
    "First five values:",
    embedding[:5],
)
