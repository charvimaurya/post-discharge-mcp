# Testing

Run from the project root with the virtual environment active.

```bash
pytest -v
pytest tests/ingestion/ -v
pytest tests/database/ -v
pytest tests/rag/ -v
pytest tests/aws/ -v
```

Default pytest discovery is restricted to tests/ and excludes integration tests.
To deliberately run live AWS checks:

```bash
pytest -v -m integration
```

Integration tests may change patient state or consume queue messages. Manual
scripts can also make billable AWS calls and write data. Run only the intended check.

## Manual checks

```bash
# Local PDF extraction and chunking
python -m scripts.ingestion.test_extraction
python -m scripts.rag.test_real_chunking

# Bedrock structured extraction
python -m scripts.ingestion.test_phase3
python -m scripts.ingestion.test_phase3_image

# Embeddings, indexing, retrieval, patient isolation
python -m scripts.rag.test_embedding
python -m scripts.rag.test_real_vector_indexing
python -m scripts.rag.test_rag_search
python -m scripts.rag.test_patient_isolation

# Full asynchronous S3 -> SQS -> Lambda -> database flow
python -m scripts.ingestion.test_full_ingestion
```

A passing mock-based test does not prove cloud permissions, deployed code, or
medical extraction accuracy. Compare extraction output against the synthetic
source document. The sample PDF is test_data/doc_001.pdf; its startxref warnings
do not prevent the current two-page extraction.

See ../scripts/README.md for script groups and ../tests/README.md for test groups.
