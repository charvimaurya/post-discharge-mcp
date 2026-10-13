# Afterward

Afterward is a post-discharge companion with document ingestion and structured recovery plans.

Active AWS storage, queues, and document processing use AfterWard resource names.
The original resources remain available for rollback; see the
[migration record](docs/aws-name-migration.md).

Use `DOCUMENT_BUCKET` for the S3 bucket setting. `AFTERWARD_BUCKET` is also
accepted. Bucket values must refer to an existing bucket.
See [deployment instructions](deployment/README.md) for building
`build/afterward_document_processor.zip` and the updated configuration paths.

- `app/mcp/`: authenticated MCP server and recovery-plan tools
- `app/`: ingestion, RAG, AWS services, and database operations
- `lambdas/`: Lambda entry points
- `deployment/`: deployment configuration and dependency pins
- `build/`: generated packages (excluded from Git)
- `tests/`: project tests

## Running the MCP server locally (fresh clone)

`.venv/` and `.env` are not in Git, so every new machine has to create them.
Requires Python 3.11 and AWS credentials with access to the project's
DynamoDB tables, Bedrock and S3 Vectors.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # fill in the blank values (ask a teammate)
aws configure               # or: export AWS_PROFILE=<your profile>

uvicorn app.mcp.http_server:app --port 8000
```

In a second terminal, check it works:

```bash
source .venv/bin/activate
MCP_URL=http://127.0.0.1:8000/mcp MCP_TEST_TOKEN=afterward-local-dev-token \
  python scripts/test_mcp_http.py
```

## Documentation

- [Complete repository guide: setup, file map, workflow, and testing order](docs/REPOSITORY_GUIDE.md)
- [Architecture](docs/architecture.md)
- [Testing](docs/testing.md)
- [AWS setup and troubleshooting](docs/aws-setup.md)
- [AWS integrations](docs/aws-integrations.md)
- [Deployment](deployment/README.md)
