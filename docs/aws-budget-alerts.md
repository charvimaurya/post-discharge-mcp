# AWS Budget alerts for the AfterWard demo

Instructions only: no budgets, notifications, actions or recipients were created.
Reviewed 17 October 2026 against [AWS cost-budget setup](https://docs.aws.amazon.com/cost-management/latest/userguide/create-cost-budget.html)
and [AWS Budgets limitations](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html).

1. Sign in to the payer/account responsible for AfterWard charges. Open Billing
   and Cost Management → Budgets → Create budget → Customize → Cost budget.
2. Name it `AfterWard-monthly-100`, select Monthly, Recurring and a fixed budget
   of **USD 100**. For a dedicated demo account, include all costs/services so
   untagged costs are covered. In a shared account, use a verified activated cost
   allocation tag, and also maintain an account-wide budget: a tag filter can miss
   untagged resources, tax, support or shared charges. Check the selected cost
   basis, credits/refunds and discounts against the intended spend policy.
3. Add an **ACTUAL** alert at **50% ($50)** and another ACTUAL alert at
   **100% ($100)**. Optionally add a FORECASTED 100% alert for earlier notice.
   The service's comparison operator can mean “greater than” the threshold;
   notifications are not guaranteed at an exact dollar boundary.
4. Add the owner's monitored email address. Complete any AWS recipient verification
   and, if using SNS, confirm the subscription and topic permissions. Review the
   summary and create only after approval. Record the budget owner and response
   runbook. Check notification/subscriber status in the console.
5. At $50, inspect Cost Explorer by service and usage type: Bedrock tokens,
   Amplify builds/SSR requests, ECS/Fargate, ALB, NAT/egress, S3 ingestion and
   storage, SQS/Lambda, DynamoDB transactions/polling, vector search and logs.
   Pause unneeded previews/builds; reduce public traffic through the approved
   access control. At $100, the owner decides whether to disable public demo
   access or stop approved resources. These are manual decisions; no automatic
   IAM-deny action or infrastructure shutdown is configured here.

Budgets are delayed alerts, **not spending caps**. Charges can exceed $100 before
an alert arrives. Do not rely on them for abuse prevention. Rate counters themselves
incur DynamoDB charges, including rejected transactions. Limit edge traffic, use
an access-controlled demo, set log retention and bound ECS scaling/concurrency.
The existing ECS/ALB and any NAT gateway can incur costs while the demo is idle.

Read-only verification after setup (not executed during this task):

```sh
aws budgets describe-budget --account-id <ACCOUNT_ID> --budget-name AfterWard-monthly-100
aws budgets describe-notifications-for-budget --account-id <ACCOUNT_ID> --budget-name AfterWard-monthly-100
```

Use `describe-subscribers-for-notification` for each returned notification to
verify the intended recipient. Never put AWS access keys in this repository,
Amplify browser settings, screenshots or the public report.
