# IAM Policies Documentation

This document explains the least-privilege IAM policies for the Voice Assistant QA Platform.

## Overview

Two IAM policies are defined:

1. **Test Runner Policy** - For CI/CD pipelines and test runners
2. **Lambda Execution Policy** - For the nightly evaluation Lambda function

Both follow the principle of least privilege, granting only the permissions needed.

---

## Test Runner Policy (`test_runner_policy.json`)

### Purpose
Used by GitHub Actions runners and local test execution to:
- Read test datasets from S3
- Write logs, reports, and evaluation artifacts to S3
- Publish custom metrics to CloudWatch
- Invoke the nightly evaluation Lambda
- Read secrets (API keys) from Secrets Manager

### Permissions Breakdown

| Statement | Purpose | Resources | Conditions |
|-----------|---------|-----------|------------|
| `S3ReadDatasets` | Read test datasets | `voice-assistant-qa-*` buckets | Only `datasets/` and `golden/` prefixes |
| `S3WriteLogsReports` | Write logs/reports | `voice-assistant-qa-*` buckets | Only `logs/`, `reports/`, `eval/` prefixes |
| `CloudWatchMetrics` | Publish metrics | All | Only `VoiceAssistantQA` namespace |
| `LambdaInvoke` | Trigger nightly eval | `voice-assistant-qa-*` functions | - |
| `SecretsManagerRead` | Read API keys | `voice-assistant-qa/*` secrets | - |

### Why These Restrictions?

- **Prefix conditions**: Prevents access to unrelated data in the same bucket
- **Namespace condition**: Prevents publishing to other CloudWatch namespaces
- **Resource patterns**: Wildcard only for account-specific bucket naming (`voice-assistant-qa-${ENV}-${ACCOUNT}`)

### Attaching to GitHub Actions

```bash
# Create role for GitHub Actions OIDC
aws iam create-role \
  --role-name voice-assistant-qa-github-actions \
  --assume-role-policy-document file://github-actions-trust-policy.json

# Attach policy
aws iam put-role-policy \
  --role-name voice-assistant-qa-github-actions \
  --policy-name VoiceAssistantQATestRunnerPolicy \
  --policy-document file://infra/iam/test_runner_policy.json
```

