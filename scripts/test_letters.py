"""The synthetic letter that helper scripts use by default."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEST_LETTER = PROJECT_ROOT / "test_data" / "letter1_margaret_knee_replacement_SYNTHETIC_v3.pdf"
