# discharge-letter-check integration review

Reviewed 17 October 2026. No package files, dependency pins or schema versions were
changed. Optional v0.2.0 adoption is a separate change, not part of this review.

## Versions, CI and access

AfterWard pins v0.1.0 in [requirements.txt](../requirements.txt) and
[Lambda requirements](../deployment/requirements-lambda.txt).
Its installed distribution reports 0.1.0. The pinned GitHub archive returned HTTP
200 with a ZIP signature. This confirms the download, not a full fresh application
installation or AWS setup.

The separate package clone is on main, clean, at
`7ac243ab226569cc8ffd2f3012d632c6ca77f38a`, with project version 0.2.0.
The public GitHub repository and both v0.1.0/v0.2.0 tags were confirmed through
anonymous requests. The package changelog still labels 0.2.0 unreleased despite
the tag; release-status wording should be reconciled separately.

The requested CI and badge already exist, locally and on GitHub:

- [Workflow](https://github.com/charvimaurya/discharge-letter-check/blob/7ac243ab226569cc8ffd2f3012d632c6ca77f38a/.github/workflows/tests.yml): push/PR matrix for Python 3.11, 3.12 and 3.13, installing `.[test]` and running pytest.
- [README badge](https://github.com/charvimaurya/discharge-letter-check/blob/7ac243ab226569cc8ffd2f3012d632c6ca77f38a/README.md): links to the tests workflow.
- [Observed run 38950242737](https://github.com/charvimaurya/discharge-letter-check/actions/runs/38950242737): completed successfully at that same SHA; `test (3.11)`, `test (3.12)` and `test (3.13)` each reported success through the GitHub API.

No workflow was added, triggered or changed. Python 3.12/3.13 were verified through
those CI job results, not local interpreters. The package's local Python 3.11.15
suite passed **149 tests**, and `examples/check_sample.py` matched its saved output.
The package matrix is not evidence that the entire AfterWard app supports all
three Python versions.

## Integration boundary

| Responsibility | Confirmed implementation |
| --- | --- |
| Canonical extraction schema | [bedrock.py](../app/ingestion/bedrock.py) calls package `load_schema()` and applies JSON Schema validation. |
| Document and recovery validators | [document_validation.py](../app/ingestion/document_validation.py) and [validator.py](../app/ingestion/validator.py) re-export package APIs. |
| Shared instruction dataclasses | [recovery_model.py](../app/models/recovery_model.py) imports package types but owns a separate application RecoveryState. |
| Extraction and persistence | AfterWard owns PDF/image processing, model calls, normalization, patient state, RAG, MCP and reminders. The package does not perform these operations. |
| Source-dependent checks | [pipeline.py](../app/ingestion/pipeline.py) passes document text to the validator for diet/follow-on checks. This is not a universal semantic proof of all medication instructions. |
| Single schema | The local copy was removed on 18 October 2026. Extraction ([bedrock.py](../app/ingestion/bedrock.py)) and the tests load the schema only through `discharge_letter_check.schema.load_schema()`; [test_package_integration.py](../tests/ingestion/test_package_integration.py) fails if a local copy reappears. |

The current v0.1.0 [integration tests](../tests/ingestion/test_package_integration.py)
passed **4/4**.

## Optional v0.2.0: upgrade blocked, kept separate

A process-local `PYTHONPATH` override selected the sibling v0.2.0 source without
installing it or changing the application's environment or pins. The same four
integration checks returned **1 passed, 3 failed**:

1. Package RecoveryState adds `allergies`; AfterWard's constructor no longer matches.
2. v0.2.0 `validate_allergies` accesses `state.allergies`, which the application
   state lacks, raising AttributeError during normal validation.
3. The extraction schema differs from the checked local contract, including
   allergies and stricter HH:MM task clock-time validation.

Before an upgrade, add allergy state/normalization/persistence/display deliberately,
update the schema contract, test old records and deployment packaging, and review
medication safety independently. No optional schema or validator changes were made.

## Medication safety findings

These are synthetic local probes and code findings, not clinical validation.

| Priority | Finding and evidence | Required follow-up |
| --- | --- | --- |
| P0 before patient-facing use | [normalizer.py](../app/ingestion/normalizer.py) assigns every normalized medication `status="pending"`. A synthetic incoming stopped medication reproduced pending status. Runtime stopped-order filtering cannot recover a stop marker lost at ingestion. | Design explicit stop-order extraction and preservation, then test the entire ingestion-to-reminder path. Do not fix this by inventing stop dates. |
| P0 before unrestricted medication recording | The [saved final-model evaluation](agent-final-evaluation.json) has 13 passes and one failure: ambiguous “I took my medicine” recorded the remaining medicine without explicit naming. This evaluation was not rerun here. | Resolve the confirmation policy and rerun the failing scenario with full-dose/identity confirmation requirements. Unit-test success is not a resolution of this policy issue. |
| P1 | v0.1.0 package validator leaves a medicine with missing dose unflagged. That is its documented optional-field behavior, not a clinical completeness guarantee. | Gate dose-specific advice/actions on source evidence and explicit uncertainty policy; never treat an unflagged item as confirmed safe. |
| P1 | A synthetic `[?morning?]` value in `time_of_day` remained unflagged; `validate_medications` scans selected text fields but not that list. A direct whitespace-only name also remained unflagged. An uncertain dose control was flagged correctly. | Add a separate reviewed validation change for scheduling uncertainty and blank strings, with conservative downstream handling. |
| P1 upgrade blocker | v0.2.0 source is incompatible with the current application state and schema contract. | Keep v0.1.0 pinned until migration tests pass. Allergy support alone does not resolve dosing or stopped-order safety. |

No medication behavior was silently changed as part of documentation work.

## Checks run for this review

| Check | Actual result |
| --- | --- |
| AfterWard default Python suite | 878 passed, 10 deselected in 1.80s; live AWS integration tests excluded |
| AfterWard package integration with installed v0.1.0 | 4 passed in 0.11s |
| Optional v0.2.0 source compatibility probe | 1 passed, 3 failed in 0.13s; dependency pin and installation unchanged |
| Package source suite, local Python 3.11.15 | 149 passed in 0.21s |
| Package example | Matched checked-in sample_result.json |
| Package GitHub Actions, current SHA | Python 3.11, 3.12 and 3.13 jobs all success in run 38950242737 |
| Web tests | 73 passed, 0 failed, duration 209.765417 ms |
| Web typecheck | Passed |
| Web production build | Passed; Next.js warned that an unrelated parent-directory lockfile was ignored |
| AWS checks | Read-only service/encryption metadata only; no patient or secret values fetched |
| Application repository link | Anonymous GitHub API returned 404; visibility/access cannot be established |
| Package link/download | Public repository and workflow/badge confirmed; pinned v0.1.0 ZIP returned HTTP 200 |

To reproduce the optional compatibility probe from the AfterWard repository root
with the sibling package at the reviewed v0.2.0 revision:

```bash
PYTHONPATH='../discharge-letter-check/src' python -m pytest -q tests/ingestion/test_package_integration.py
```

Run the normal suite without that process-local override. Do not interpret the
failed optional probe as an approved dependency upgrade or mix it into the
passing v0.1.0 baseline. Local medication probes used only invented dataclasses;
they did not call AWS or persist records.
