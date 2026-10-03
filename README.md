# Afterward

Afterward is a post-discharge companion with document ingestion and structured recovery plans.

The project was previously called CareLoop. Existing AWS bucket, queue, Lambda,
and IAM identifiers retain their deployed names so current integrations continue
to work. The GitHub repository is https://github.com/charvimaurya/Afterward;
the local folder has not been renamed.

Use `DOCUMENT_BUCKET` for the S3 bucket setting. `AFTERWARD_BUCKET` is also
accepted, with `CARELOOP_BUCKET` retained as a legacy fallback. Bucket values
must refer to an existing bucket; changing the project name does not rename AWS
resources. See [deployment instructions](deployment/README.md) for building
`build/afterward_document_processor.zip` and the updated configuration paths.

- `mcp_server/`: MCP server Python package
- `app/`: ingestion, RAG, AWS services, and database operations
- `lambdas/`: Lambda entry points
- `deployment/`: deployment configuration and dependency pins
- `build/`: generated packages (excluded from Git)
- `tests/`: project tests

## Documentation

- [Architecture](docs/architecture.md)
- [Testing](docs/testing.md)
- [AWS setup and troubleshooting](docs/aws-setup.md)
- [Deployment](deployment/README.md)
