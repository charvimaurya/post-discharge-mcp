# AfterWard bridge deployment (prepared, not deployed)

Read-only AWS inventory on 17 October 2026 found one London ECS cluster
(`afterward-cluster`) with one service (`afterward-mcp-service`). It runs the
MCP task on port 8000. Its internet-facing ALB has HTTP port 80, target port
8000 and `/health`. No bridge service or target group was found in that
account/region. Other regions or non-ECS hosting were not inventoried.

The existing root `Dockerfile` and `ecs-task-definition.json` remain MCP-only.
`Dockerfile.bridge` and `template.yaml` add a separate bridge service and ALB;
they do not rename, deploy or modify any existing AWS resource by themselves.

## Runtime contract

- Listen on 8002. `GET`/`HEAD /bridge/health` is public liveness, returns no
  credentials/configuration, and does not call AWS. It does not certify model
  or database readiness.
- Every other HTTP request requires exactly one `X-Bridge-Key` header matching
  `BRIDGE_KEY` using constant-time comparison. Missing/blank configuration
  returns 503; invalid/missing caller credentials return 401. In production
  or ECS, a key shorter than 32 characters also fails closed.
- ECS injects `BRIDGE_KEY` from a dedicated Secrets Manager secret using the
  execution role. The application task role reads only the MCP token secret
  at runtime via `MCP_AUTH_TOKEN_SECRET_ARN`; a plain local token cannot
  override it in production. The secret value is cached until process restart.
- `CLOCK_MODE=production`, `LOCAL_REMINDER_LOOP=0`; the code suppresses the loop
  in ECS even if the loop variable is accidentally enabled. The existing
  scheduled reminder Lambda remains responsible for cloud reminders.
- The container runs as UID 10001 with a read-only root filesystem. One worker
  and one task are deliberate: sessions/crisis flags remain process-local.
  Replacement loses this state. Deployment stops the old task before starting
  the new one (brief downtime), avoiding simultaneous independent session stores.
  Durable identity-bound sessions are required before scaling or general use.
- The bridge role can read/update only the demo patient's recovery row, query/
  batch-write its history, invoke one selected agent model, and read one MCP
  secret. It has no S3, IAM, secret-write or direct vector permissions. MCP
  retains responsibility for its own tool permissions. DynamoDB BatchWriteItem
  is required by the existing history-clear implementation and permits puts
  as well as deletes; its scope is restricted to the demo patient's partition.
- HTTPS terminates on a new ALB. Tasks are private, with no public IP and inbound
  8002 allowed only from the ALB security group. ALB-to-task traffic is HTTP
  inside the VPC; frontend-to-ALB is TLS. Egress is HTTPS for AWS and MCP.

## Required operator inputs

Use two public ALB subnets and private task subnets with NAT access (including
the public MCP endpoint) or a reviewed private routing alternative. Supply an
existing validated regional ACM certificate and configure its hostname in DNS
to point at the new ALB. An ALB DNS name does not match your ACM certificate.
Set `AllowedIngressCidr` to the trusted frontend's egress range. Hosted frontends
without fixed egress/VPC access need a networking decision before deployment;
do not silently open the CIDR to all traffic.

Use distinct local/cloud bridge keys. Supply a random cloud key of at least
32 characters stored as a plain SecretString, not a JSON object. Never use
`NEXT_PUBLIC_BRIDGE_KEY`, commit keys, put them in build args or expose them in
command output. An optional `SecretKmsKeyArn` grants narrowly conditioned
Decrypt when both secrets use the same customer-managed key; its key policy
must also authorize the relevant roles. Leave it blank for AWS-managed keys.

The operator deploying the template needs CloudFormation/IAM/ECS/ELB/EC2/Logs
permissions and iam:PassRole, independent of the restricted application roles.
The current audit identity was denied cloudformation:ValidateTemplate.

## Commands for review — run AWS writes only after deployment approval

From the repository root, fill in existing network/certificate/secret values.
These commands were **not** executed against AWS during implementation.

