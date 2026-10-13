# AfterWard resource migration configuration

These files record the completed resource-name migration. Active deployment settings have also been updated. See [the migration document](../../docs/aws-name-migration.md) for live findings, the resolved permission blocker, execution order, and rollback.

`resource-names.json` defines the names. The S3 and SQS settings were derived from the live snapshot on 13 October 2026, preserving AWS-managed encryption. `vector-index.json` preserves the source index dimensions and metadata settings. The IAM policy files are proposed repository policies: inspect and merge the actual live permissions before applying them. In particular, extend the existing MCP role's access during transition instead of replacing its permissions and removing rollback access.

For a future recreation, do not configure `s3-notifications.json` until historical objects have been copied. Create the dead-letter queue before applying the processing queue attributes. The missing permissions have been granted and live ECS settings have been saved. Review those settings before applying replacement configuration.