### GitHub Actions Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR_ORG/voice-assistant-qa:*"
        }
      }
    }
  ]
}
```

---

## Lambda Execution Policy (`lambda_execution_policy.json`)

### Purpose
Used by the nightly evaluation Lambda function to:
- Read/write all data in the project S3 buckets
- Write logs to CloudWatch Logs
- Publish metrics to CloudWatch
- Read secrets (API keys) from Secrets Manager
- Send SNS notifications on failure

### Permissions Breakdown

| Statement | Purpose | Resources | Conditions |
|-----------|---------|-----------|------------|
| `S3ReadWrite` | Full S3 access for project | `voice-assistant-qa-*` buckets | - |
| `CloudWatchLogs` | Write Lambda logs | `/aws/lambda/voice-assistant-qa-*` log groups | - |
| `CloudWatchMetrics` | Publish custom metrics | All | Only `VoiceAssistantQA` namespace |
| `SecretsManager` | Read API keys | `voice-assistant-qa/*` secrets | - |
| `SNSNotifications` | Send alerts | `voice-assistant-qa-alerts` topic | - |

### Creating the Lambda Role

```bash
aws iam create-role \
  --role-name voice-assistant-qa-lambda-role \
  --assume-role-policy-document file://lambda-trust-policy.json

aws iam put-role-policy \
  --role-name voice-assistant-qa-lambda-role \
  --policy-name VoiceAssistantQALambdaPolicy \
  --policy-document file://infra/iam/lambda_execution_policy.json
```

### Lambda Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

---

## Secrets Manager Structure

Store the following secrets in AWS Secrets Manager:

```
/voice-assistant-qa/
├── api-key                 # API key for the service
├── openai-api-key          # OpenAI API key
├── gemini-api-key          # Gemini API key (optional)
├── slack-webhook-url       # Slack webhook for notifications
├── aws-access-key-id       # For cross-account access (if needed)
└── aws-secret-access-key   # For cross-account access (if needed)
```

### Creating Secrets

```bash
aws secretsmanager create-secret \
  --name voice-assistant-qa/api-key \
  --secret-string "your-secure-api-key"

aws secretsmanager create-secret \
  --name voice-assistant-qa/openai-api-key \
  --secret-string "sk-..."
```

---

## S3 Bucket Structure

The policies assume this bucket naming convention:

```
voice-assistant-qa-${ENV}-${ACCOUNT_ID}
```

Example: `voice-assistant-qa-prod-123456789012`

### Bucket Policy (Optional - for additional security)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EnforceEncryption",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:PutObject",
      "Resource": "arn:aws:s3:::voice-assistant-qa-*/*",
      "Condition": {
        "StringNotEquals": {
          "s3:x-amz-server-side-encryption": "AES256"
        }
      }
    },
    {
      "Sid": "EnforceTLS",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": "arn:aws:s3:::voice-assistant-qa-*/*",
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
```

---

## CloudWatch Namespace

All custom metrics are published to the `VoiceAssistantQA` namespace with these dimensions:

| Metric | Dimensions |
|--------|------------|
| P95Latency | Endpoint |
| ErrorRate | Endpoint |
| HallucinationScore | Model |
| FaithfulnessScore | Model |
| RelevancyScore | Model |
| ConfirmationRate | (none) |
| RefusalRate | (none) |
| PiiMaskingRate | (none) |
| WER | Adapter, Slice |
| CostPerRequest | Model |
| STTLatency | Adapter |
| LLMLatency | Model |
| TTSLatency | Adapter |
| IntentAccuracy | (none) |
| SlotAccuracy | (none) |
| ThroughputRPS | Endpoint |

---

## Monitoring and Auditing

### CloudTrail

Enable CloudTrail to audit all API calls made with these roles:

```bash
aws cloudtrail create-trail \
  --name voice-assistant-qa-audit \
  --s3-bucket-name voice-assistant-qa-audit-logs \
  --is-multi-region-trail
```

### Access Analyzer

Use IAM Access Analyzer to verify policies don't grant unintended access:

```bash
aws accessanalyzer create-analyzer \
  --analyzer-name voice-assistant-qa-analyzer \
  --type ACCOUNT
```

---

## Policy Versioning

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01-15 | Initial policies |
| 1.1 | 2024-02-01 | Added SecretsManager read for API keys |
| 1.2 | 2024-03-01 | Added SNS publish for Lambda alerts |

---

## Testing Permissions

### Test Test Runner Policy

```bash
# Assume role and test
aws sts assume-role \
  --role-arn arn:aws:iam::123456789012:role/voice-assistant-qa-github-actions \
  --role-session-name test-session

# With temp credentials, test:
aws s3 ls s3://voice-assistant-qa-prod-123456789012/datasets/
aws cloudwatch put-metric-data \
  --namespace VoiceAssistantQA \
  --metric-data MetricName=TestMetric,Value=1
```

### Test Lambda Policy

```bash
# Deploy Lambda and check CloudWatch Logs
# Verify metrics appear in CloudWatch under VoiceAssistantQA namespace
```

---

## Troubleshooting

### Access Denied on S3

1. Check bucket name matches `voice-assistant-qa-*` pattern
2. Verify prefix condition matches (`datasets/`, `golden/`, `logs/`, `reports/`, `eval/`)
3. Check bucket policy doesn't deny access

### CloudWatch Metrics Not Appearing

1. Verify namespace is exactly `VoiceAssistantQA`
2. Check metric dimensions match dashboard/alarm definitions
3. Ensure `cloudwatch:PutMetricData` permission has namespace condition

### Lambda Can't Read Secrets

1. Verify secret name starts with `voice-assistant-qa/`
2. Check Lambda role has `secretsmanager:GetSecretValue` on correct ARN
3. Verify secret exists in same region as Lambda

---

## References

- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Least Privilege](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html#grant-least-privilege)
- [CloudWatch Custom Metrics](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/publishingMetrics.html)
- [Secrets Manager](https://docs.aws.amazon.com/secretsmanager/latest/userguide/intro.html)