"""DuckDB queries for log analysis and data validation."""

import duckdb
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.logging_utils import get_logger

logger = get_logger(__name__)


class LogAnalyzer:
    """Analyze logs using DuckDB."""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.conn = duckdb.connect(":memory:")
        self._register_logs()

    def _register_logs(self):
        """Register log files as a DuckDB table."""
        log_files = list(self.log_dir.rglob("*.log"))
        if not log_files:
            logger.warning(f"No log files found in {self.log_dir}")
            return

        # Create view from JSON lines
        self.conn.execute(f"""
            CREATE OR REPLACE VIEW logs AS
            SELECT * FROM read_json_auto('{self.log_dir}/*.log', 
                format='json_lines',
                ignore_errors=true
            )
        """)

    def query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute SQL query and return results as list of dicts."""
        result = self.conn.execute(sql).fetchall()
        columns = [desc[0] for desc in self.conn.description] if self.conn.description else []
        return [dict(zip(columns, row)) for row in result]

    # ===== PII Validation Queries =====

    def find_unmasked_pii_in_logs(self) -> List[Dict[str, Any]]:
        """Find log entries where PII might not be masked."""
        sql = """
        SELECT 
            timestamp,
            request_id,
            endpoint,
            response_text,
            pii_masked
        FROM logs
        WHERE pii_masked = false
          AND (
            response_text LIKE '%@%' 
            OR response_text LIKE '%[0-9][0-9][0-9]-[0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]%'
            OR response_text LIKE '%[0-9][0-9][0-9][0-9] [0-9][0-9][0-9][0-9] [0-9][0-9][0-9][0-9] [0-9][0-9][0-9][0-9]%'
            OR response_text LIKE '%[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]%'
          )
        ORDER BY timestamp DESC
        LIMIT 100
        """
        return self.query(sql)

    def find_pii_in_transcripts(self) -> List[Dict[str, Any]]:
        """Find PII in transcripts that should be masked."""
        sql = """
        SELECT 
            timestamp,
            request_id,
            transcript,
            pii_masked
        FROM logs
        WHERE transcript IS NOT NULL
          AND (
            transcript LIKE '%@%' 
            OR transcript LIKE '%[0-9][0-9][0-9]-[0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]%'
            OR transcript LIKE '%[0-9][0-9][0-9][0-9] [0-9][0-9][0-9][0-9] [0-9][0-9][0-9][0-9] [0-9][0-9][0-9][0-9]%'
          )
        ORDER BY timestamp DESC
        LIMIT 100
        """
        return self.query(sql)

    # ===== Duplicate Detection =====

    def find_duplicate_requests(self) -> List[Dict[str, Any]]:
        """Find duplicate requests (same input/transcript)."""
        sql = """
        SELECT 
            COALESCE(input_text, transcript) as input,
            COUNT(*) as count,
            MIN(timestamp) as first_seen,
            MAX(timestamp) as last_seen
        FROM logs
        WHERE (input_text IS NOT NULL OR transcript IS NOT NULL)
        GROUP BY COALESCE(input_text, transcript)
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 50
        """
        return self.query(sql)

    def find_duplicate_responses(self) -> List[Dict[str, Any]]:
        """Find duplicate responses."""
        sql = """
        SELECT 
            response_text,
            COUNT(*) as count,
            MIN(timestamp) as first_seen,
            MAX(timestamp) as last_seen
        FROM logs
        WHERE response_text IS NOT NULL
        GROUP BY response_text
        HAVING COUNT(*) > 1
        ORDER BY count DESC
        LIMIT 50
        """
        return self.query(sql)

    # ===== Null/Malformed Field Detection =====

    def find_null_or_malformed_fields(self) -> List[Dict[str, Any]]:
        """Find logs with null or malformed critical fields."""
        sql = """
        SELECT 
            timestamp,
            request_id,
            endpoint,
            CASE WHEN intent IS NULL THEN 'intent' END as missing_intent,
            CASE WHEN latency_ms IS NULL THEN 'latency_ms' END as missing_latency,
            CASE WHEN token_count IS NULL THEN 'token_count' END as missing_tokens,
            CASE WHEN estimated_cost_usd IS NULL THEN 'cost' END as missing_cost
        FROM logs
        WHERE intent IS NULL
           OR latency_ms IS NULL
           OR token_count IS NULL
           OR estimated_cost_usd IS NULL
        ORDER BY timestamp DESC
        LIMIT 100
        """
        return self.query(sql)

    # ===== Latency Drift Analysis =====

    def latency_drift_by_day(self) -> List[Dict[str, Any]]:
        """Analyze latency drift over time (P50, P95, P99 by day)."""
        sql = """
        SELECT 
            date(timestamp) as day,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms.total_ms) as p50_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms.total_ms) as p95_ms,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms.total_ms) as p99_ms,
            AVG(latency_ms.total_ms) as avg_ms,
            COUNT(*) as request_count
        FROM logs
        WHERE latency_ms.total_ms IS NOT NULL
        GROUP BY date(timestamp)
        ORDER BY day
        """
        return self.query(sql)

    def latency_drift_by_stage(self) -> List[Dict[str, Any]]:
        """Analyze latency drift by stage (STT, LLM, TTS) over time."""
        sql = """
        SELECT 
            date(timestamp) as day,
            AVG(latency_ms.stt_ms) as avg_stt_ms,
            AVG(latency_ms.llm_ms) as avg_llm_ms,
            AVG(latency_ms.tts_ms) as avg_tts_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms.stt_ms) as p95_stt_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms.llm_ms) as p95_llm_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms.tts_ms) as p95_tts_ms
        FROM logs
        WHERE latency_ms.stt_ms IS NOT NULL
           OR latency_ms.llm_ms IS NOT NULL
           OR latency_ms.tts_ms IS NOT NULL
        GROUP BY date(timestamp)
        ORDER BY day
        """
        return self.query(sql)

    def endpoint_latency_stats(self) -> List[Dict[str, Any]]:
        """Latency stats by endpoint."""
        sql = """
        SELECT 
            endpoint,
            COUNT(*) as requests,
            AVG(latency_ms.total_ms) as avg_ms,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY latency_ms.total_ms) as p50_ms,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms.total_ms) as p95_ms,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms.total_ms) as p99_ms,
            AVG(latency_ms.stt_ms) as avg_stt_ms,
            AVG(latency_ms.llm_ms) as avg_llm_ms,
            AVG(latency_ms.tts_ms) as avg_tts_ms
        FROM logs
        WHERE latency_ms.total_ms IS NOT NULL
        GROUP BY endpoint
        ORDER BY requests DESC
        """
        return self.query(sql)

    # ===== Hallucination/Quality Drift =====

    def hallucination_drift_by_day(self) -> List[Dict[str, Any]]:
        """Track hallucination score drift over time (from eval reports)."""
        # This would query evaluation reports stored as JSON
        # For now, placeholder - would need eval reports in DuckDB
        sql = """
        SELECT 
            'eval_reports_not_loaded' as note
        """
        return self.query(sql)

    # ===== Cost Analysis =====

    def cost_per_day(self) -> List[Dict[str, Any]]:
        """Daily cost analysis."""
        sql = """
        SELECT 
            date(timestamp) as day,
            SUM(estimated_cost_usd) as total_cost_usd,
            AVG(estimated_cost_usd) as avg_cost_per_request,
            COUNT(*) as request_count,
            SUM(token_count) as total_tokens
        FROM logs
        WHERE estimated_cost_usd IS NOT NULL
        GROUP BY date(timestamp)
        ORDER BY day
        """
        return self.query(sql)

    def cost_by_model(self) -> List[Dict[str, Any]]:
        """Cost breakdown by model (would need model info in logs)."""
        sql = """
        SELECT 
            'model_not_in_logs' as note
        """
        return self.query(sql)

    # ===== Error Analysis =====

    def error_rate_by_day(self) -> List[Dict[str, Any]]:
        """Error rate trends over time."""
        sql = """
        SELECT 
            date(timestamp) as day,
            COUNT(*) as total_requests,
            SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count,
            SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as error_rate
        FROM logs
        GROUP BY date(timestamp)
        ORDER BY day
        """
        return self.query(sql)

    def errors_by_type(self) -> List[Dict[str, Any]]:
        """Error breakdown by type."""
        sql = """
        SELECT 
            error,
            COUNT(*) as count
        FROM logs
        WHERE error IS NOT NULL
        GROUP BY error
        ORDER BY count DESC
        LIMIT 20
        """
        return self.query(sql)

    # ===== Intent/Slot Accuracy =====

    def intent_distribution(self) -> List[Dict[str, Any]]:
        """Distribution of intents over time."""
        sql = """
        SELECT 
            date(timestamp) as day,
            intent,
            COUNT(*) as count
        FROM logs
        WHERE intent IS NOT NULL
        GROUP BY date(timestamp), intent
        ORDER BY day, count DESC
        """
        return self.query(sql)

    # ===== Session Analysis =====

    def session_stats(self) -> List[Dict[str, Any]]:
        """Session-level statistics."""
        sql = """
        SELECT 
            session_id,
            COUNT(*) as turns,
            MIN(timestamp) as started_at,
            MAX(timestamp) as ended_at,
            DATE_DIFF('minute', MIN(timestamp), MAX(timestamp)) as duration_minutes
        FROM logs
        WHERE session_id IS NOT NULL
        GROUP BY session_id
        HAVING COUNT(*) > 1
        ORDER BY turns DESC
        LIMIT 50
        """
        return self.query(sql)

    def close(self):
        """Close DuckDB connection."""
        self.conn.close()


def run_all_validation_queries(log_dir: str = "logs") -> Dict[str, List[Dict]]:
    """Run all validation queries and return results."""
    analyzer = LogAnalyzer(log_dir)
    results = {}

    try:
        # PII checks
        results["unmasked_pii_in_responses"] = analyzer.find_unmasked_pii_in_logs()
        results["pii_in_transcripts"] = analyzer.find_pii_in_transcripts()

        # Duplicates
        results["duplicate_requests"] = analyzer.find_duplicate_requests()
        results["duplicate_responses"] = analyzer.find_duplicate_responses()

        # Null fields
        results["null_malformed_fields"] = analyzer.find_null_or_malformed_fields()

        # Latency
        results["latency_drift_by_day"] = analyzer.latency_drift_by_day()
        results["latency_drift_by_stage"] = analyzer.latency_drift_by_stage()
        results["endpoint_latency_stats"] = analyzer.endpoint_latency_stats()

        # Cost
        results["cost_per_day"] = analyzer.cost_per_day()

        # Errors
        results["error_rate_by_day"] = analyzer.error_rate_by_day()
        results["errors_by_type"] = analyzer.errors_by_type()

        # Intent
        results["intent_distribution"] = analyzer.intent_distribution()

        # Sessions
        results["session_stats"] = analyzer.session_stats()

    finally:
        analyzer.close()

    return results


def export_validation_report(log_dir: str = "logs", output_dir: str = "reports/validation"):
    """Run all queries and export to JSON files."""
    import json

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = run_all_validation_queries(log_dir)

    for name, data in results.items():
        file_path = output_path / f"{name}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Exported {len(data)} rows to {file_path}")

    # Summary
    summary = {
        "generated_at": str(datetime.utcnow()),
        "checks": {k: len(v) for k, v in results.items()},
        "issues_found": sum(len(v) for v in results.values()),
    }

    with open(output_path / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    return summary


if __name__ == "__main__":
    from datetime import datetime
    export_validation_report()