# Automated tests

Run from the project root with the virtual environment active:

```bash
pytest -v
```

Tests are grouped by area:

- `ingestion/`: document processing, Lambda handler, normalization, validation,
  and source evidence.
- `database/`: RecoveryState operations, patient actions, and Event History.
- `rag/`: document chunking.
- `aws/`: SQS message parsing and notification checks.
- `test_model_config.py`: model selection and configuration validation.

To run one group:

```bash
pytest tests/ingestion/ -v
pytest tests/database/ -v
pytest tests/rag/ -v
pytest tests/aws/ -v
```

The default configuration excludes tests marked `integration`. To explicitly
run live AWS integration tests (which can modify data and consume messages):

```bash
pytest -v -m integration
```

Manual checks live under `scripts/` and are excluded from default discovery.
