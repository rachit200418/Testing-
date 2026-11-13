# Terraform Infrastructure for Voice Assistant QA Platform

This module provisions the AWS infrastructure for the Voice Assistant QA Platform's nightly evaluation pipeline.

## Resources Created

| Resource | Purpose |
|----------|---------|
| S3 Bucket | Stores datasets, logs, reports, eval artifacts |
| IAM Role (Lambda) | Nightly evaluation Lambda execution role |
| IAM Role (GitHub Actions) | OIDC role for CI/CD pipeline |
| Lambda Function | Nightly evaluation runner |
| EventBridge Rule | Triggers Lambda nightly at 2 AM UTC |
| CloudWatch Dashboard | Monitoring dashboard |
| CloudWatch Alarms | Alerting on latency, errors, quality metrics |
| SNS Topic | Alert notifications (email + Slack) |

## Prerequisites

1. **Terraform 1.6+**
2. **AWS CLI** configured with admin permissions
3. **S3 bucket for Terraform state** (create manually first):
   ```bash
   aws s3 mb s3://voice-assistant-qa-terraform-state --region us-east-1
   aws s3api put-bucket-versioning --bucket voice-assistant-qa-terraform-state --versioning-configuration Status=Enabled
   ```
4. **Lambda deployment packages**:
   - `nightly_eval.zip` - Lambda function code
   - `lambda_layer.zip` - Python dependencies layer

## Quick Start

```bash
cd infra/terraform

# Copy and edit variables
cp variables.tfvars.example variables.tfvars
# Edit variables.tfvars with your values

# Initialize
terraform init

# Plan
terraform plan -var-file=variables.tfvars

# Apply
terraform apply -var-file=variables.tfvars
```

## Creating Lambda Deployment Packages

### 1. Lambda Function Code (`nightly_eval.zip`)

```bash
# From project root
cd infra/lambda
zip -r ../terraform/nightly_eval.zip nightly_eval.py
```

### 2. Lambda Layer (`lambda_layer.zip`)

```bash
# Create layer with dependencies
mkdir -p lambda_layer/python
cd lambda_layer
pip install -t python/ \
  boto3 \
  requests \
  deep-eval \
  ragas \
  jiwer \
  faster-whisper \
  edge-tts \
  pydantic \
  pydantic-settings \
  sqlalchemy \
  aiosqlite \
  loguru \
  pyyaml
cd ..
zip -r infra/terraform/lambda_layer.zip lambda_layer/python
```

**Note**: The layer should be created on Linux (or use `pip install --platform manylinux2014_x86_64` on Mac/Windows).

## Required GitHub Secrets

After Terraform applies, add these to your GitHub repository secrets:

| Secret | Value |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | IAM user with Terraform deployment permissions |
| `AWS_SECRET_ACCESS_KEY` | Secret key |
| `AWS_REGION` | `us-east-1` |
| `S3_BUCKET` | Output from `terraform output s3_bucket_name` |
| `SLACK_WEBHOOK_URL` | Your Slack webhook URL |
| `OPENAI_API_KEY` | OpenAI API key |
| `API_KEY` | Service API key |

## GitHub Actions OIDC Setup

The Terraform creates an IAM role for GitHub Actions with OIDC. To use it:

1. **Configure AWS OIDC Provider** (one-time):
   ```bash
   aws iam create-open-id-connect-provider \
     --url https://token.actions.githubusercontent.com \
     --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1 \
     --client-id-list sts.amazonaws.com
   ```

2. **Update workflow** to use the role:
   ```yaml
   - name: Configure AWS credentials
     uses: aws-actions/configure-aws-credentials@v4
     with:
       role-to-assume: ${{ secrets.GITHUB_ACTIONS_ROLE_ARN }}
       aws-region: us-east-1
   ```

3. **Add role ARN to GitHub secrets**:
   - `GITHUB_ACTIONS_ROLE_ARN` = `terraform output github_actions_role_arn`

## Estimated Monthly Costs (us-east-1)

| Component | Usage | Monthly Cost |
|-----------|-------|--------------|
| S3 Storage | 10 GB | $0.23 |
| S3 Requests | 1M PUT/GET | $0.50 |
| Lambda | 1M invocations, 512MB, 300s | $3.50 |
| CloudWatch Metrics | 10 custom metrics | $3.00 |
| CloudWatch Logs | 5 GB ingest | $2.50 |
| CloudWatch Alarms | 10 alarms | $1.00 |
| EventBridge | 1M events | $1.00 |
| SNS | 100 notifications | $0.50 |
| **Total** | | **~$12.23/month** |

*First 12 months may qualify for AWS Free Tier.*

## Teardown

```bash
terraform destroy -var-file=variables.tfvars
```

**Manual cleanup after destroy:**
- CloudWatch log groups: `/aws/lambda/voice-assistant-qa-*`
- CloudWatch metric filters (if any)
- Secrets Manager secrets: `voice-assistant-qa/*`

## Updating Infrastructure

```bash
# Pull latest changes
git pull

# Plan changes
terraform plan -var-file=variables.tfvars

# Apply
terraform apply -var-file=variables.tfvars
```

## Module Structure

```
infra/terraform/
├── main.tf                 # Main configuration
├── variables.tfvars.example # Example variables
├── dashboard.json          # CloudWatch dashboard (referenced)
├── nightly_eval.zip        # Lambda function (generated)
└── lambda_layer.zip        # Lambda layer (generated)
```

## Security Notes

- All S3 buckets have encryption, versioning, and public access blocked
- IAM policies follow least privilege principle
- GitHub Actions uses OIDC (no long-lived credentials)
- Secrets stored in AWS Secrets Manager (not in code)
- CloudWatch alarms notify via SNS (email + Slack)

## Troubleshooting

### Lambda deployment fails
- Ensure `nightly_eval.zip` and `lambda_layer.zip` exist
- Check Python version compatibility (3.11)
- Verify layer was built on Linux

### GitHub Actions can't assume role
- Verify OIDC provider exists
- Check `github_repo` variable matches your repo exactly
- Ensure repository has `id-token: write` permission

### CloudWatch alarms not firing
- Verify metrics are being published to `VoiceAssistantQA` namespace
- Check alarm dimensions match published metrics
- Ensure SNS topic subscription is confirmed