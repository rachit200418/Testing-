# AWS Setup Guide

## Overview

This guide covers deploying the QA platform's AWS infrastructure for:
- S3 storage (datasets, logs, reports)
- Nightly Lambda evaluation
- CloudWatch metrics & alarms
- Least-privilege IAM

## Prerequisites

- AWS CLI configured with admin permissions
- Terraform 1.6+
- Python 3.11+ for Lambda packaging

## Architecture

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   GitHub Actions│────▶│   S3 Bucket  │◀───▶│  Athena/DuckDB  │
│   (Nightly)     │     │  (datasets,  │     │  (Validation)   │
└─────────────────┘     │   logs,      │     └─────────────────┘
                        │   reports)   │
                        └──────┬───────┘
                               │
                    ┌──────────▼──────────┐
                    │  Lambda (Nightly)   │
                    │  - Sample eval      │
                    │  - Slack/Email      │
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   CloudWatch        │
                    │  - Custom Metrics   │
                    │  - Dashboard        │
                    │  - Alarms           │
                    └─────────────────────┘
```

## S3 Bucket Layout

```
s3://voice-assistant-qa-{env}-{account}/
├── datasets/
│   ├── audio/           # Raw audio clips
│   ├── manifest.csv     # Dataset manifest
│   └── golden/          # Golden eval dataset
├── logs/
│   ├── YYYY/
│   │   ├── MM/
│   │   │   ├── DD/
│   │   │   │   ├── app-<request_id>.jsonl
│   ├── latest/          # Symlink to latest day
├── reports/
│   ├── YYYY-MM-DD/
│   │   ├── stt_wer.html
│   │   ├── llm_eval.html
│   │   ├── safety.html
│   │   ├── ui_trace.zip
│   │   ├── locust.html
│   │   └── summary.json
├── eval/
│   ├── baseline/        # Baseline run artifacts
│   └── current/         # Latest run artifacts
```

## Terraform Deployment

### 1. Initialize

```bash
cd infra/terraform
terraform init
```

### 2. Plan

```bash
terraform plan -var="environment=dev" -var="aws_region=us-east-1"
```

### 3. Apply

```bash
terraform apply -var="environment=dev" -var="aws_region=us-east-1"
```

### 4. Outputs

```bash
terraform output
# s3_bucket_name
# lambda_function_arn
# cloudwatch_dashboard_url
# iam_policy_arn
```

## IAM Policy (Least Privilege)

### Test Runner Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3ReadDatasets",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::voice-assistant-qa-*",
        "arn:aws:s3:::voice-assistant-qa-*/*"
      ],
      "Condition": {
        "StringEquals": {
          "s3:prefix": ["datasets/", "golden/"]
        }
      }
    },
    {
      "Sid": "S3WriteLogsReports",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl"
      ],
      "Resource": [
        "arn:aws:s3:::voice-assistant-qa-*/logs/*",
        "arn:aws:s3:::voice-assistant-qa-*/reports/*",
        "arn:aws:s3:::voice-assistant-qa-*/eval/*"
      ]
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "VoiceAssistantQA"
        }
      }
    },
    {
      "Sid": "LambdaInvoke",
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:*:*:function:voice-assistant-qa-*"
    }
  ]
}
```

