"""S3 Logging utilities for uploading logs and reports."""

import boto3
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)


class S3LogUploader:
    """Upload logs and reports to S3."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    def _get_client(self):
        """Get or create S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                region_name=self.settings.s3_region,
                aws_access_key_id=self.settings.s3_access_key,
                aws_secret_access_key=self.settings.s3_secret_key,
            )
        return self._client

    def upload_file(self, local_path: Path, s3_key: str) -> bool:
        """Upload a single file to S3."""
        if not self.settings.enable_s3_logging or not self.settings.s3_bucket:
            logger.debug("S3 logging disabled, skipping upload")
            return False

        try:
            client = self._get_client()
            client.upload_file(str(local_path), self.settings.s3_bucket, s3_key)
            logger.info(f"Uploaded {local_path} to s3://{self.settings.s3_bucket}/{s3_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {local_path} to S3: {e}")
            return False

    def upload_directory(self, local_dir: Path, s3_prefix: str) -> int:
        """Upload all files in a directory to S3."""
        if not self.settings.enable_s3_logging or not self.settings.s3_bucket:
            return 0

        uploaded = 0
        for file_path in local_dir.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(local_dir)
                s3_key = f"{s3_prefix}/{relative}"
                if self.upload_file(file_path, s3_key):
                    uploaded += 1
        return uploaded

    def upload_logs(self, date_str: str = None) -> int:
        """Upload log files for a specific date."""
        if date_str is None:
            date_str = datetime.utcnow().strftime("%Y/%m/%d")

        logs_dir = Path("logs")
        if not logs_dir.exists():
            return 0

        return self.upload_directory(logs_dir, f"logs/{date_str}")

    def upload_reports(self, date_str: str = None) -> int:
        """Upload report files for a specific date."""
        if date_str is None:
            date_str = datetime.utcnow().strftime("%Y-%m-%d")

        reports_dir = Path("reports")
        if not reports_dir.exists():
            return 0

        return self.upload_directory(reports_dir, f"reports/{date_str}")

    def upload_eval_artifacts(self, run_id: str) -> int:
        """Upload evaluation artifacts."""
        eval_dir = Path("reports/llm_eval")
        if not eval_dir.exists():
            return 0

        return self.upload_directory(eval_dir, f"eval/{run_id}")


def upload_logs_if_enabled() -> int:
    """Convenience function to upload logs if S3 logging is enabled."""
    settings = get_settings()
    if not settings.enable_s3_logging:
        return 0

    uploader = S3LogUploader()
    return uploader.upload_logs()


def upload_reports_if_enabled() -> int:
    """Convenience function to upload reports if S3 logging is enabled."""
    settings = get_settings()
    if not settings.enable_s3_logging:
        return 0

    uploader = S3LogUploader()
    return uploader.upload_reports()


class S3LogReader:
    """Read logs from S3 for analysis."""

    def __init__(self):
        self.settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                region_name=self.settings.s3_region,
                aws_access_key_id=self.settings.s3_access_key,
                aws_secret_access_key=self.settings.s3_secret_key,
            )
        return self._client

    def list_log_files(self, prefix: str = "logs/") -> list[str]:
        """List log files in S3."""
        if not self.settings.s3_bucket:
            return []

        client = self._get_client()
        paginator = client.get_paginator("list_objects_v2")
        keys = []

        for page in paginator.paginate(Bucket=self.settings.s3_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])

        return keys

    def download_log_file(self, s3_key: str, local_path: Path) -> bool:
        """Download a log file from S3."""
        if not self.settings.s3_bucket:
            return False

        try:
            client = self._get_client()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            client.download_file(self.settings.s3_bucket, s3_key, str(local_path))
            return True
        except Exception as e:
            logger.error(f"Failed to download {s3_key}: {e}")
            return False