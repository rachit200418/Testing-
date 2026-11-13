# Terraform configuration for Voice Assistant QA Platform AWS infrastructure

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket = "voice-assistant-qa-terraform-state"
    key    = "infrastructure/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "voice-assistant-qa"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# Variables
variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "account_id" {
  description = "AWS account ID"
  type        = string
}

variable "s3_bucket_name" {
  description = "S3 bucket name for datasets, logs, reports"
  type        = string
  default     = ""
}

# Generate bucket name if not provided
locals {
  bucket_name = var.s3_bucket_name != "" ? var.s3_bucket_name : "voice-assistant-qa-${var.environment}-${var.account_id}"
}

# ============================================================
# S3 BUCKET
# ============================================================

resource "aws_s3_bucket" "main" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_versioning" "main" {
  bucket = aws_s3_bucket.main.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "main" {
  bucket = aws_s3_bucket.main.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    id     = "expire-old-logs"
    status = "Enabled"

    filter {
      prefix = "logs/"
    }

    expiration {
      days = 90
    }
  }

  rule {
    id     = "expire-old-reports"
    status = "Enabled"

    filter {
      prefix = "reports/"
    }

    expiration {
      days = 365
    }
  }

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {
      prefix = ""
    }

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
  }
}

# ============================================================
# IAM ROLES AND POLICIES
# ============================================================