### Lambda Execution Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3ReadWrite",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::voice-assistant-qa-*",
        "arn:aws:s3:::voice-assistant-qa-*/*"
      ]
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/aws/lambda/voice-assistant-qa-*"
    },
    {
      "Sid": "CloudWatchMetrics",
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "cloudwatch:namespace": "VoiceAssistantQA"
        }
      }
    },
    {
      "Sid": "SecretsManager",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:*:*:secret:voice-assistant-qa/*"
    }
  ]
}
```

## Lambda Function

### Package

```bash
cd infra/lambda
pip install -r requirements.txt -t package/
cp nightly_eval.py package/
cd package && zip -r ../nightly_eval.zip .
```

### Deploy

```bash
aws lambda create-function \
  --function-name voice-assistant-qa-nightly-eval \
  --runtime python3.11 \
  --handler nightly_eval.handler \
  --zip-file fileb://nightly_eval.zip \
  --role arn:aws:iam::ACCOUNT:role/voice-assistant-qa-lambda-role \
  --timeout 300 \
  --memory-size 512 \
  --environment Variables={S3_BUCKET=voice-assistant-qa-prod-123456789,SLACK_WEBHOOK_URL=https://hooks.slack.com/...}
```

### Schedule (EventBridge)

```bash
aws events put-rule \
  --name voice-assistant-qa-nightly \
  --schedule-expression "cron(0 2 * * ? *)" \
  --description "Nightly QA evaluation"

aws events put-targets \
  --rule voice-assistant-qa-nightly \
  --targets "Id=1,Arn=arn:aws:lambda:us-east-1:ACCOUNT:function:voice-assistant-qa-nightly-eval"

aws lambda add-permission \
  --function-name voice-assistant-qa-nightly-eval \
  --statement-id allow-eventbridge \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn arn:aws:events:us-east-1:ACCOUNT:rule/voice-assistant-qa-nightly
```

## CloudWatch Dashboard

### Metrics (Custom Namespace: VoiceAssistantQA)

| Metric | Dimensions | Statistic | Alarm Threshold |
|--------|------------|-----------|-----------------|
| P95Latency | Endpoint | p95 | > 5000ms |
| ErrorRate | Endpoint | Sum/Count | > 5% |
| HallucinationScore | Model | Average | > 0.15 |
| WER | Adapter,Slice | Average | > threshold |
| CostPerRequest | Model | Average | > $0.01 |
| ConfirmationRate | Tool | Average | < 100% |

### Dashboard JSON

See `infra/cloudwatch/dashboard.json` for full dashboard definition.

### Alarms

```bash
# P95 Latency Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name voice-assistant-qa-p95-latency \
  --alarm-description "P95 latency exceeded threshold" \
  --metric-name P95Latency \
  --namespace VoiceAssistantQA \
  --statistic p95 \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 5000 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:voice-assistant-qa-alerts

# Error Rate Alarm
aws cloudwatch put-metric-alarm \
  --alarm-name voice-assistant-qa-error-rate \
  --alarm-description "Error rate exceeded 5%" \
  --metric-name ErrorRate \
  --namespace VoiceAssistantQA \
  --statistic Average \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 0.05 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT:voice-assistant-qa-alerts
```

## Cost Estimation (Monthly, us-east-1)

| Component | Usage | Cost |
|-----------|-------|------|
| S3 Storage | 10 GB | $0.23 |
| S3 Requests | 1M PUT/GET | $0.50 |
| Lambda | 1M invocations, 512MB, 300s | $3.50 |
| CloudWatch Metrics | 10 custom metrics | $3.00 |
| CloudWatch Logs | 5 GB ingest | $2.50 |
| CloudWatch Alarms | 5 alarms | $0.50 |
| EventBridge | 1M events | $1.00 |
| **Total** | | **~$11.23/month** |

*Note: Costs vary by region and usage. First 12 months free tier may apply.*

## Teardown Checklist

```bash
# 1. Delete CloudWatch alarms
aws cloudwatch delete-alarms --alarm-names voice-assistant-qa-p95-latency voice-assistant-qa-error-rate

# 2. Delete EventBridge rule
aws events remove-targets --rule voice-assistant-qa-nightly --ids 1
aws events delete-rule --name voice-assistant-qa-nightly

# 3. Delete Lambda
aws lambda delete-function --function-name voice-assistant-qa-nightly-eval

# 4. Delete IAM roles/policies
aws iam delete-role-policy --role-name voice-assistant-qa-lambda-role --policy-name VoiceAssistantQALambdaPolicy
aws iam delete-role --role-name voice-assistant-qa-lambda-role

aws iam delete-role-policy --role-name voice-assistant-qa-test-runner --policy-name VoiceAssistantQATestRunnerPolicy
aws iam delete-role --role-name voice-assistant-qa-test-runner

# 5. Empty and delete S3 bucket
aws s3 rm s3://voice-assistant-qa-prod-123456789 --recursive
aws s3 rb s3://voice-assistant-qa-prod-123456789

# 6. Terraform destroy (if used)
cd infra/terraform && terraform destroy
```

## GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| AWS_ACCESS_KEY_ID | IAM user with deployment permissions |
| AWS_SECRET_ACCESS_KEY | Secret key |
| AWS_REGION | e.g., us-east-1 |
| S3_BUCKET | Bucket name |
| SLACK_WEBHOOK_URL | For Lambda notifications |
| OPENAI_API_KEY | For real LLM eval (optional) |

## Validation Queries

### DuckDB (Local)

```sql
-- Unmasked PII in logs
SELECT * FROM read_json_auto('logs/app.log')
WHERE pii_masked = false AND (response_text LIKE '%@%' OR response_text LIKE '%[0-9]%');

-- Duplicate requests
SELECT input_text, COUNT(*) as cnt
FROM read_json_auto('logs/app.log')
GROUP BY input_text HAVING cnt > 1;

-- Latency drift by day
SELECT date(timestamp) as day, percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms.total_ms) as p95
FROM read_json_auto('logs/app.log')
GROUP BY day ORDER BY day;

-- Hallucination score drift
SELECT date(timestamp) as day, avg(hallucination_score) as avg_hallucination
FROM read_json_auto('reports/llm_eval/*.json')
GROUP BY day ORDER BY day;

-- Cost per day
SELECT date(timestamp) as day, sum(estimated_cost_usd) as daily_cost
FROM read_json_auto('logs/app.log')
GROUP BY day ORDER BY day;
```

### Athena (Same SQL, External Tables)

```sql
CREATE EXTERNAL TABLE voice_assistant_logs (
  timestamp string,
  request_id string,
  session_id string,
  endpoint string,
  transcript string,
  response_text string,
  intent string,
  latency_ms struct<stt_ms:int,llm_ms:int,tts_ms:int,total_ms:int>,
  token_count int,
  estimated_cost_usd double,
  pii_masked boolean
)
PARTITIONED BY (year string, month string, day string)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://voice-assistant-qa-prod-123456789/logs/';
```