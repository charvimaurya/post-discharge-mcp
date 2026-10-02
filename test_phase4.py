"""Run the Phase 4 unit tests using the original script command."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).parent / "tests" / "test_phase4.py"),
        run_name="__main__",
    )