# Lambda execution role
resource "aws_iam_role" "lambda_execution" {
  name = "voice-assistant-qa-lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_execution" {
  name = "VoiceAssistantQALambdaPolicy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ReadWrite"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${local.bucket_name}",
          "arn:aws:s3:::${local.bucket_name}/*"
        ]
      },
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:log-group:/aws/lambda/voice-assistant-qa-*"
      },
      {
        Sid    = "CloudWatchMetrics"
        Effect = "Allow"
        Action = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "VoiceAssistantQA"
          }
        }
      },
      {
        Sid    = "SecretsManager"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:*:*:secret:voice-assistant-qa/*"
      },
      {
        Sid    = "SNSNotifications"
        Effect = "Allow"
        Action = ["sns:Publish"]
        Resource = "arn:aws:sns:*:*:voice-assistant-qa-alerts"
      }
    ]
  })
}

# GitHub Actions OIDC role (for CI/CD)
resource "aws_iam_role" "github_actions" {
  name = "voice-assistant-qa-github-actions-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = "arn:aws:iam::${var.account_id}:oidc-provider/token.actions.githubusercontent.com"
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*"
        }
      }
    }]
  })
}

variable "github_repo" {
  description = "GitHub repository in format 'org/repo'"
  type        = string
  default     = ""
}

resource "aws_iam_role_policy" "github_actions" {
  name = "VoiceAssistantQATestRunnerPolicy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ReadDatasets"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${local.bucket_name}",
          "arn:aws:s3:::${local.bucket_name}/*"
        ]
        Condition = {
          StringEquals = {
            "s3:prefix" = ["datasets/", "golden/"]
          }
        }
      },
      {
        Sid    = "S3WriteLogsReports"
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl"
        ]
        Resource = [
          "arn:aws:s3:::${local.bucket_name}/logs/*",
          "arn:aws:s3:::${local.bucket_name}/reports/*",
          "arn:aws:s3:::${local.bucket_name}/eval/*"
        ]
      },
      {
        Sid    = "CloudWatchMetrics"
        Effect = "Allow"
        Action = ["cloudwatch:PutMetricData"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "cloudwatch:namespace" = "VoiceAssistantQA"
          }
        }
      },
      {
        Sid    = "LambdaInvoke"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = "arn:aws:lambda:*:*:function:voice-assistant-qa-*"
      },
      {
        Sid    = "SecretsManagerRead"
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = "arn:aws:secretsmanager:*:*:secret:voice-assistant-qa/*"
      }
    ]
  })
}

# ============================================================
# LAMBDA FUNCTION
# ============================================================

resource "aws_lambda_function" "nightly_eval" {
  function_name = "voice-assistant-qa-nightly-eval-${var.environment}"
  role          = aws_iam_role.lambda_execution.arn
  runtime       = "python3.11"
  handler       = "nightly_eval.handler"
  timeout       = 300
  memory_size   = 512

  # Package the lambda code
  filename         = "nightly_eval.zip"
  source_code_hash = filebase64sha256("nightly_eval.zip")

  environment {
    variables = {
      S3_BUCKET           = local.bucket_name
      AWS_REGION          = var.aws_region
      SLACK_WEBHOOK_URL   = var.slack_webhook_url
      API_KEY             = var.api_key
      OPENAI_API_KEY      = var.openai_api_key
    }
  }
}

variable "slack_webhook_url" {
  description = "Slack webhook URL for notifications"
  type        = string
  default     = ""
}

variable "api_key" {
  description = "API key for the service"
  type        = string
  default     = ""
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  default     = ""
}

# Lambda layer for dependencies
resource "aws_lambda_layer_version" "dependencies" {
  layer_name          = "voice-assistant-qa-deps-${var.environment}"
  description         = "Python dependencies for nightly eval"
  compatible_runtimes = ["python3.11"]
  source_code_hash    = filebase64sha256("lambda_layer.zip")

  # Create layer zip with: pip install -t python/ -r requirements.txt && zip -r lambda_layer.zip python/
}

resource "aws_lambda_function" "nightly_eval" {
  function_name = "voice-assistant-qa-nightly-eval-${var.environment}"
  role          = aws_iam_role.lambda_execution.arn
  runtime       = "python3.11"
  handler       = "nightly_eval.handler"
  timeout       = 300
  memory_size   = 512
  layers        = [aws_lambda_layer_version.dependencies.arn]

  filename         = "nightly_eval.zip"
  source_code_hash = filebase64sha256("nightly_eval.zip")

  environment {
    variables = {
      S3_BUCKET           = local.bucket_name
      AWS_REGION          = var.aws_region
      SLACK_WEBHOOK_URL   = var.slack_webhook_url
      API_KEY             = var.api_key
      OPENAI_API_KEY      = var.openai_api_key
    }
  }
}

# ============================================================
# EVENTBRIDGE SCHEDULE (Nightly at 2 AM UTC)
# ============================================================

resource "aws_cloudwatch_event_rule" "nightly_eval" {
  name                = "voice-assistant-qa-nightly-eval-${var.environment}"
  description         = "Trigger nightly evaluation at 2 AM UTC"
  schedule_expression = "cron(0 2 * * ? *)"
  is_enabled          = true
}

resource "aws_cloudwatch_event_target" "nightly_eval" {
  rule = aws_cloudwatch_event_rule.nightly_eval.name
  arn  = aws_lambda_function.nightly_eval.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.nightly_eval.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.nightly_eval.arn
}

# ============================================================
# CLOUDWATCH DASHBOARD
# ============================================================

resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "voice-assistant-qa-${var.environment}"
  dashboard_body = file("${path.module}/dashboard.json")
}

# ============================================================
# CLOUDWATCH ALARMS
# ============================================================

resource "aws_sns_topic" "alerts" {
  name = "voice-assistant-qa-alerts-${var.environment}"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

variable "alert_email" {
  description = "Email for CloudWatch alerts"
  type        = string
  default     = ""
}

# P95 Latency alarm - text chat
resource "aws_cloudwatch_metric_alarm" "p95_latency_text" {
  alarm_name          = "voice-assistant-qa-p95-latency-text-chat-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "P95Latency"
  namespace           = "VoiceAssistantQA"
  period              = 300
  statistic           = "Maximum"
  threshold           = 5000
  alarm_description   = "P95 latency for /text/chat exceeded 5 seconds"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]

  dimension {
    name  = "Endpoint"
    value = "/text/chat"
  }
}

# P95 Latency alarm - audio chat
resource "aws_cloudwatch_metric_alarm" "p95_latency_audio" {
  alarm_name          = "voice-assistant-qa-p95-latency-audio-chat-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "P95Latency"
  namespace           = "VoiceAssistantQA"
  period              = 300
  statistic           = "Maximum"
  threshold           = 15000
  alarm_description   = "P95 latency for /audio/chat exceeded 15 seconds"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimension {
    name  = "Endpoint"
    value = "/audio/chat"
  }
}

# Error rate alarm - text chat
resource "aws_cloudwatch_metric_alarm" "error_rate_text" {
  alarm_name          = "voice-assistant-qa-error-rate-text-chat-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ErrorRate"
  namespace           = "VoiceAssistantQA"
  period              = 300
  statistic           = "Average"
  threshold           = 0.05
  alarm_description   = "Error rate for /text/chat exceeded 5%"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimension {
    name  = "Endpoint"
    value = "/text/chat"
  }
}

# Error rate alarm - audio chat
resource "aws_cloudwatch_metric_alarm" "error_rate_audio" {
  alarm_name          = "voice-assistant-qa-error-rate-audio-chat-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ErrorRate"
  namespace           = "VoiceAssistantQA"
  period              = 300
  statistic           = "Average"
  threshold           = 0.10
  alarm_description   = "Error rate for /audio/chat exceeded 10%"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimension {
    name  = "Endpoint"
    value = "/audio/chat"
  }
}

# Hallucination score alarm
resource "aws_cloudwatch_metric_alarm" "hallucination" {
  alarm_name          = "voice-assistant-qa-hallucination-score-${var.environment}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HallucinationScore"
  namespace           = "VoiceAssistantQA"
  period              = 86400
  statistic           = "Average"
  threshold           = 0.15
  alarm_description   = "Hallucination score exceeded 15% in nightly eval"
  alarm_actions       = [aws_sns_topic.alerts.arn]

  dimension {
    name  = "Model"
    value = "gpt-4o-mini"
  }
}

# Confirmation rate alarm
resource "aws_cloudwatch_metric_alarm" "confirmation_rate" {
  alarm_name          = "voice-assistant-qa-confirmation-rate-${var.environment}"
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ConfirmationRate"
  namespace           = "VoiceAssistantQA"
  period              = 86400
  statistic           = "Average"
  threshold           = 1.0
  alarm_description   = "Confirmation rate dropped below 100% in nightly eval"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# ============================================================
# OUTPUTS
# ============================================================

output "s3_bucket_name" {
  description = "S3 bucket for datasets, logs, reports"
  value       = aws_s3_bucket.main.bucket
}

output "lambda_function_arn" {
  description = "Nightly eval Lambda function ARN"
  value       = aws_lambda_function.nightly_eval.arn
}

output "github_actions_role_arn" {
  description = "GitHub Actions OIDC role ARN"
  value       = aws_iam_role.github_actions.arn
}

output "cloudwatch_dashboard_url" {
  description = "CloudWatch dashboard URL"
  value       = "https://${var.aws_region}.console.aws.amazon.com/cloudwatch/home?region=${var.aws_region}#dashboards:name=voice-assistant-qa-${var.environment}"
}

output "sns_topic_arn" {
  description = "SNS topic for alerts"
  value       = aws_sns_topic.alerts.arn
}