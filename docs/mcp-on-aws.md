# Optional: run the demo against the MCP server on AWS

By default the demo uses a **local copy** of the MCP server, started by
`scripts/start-demo.ps1`. It runs today's code and reads and writes the same AWS
data (DynamoDB, S3 Vectors, Bedrock) as the cloud copy.

The **cloud copy** runs on Amazon ECS on Fargate, behind an Application Load
Balancer and Amazon CloudFront:

| Item | Value |
| --- | --- |
| MCP address | `https://dakpc9juquqks.cloudfront.net/mcp` |
| Cluster and service | `afterward-cluster` / `afterward-mcp-service` |
| Task definition family | `afterward-mcp` |
| Image repository (ECR) | `992617582533.dkr.ecr.eu-west-2.amazonaws.com/afterward-mcp` |
| Token | Secrets Manager secret `afterward/mcp/auth-token` |

The cloud copy runs the code from its **last deploy**. Update it (part 1) before
using it for a demo, so it has all nine tools.

## Part 1: push a new image and update the service (administrator)

Needs: Docker Desktop running, the AWS CLI, and permission to push to ECR and
update the ECS service. About 30 to 60 minutes. Run in PowerShell from the
repository root.

1. **Note the current image, for rollback.** In the AWS console, open
   **ECR > afterward-mcp** and write down the image digest (`sha256:...`) tagged
   `latest`.

2. **Sign Docker in to ECR:**

   ```powershell
   aws ecr get-login-password --region eu-west-2 | docker login --username AWS --password-stdin 992617582533.dkr.ecr.eu-west-2.amazonaws.com
   ```

   Ready when it prints `Login Succeeded`.

3. **Build the image from today's code:**

   ```powershell
   docker build -t afterward-mcp .
   ```

4. **Tag it with today's date and as `latest`, then push both:**

   ```powershell
   $repo = "992617582533.dkr.ecr.eu-west-2.amazonaws.com/afterward-mcp"
   $tag  = Get-Date -Format "yyyyMMdd-HHmm"
   docker tag afterward-mcp:latest "${repo}:$tag"
   docker tag afterward-mcp:latest "${repo}:latest"
   docker push "${repo}:$tag"
   docker push "${repo}:latest"
   ```

5. **Restart the service so it pulls the new image:**

   ```powershell
   aws ecs update-service --cluster afterward-cluster --service afterward-mcp-service --force-new-deployment --region eu-west-2
   aws ecs wait services-stable --cluster afterward-cluster --services afterward-mcp-service --region eu-west-2
   ```

   The wait returns when the new task is running and healthy (a few minutes).
   The CloudWatch alarm `afterward-mcp-no-healthy-targets` should stay **OK**.

6. **Check it.** Start the demo against the cloud copy (part 2) and ask
   "What does my week look like?". The Developer view should show the
   `get_week_summary` tool, which exists only in the newest code.

**If something goes wrong:** in ECR, tag the digest you noted in step 1 as
`latest` again, then repeat step 5.

## Part 2: start the demo against the cloud copy

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-demo.ps1 -CloudMcp -Reset
```

The script does not start a local MCP server. It points the bridge at the
CloudFront address and reads the token from Secrets Manager for that run only,
so your AWS login needs `secretsmanager:GetSecretValue` on
`afterward/mcp/auth-token`. Add `-Alexa` for the tunnel as usual.

**Two differences from the local copy:**

- `-Record` fixes the clock for the bridge only. The cloud MCP server's clock comes
  from the ECS task settings.
- The cloud server accepts requests from the origin `http://localhost:3000`
  (`MCP_ALLOWED_ORIGINS` in the task definition), which is what the bridge sends.
