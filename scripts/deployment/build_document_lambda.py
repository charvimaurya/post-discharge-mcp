"""Build a Python 3.11 x86_64 Lambda ZIP using Linux-compatible wheels."""

import subprocess
import sys
from tempfile import TemporaryDirectory
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("app", "lambdas")


def build(staging: Path):
    for dependency in ("pypdf", "dotenv", "boto3", "botocore", "jsonschema", "rpds", "discharge_letter_check"):
        if not (staging / dependency / "__init__.py").is_file():
            raise SystemExit(f"Missing staged dependency: {dependency} in {staging}")

    if not list((staging / "rpds").glob("rpds*.so")):
        raise SystemExit("Missing Linux rpds native extension")

    entries = {}
    for path in staging.rglob("*"):
        relative = path.relative_to(staging)
        if relative.parts[0] not in PACKAGES:
            entries[relative.as_posix()] = path
    for package in PACKAGES:
        for path in (ROOT / package).rglob("*"):
            entries[path.relative_to(ROOT).as_posix()] = path

    required = ("app/models/__init__.py", "app/models/recovery_model.py",
                "lambdas/document_processor/handler.py", "app/ingestion/document_service.py",
                "lambdas/reminder_checker/handler.py",
                "discharge_letter_check/models.py", "discharge_letter_check/validator.py",
                "discharge_letter_check/document_validation.py",
                "discharge_letter_check/schema.py",
                "discharge_letter_check/schemas/discharge-extraction.schema.json")
    for name in required:
        if name not in entries or not entries[name].is_file():
            raise SystemExit(f"Missing required Lambda source: {name}")

    output = ROOT / "build" / "afterward_document_processor.zip"
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, path in sorted(entries.items()):
            if (not path.is_file() or "__pycache__" in path.parts
                    or path.suffix in {".pyc", ".pyo"}
                    or any(part.startswith(".") for part in Path(name).parts)):
                continue
            archive.write(path, name)
    print(f"Built {output} ({output.stat().st_size} bytes)")


def main():
    (ROOT / "build").mkdir(exist_ok=True)
    # Fresh staging avoids mixing macOS extensions or stale dependencies into Lambda.
    with TemporaryDirectory(prefix="lambda-linux-", dir=ROOT / "build") as directory:
        staging = Path(directory)
        subprocess.run([
            sys.executable, "-m", "pip", "install",
            "--platform", "manylinux2014_x86_64",
            "--implementation", "cp", "--python-version", "3.11",
            "--abi", "cp311", "--only-binary=:all:",
            "--target", str(staging),
            "-r", str(ROOT / "deployment" / "requirements-lambda.txt"),
        ], check=True)
        build(staging)


if __name__ == "__main__":
    main()
