"""Build the Lambda ZIP from current source and staged Python dependencies."""

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


ROOT = Path(__file__).resolve().parents[2]
PACKAGES = ("app", "models", "mcp_server", "lambdas")


def main():
    staging = ROOT / "build" / "lambda_package"
    for dependency in ("pypdf", "dotenv", "boto3", "botocore"):
        if not (staging / dependency / "__init__.py").is_file():
            raise SystemExit(f"Missing staged dependency: {dependency} in {staging}")

    entries = {}
    for path in staging.rglob("*"):
        relative = path.relative_to(staging)
        if relative.parts[0] not in PACKAGES:
            entries[relative.as_posix()] = path
    for package in PACKAGES:
        for path in (ROOT / package).rglob("*"):
            entries[path.relative_to(ROOT).as_posix()] = path

    required = ("models/__init__.py", "models/recovery_model.py",
                "lambdas/document_processor/handler.py", "app/ingestion/document_service.py")
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


if __name__ == "__main__":
    main()