```bash
export AWS_REGION=eu-west-2
export AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
export BRIDGE_CLUSTER_ARN="arn:aws:ecs:${AWS_REGION}:${AWS_ACCOUNT_ID}:cluster/afterward-cluster"
export BRIDGE_VPC_ID=vpc-REPLACE
export BRIDGE_PUBLIC_SUBNETS=subnet-REPLACE1,subnet-REPLACE2
export BRIDGE_PRIVATE_SUBNETS=subnet-REPLACE3,subnet-REPLACE4
export BRIDGE_FRONTEND_CIDR=REPLACE_WITH_TRUSTED_EGRESS_CIDR
export BRIDGE_CERTIFICATE_ARN=arn:aws:acm:eu-west-2:REPLACE:certificate/REPLACE
export BRIDGE_KEY_SECRET_ARN=arn:aws:secretsmanager:eu-west-2:REPLACE:secret:REPLACE
export MCP_TOKEN_SECRET_ARN=arn:aws:secretsmanager:eu-west-2:REPLACE:secret:REPLACE
export BRIDGE_MCP_URL=https://dakpc9juquqks.cloudfront.net/mcp
export BRIDGE_IMAGE_TAG="$(git rev-parse --short HEAD)-bridge"
export BRIDGE_ECR="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/afterward-bridge"

# Read-only AWS template validation; requires permission.
aws cloudformation validate-template --template-body file://deployment/bridge/template.yaml

# New repository only if it does not already exist. This creates an AWS resource.
aws ecr create-repository --repository-name afterward-bridge \
  --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true

docker build --platform linux/amd64 -f Dockerfile.bridge -t "${BRIDGE_ECR}:${BRIDGE_IMAGE_TAG}" .
aws ecr get-login-password | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker push "${BRIDGE_ECR}:${BRIDGE_IMAGE_TAG}"
export BRIDGE_IMAGE_DIGEST="$(aws ecr describe-images --repository-name afterward-bridge --image-ids imageTag="${BRIDGE_IMAGE_TAG}" --query 'imageDetails[0].imageDigest' --output text)"

# This command creates/updates the stack and service. Requires explicit approval.
aws cloudformation deploy --stack-name afterward-bridge \
  --template-file deployment/bridge/template.yaml --capabilities CAPABILITY_IAM \
  --parameter-overrides \
  ClusterArn="$BRIDGE_CLUSTER_ARN" VpcId="$BRIDGE_VPC_ID" \
  PublicSubnetIds="$BRIDGE_PUBLIC_SUBNETS" PrivateSubnetIds="$BRIDGE_PRIVATE_SUBNETS" \
  AllowedIngressCidr="$BRIDGE_FRONTEND_CIDR" CertificateArn="$BRIDGE_CERTIFICATE_ARN" \
  ImageUri="${BRIDGE_ECR}@${BRIDGE_IMAGE_DIGEST}" \
  BridgeKeySecretArn="$BRIDGE_KEY_SECRET_ARN" McpTokenSecretArn="$MCP_TOKEN_SECRET_ARN" \
  McpUrl="$BRIDGE_MCP_URL"

aws cloudformation describe-stacks --stack-name afterward-bridge --query 'Stacks[0].Outputs'
export BRIDGE_SERVICE="$(aws cloudformation describe-stacks --stack-name afterward-bridge --query 'Stacks[0].Outputs[?OutputKey==`ServiceName`].OutputValue | [0]' --output text)"
aws ecs wait services-stable --cluster "$BRIDGE_CLUSTER_ARN" --services "$BRIDGE_SERVICE"
```

Defaults select the named Haiku inference profile and its matching foundation
model. Override **both** `AgentModelId` and `AgentFoundationModelId` together if
using another model. Cross-region foundation-model permissions are restricted
to that model ID. Bedrock model access and organization policies must permit it.
The MCP origin defaults to the existing server's localhost origin; changing it
requires matching the MCP allowed-origin configuration.

After DNS is configured, set server-only `AGENT_API_URL=https://<certificate-hostname>`
and `BRIDGE_KEY_SECRET_ARN` on Amplify. Its SSR compute role reads the dedicated
bridge key secret at runtime; see [Amplify configuration](../amplify/README.md). Local
development now also requires matching nonempty `BRIDGE_KEY` settings in root
`.env` and `web/.env.local`; do not reuse the cloud key. Never send browser-provided
authentication headers onward. API routes construct service headers themselves.

## Local validation and post-deployment checks

```bash
AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing AWS_EC2_METADATA_DISABLED=true \
  .venv-check/bin/python -m pytest -q -p no:cacheprovider
cd web
npm test
npm run typecheck
```

Use your normal environment on a fresh clone instead of the existing local
`.venv-check` path. The full Python suite includes raw unauthenticated requests,
invalid/duplicate keys, missing production keys, constant-time comparison,
public health, secret-only cloud MCP credentials and cloud loop suppression.

After approved deployment, from an allowed network, public health should return
200 and an unauthenticated GET `/today` should return 401. Supply the key through
a protected header file or secret-aware test harness for authenticated smoke
tests; do not place it in command arguments, terminal output or shell history.
Authenticated `/today` should work; no upload/chat/reset is necessary for this
initial read check. Do not use `/documents/uploaded` as a health check.

## Remaining publication blockers

This service credential authenticates the frontend server, not visitors. Next.js
routes still need visitor authentication, quotas and isolated demo state before
public exposure. Upload size/page limits and document-safe reset are separate
work. The existing MCP CloudFront configuration has an HTTP origin leg. Live IAM
roles were found to retain broad managed policies; this new stack does not alter
them. Do not describe the entire application as production-ready because the
bridge container/configuration is prepared.

AWS references: [ECS service](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-service.html),
[ALB HTTPS listener](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-elasticloadbalancingv2-listener.html),
[Fargate networking](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-networking.html).
