#!/usr/bin/env python3
"""
Lambda function for nightly evaluation of Voice Assistant QA Platform.

Runs a sample evaluation and posts summary to Slack/Email.
"""

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import boto3

# Add the app to path
sys.path.insert(0, "/opt/python")
sys.path.insert(0, "/var/task")

from app.s3_logging import S3LogUploader


def handler(event, context):
    """Lambda entry point."""
    print(f"Starting nightly eval at {datetime.utcnow().isoformat()}")

    # Configuration from environment
    s3_bucket = os.environ.get("S3_BUCKET")
    slack_webhook = os.environ.get("SLACK_WEBHOOK_URL")
    api_key = os.environ.get("API_KEY", "test-api-key")
    openai_key = os.environ.get("OPENAI_API_KEY")

    if not s3_bucket:
        return {"statusCode": 500, "body": "S3_BUCKET not configured"}

    # Set up environment for the test run
    env = os.environ.copy()
    env.update({
        "STT_ADAPTER": "faster-whisper",
        "LLM_ADAPTER": "openai",
        "TTS_ADAPTER": "edge-tts",
        "API_KEY": api_key,
        "OPENAI_API_KEY": openai_key,
        "DATABASE_URL": "sqlite+aiosqlite:///./data/app.db",
        "WHISPER_MODEL_SIZE": "base",
        "WHISPER_DEVICE": "cpu",
        "WHISPER_COMPUTE_TYPE": "int8",
    })

    run_id = f"nightly_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    report_dir = Path(f"/tmp/reports/{run_id}")
    report_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Run smoke evaluation (15 cases)
        print("Running smoke evaluation...")
        result = run_smoke_eval(report_dir, env)

        # Run safety smoke tests
        print("Running safety tests...")
        safety_result = run_safety_tests(report_dir, env)

        # Generate summary
        summary = generate_summary(result, safety_result, run_id)

        # Upload reports to S3
        print("Uploading reports to S3...")
        upload_reports(s3_bucket, report_dir, run_id)

        # Post to Slack
        if slack_webhook:
            print("Posting to Slack...")
            post_to_slack(slack_webhook, summary)

        print(f"Nightly eval completed: {run_id}")
        return {
            "statusCode": 200,
            "body": json.dumps({
                "run_id": run_id,
                "summary": summary,
                "status": "success"
            })
        }

    except Exception as e:
        print(f"Nightly eval failed: {e}")
        if slack_webhook:
            post_to_slack(slack_webhook, {
                "run_id": run_id,
                "status": "failed",
                "error": str(e)
            })
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }


def run_smoke_eval(report_dir: Path, env: dict) -> dict:
    """Run smoke evaluation with 15 golden cases."""
    # Use pytest to run a subset of tests
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/llm_eval/test_deepeval.py::TestDeepEvalSmoke::test_smoke_relevancy",
        "-v", "--tb=short",
        f"--html={report_dir}/smoke_eval.html",
        "--self-contained-html"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_safety_tests(report_dir: Path, env: dict) -> dict:
    """Run safety smoke tests."""
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/safety/test_safety.py::TestSafetyEndToEnd::test_medical_advice_refused",
        "tests/safety/test_safety.py::TestSafetyEndToEnd::test_prompt_injection_refused",
        "tests/safety/test_safety.py::TestSafetyEndToEnd::test_pii_masked_in_response",
        "tests/safety/test_safety.py::TestSafetyEndToEnd::test_system_prompt_not_revealed",
        "tests/safety/test_safety.py::TestSafetyEndToEnd::test_confirmation_before_booking",
        "-v", "--tb=short",
        f"--html={report_dir}/safety_smoke.html",
        "--self-contained-html"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=300)

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def generate_summary(eval_result: dict, safety_result: dict, run_id: str) -> dict:
    """Generate summary from test results."""
    eval_passed = eval_result["returncode"] == 0
    safety_passed = safety_result["returncode"] == 0

    # Parse test counts from stdout (simplified)
    def parse_counts(stdout: str) -> dict:
        passed = stdout.count(" PASSED")
        failed = stdout.count(" FAILED")
        errors = stdout.count(" ERROR")
        return {"passed": passed, "failed": failed, "errors": errors}

    return {
        "run_id": run_id,
        "timestamp": datetime.utcnow().isoformat(),
        "overall_status": "passed" if (eval_passed and safety_passed) else "failed",
        "eval": {
            "status": "passed" if eval_passed else "failed",
            "counts": parse_counts(eval_result["stdout"]),
        },
        "safety": {
            "status": "passed" if safety_passed else "failed",
            "counts": parse_counts(safety_result["stdout"]),
        },
        "reports": {
            "eval_html": f"s3://{os.environ.get('S3_BUCKET')}/reports/{datetime.utcnow().strftime('%Y-%m-%d')}/{run_id}/smoke_eval.html",
            "safety_html": f"s3://{os.environ.get('S3_BUCKET')}/reports/{datetime.utcnow().strftime('%Y-%m-%d')}/{run_id}/safety_smoke.html",
        }
    }


def upload_reports(s3_bucket: str, report_dir: Path, run_id: str):
    """Upload reports to S3."""
    s3 = boto3.client("s3")
    date_prefix = datetime.utcnow().strftime("%Y-%m-%d")

    for file_path in report_dir.rglob("*"):
        if file_path.is_file():
            relative = file_path.relative_to(report_dir)
            s3_key = f"reports/{date_prefix}/{run_id}/{relative}"
            s3.upload_file(str(file_path), s3_bucket, s3_key)
            print(f"Uploaded {file_path} to s3://{s3_bucket}/{s3_key}")


def post_to_slack(webhook_url: str, summary: dict):
    """Post summary to Slack."""
    import urllib.request

    status_emoji = "✅" if summary["overall_status"] == "passed" else "❌"

    message = {
        "text": f"{status_emoji} Nightly QA Evaluation: {summary['overall_status'].upper()}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{status_emoji} Nightly QA Evaluation - {summary['run_id']}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Status:* {summary['overall_status'].upper()}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:* {summary['timestamp']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Eval:* {summary['eval']['status']} ({summary['eval']['counts']['passed']} passed, {summary['eval']['counts']['failed']} failed)"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Safety:* {summary['safety']['status']} ({summary['safety']['counts']['passed']} passed, {summary['safety']['counts']['failed']} failed)"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reports:*\n• <{summary['reports']['eval_html']}|Eval Report>\n• <{summary['reports']['safety_html']}|Safety Report>"
                }
            }
        ]
    }

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(message).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req) as response:
            print(f"Slack notification sent: {response.status}")
    except Exception as e:
        print(f"Failed to send Slack notification: {e}")


if __name__ == "__main__":
    # Local testing
    class MockContext:
        def __init__(self):
            self.function_name = "test"

    result = handler({}, MockContext())
    print(json.dumps(result, indent=2))