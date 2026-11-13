-- Athena DDL for Voice Assistant QA Platform Logs
-- Run these in Athena console to create external tables over S3 logs

-- 1. Main logs table (partitioned by date)
CREATE EXTERNAL TABLE IF NOT EXISTS voice_assistant_logs (
    `timestamp` string,
    `request_id` string,
    `session_id` string,
    `endpoint` string,
    `input_text` string,
    `transcript` string,
    `response_text` string,
    `intent` string,
    `slots` map<string, string>,
    `tool_calls` array<struct<name:string, arguments:map<string,string>, result:map<string,string>, error:string>>,
    `latency_ms` struct<stt_ms:int, llm_ms:int, tts_ms:int, total_ms:int>,
    `token_count` int,
    `estimated_cost_usd` double,
    `pii_masked` boolean,
    `error` string
)
PARTITIONED BY (
    `year` string,
    `month` string,
    `day` string
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
WITH SERDEPROPERTIES (
    'ignore.malformed.json' = 'true'
)
LOCATION 's3://${BUCKET_NAME}/logs/'
TBLPROPERTIES (
    'projection.enabled' = 'true',
    'projection.year.type' = 'integer',
    'projection.year.range' = '2024,2030',
    'projection.month.type' = 'integer',
    'projection.month.range' = '1,12',
    'projection.month.digits' = '2',
    'projection.day.type' = 'integer',
    'projection.day.range' = '1,31',
    'projection.day.digits' = '2',
    'storage.location.template' = 's3://${BUCKET_NAME}/logs/${year}/${month}/${day}/'
);

-- 2. Evaluation reports table
CREATE EXTERNAL TABLE IF NOT EXISTS voice_assistant_eval_reports (
    `run_id` string,
    `timestamp` string,
    `case_id` string,
    `input` string,
    `expected_intent` string,
    `actual_intent` string,
    `intent_match` boolean,
    `expected_slots` map<string, string>,
    `actual_slots` map<string, string>,
    `slot_accuracy` double,
    `relevancy_score` double,
    `faithfulness_score` double,
    `hallucination_score` double,
    `confirmation_score` double,
    `refusal_score` double,
    `pii_masking_score` double,
    `latency_total_ms` int,
    `latency_stt_ms` int,
    `latency_llm_ms` int,
    `latency_tts_ms` int,
    `cost_usd` double
)
PARTITIONED BY (
    `run_date` string
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://${BUCKET_NAME}/eval/';

-- 3. Safety test results table
CREATE EXTERNAL TABLE IF NOT EXISTS voice_assistant_safety_results (
    `run_id` string,
    `timestamp` string,
    `category` string,
    `attack` string,
    `blocked` boolean,
    `response` string,
    `intent` string
)
PARTITIONED BY (
    `run_date` string
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://${BUCKET_NAME}/reports/safety/';

-- 4. Performance test results table
CREATE EXTERNAL TABLE IF NOT EXISTS voice_assistant_perf_results (
    `run_id` string,
    `timestamp` string,
    `endpoint` string,
    `requests` int,
    `failures` int,
    `avg_ms` double,
    `p50_ms` double,
    `p95_ms` double,
    `p99_ms` double,
    `error_rate` double,
    `throughput_rps` double
)
PARTITIONED BY (
    `run_date` string
)
ROW FORMAT SERDE 'org.openx.data.jsonserde.JsonSerDe'
LOCATION 's3://${BUCKET_NAME}/reports/perf/';


-- ============================================================
-- VALIDATION QUERIES (Run in Athena after table creation)
-- ============================================================

-- 1. Find unmasked PII in logs
SELECT 
    timestamp,
    request_id,
    endpoint,
    response_text,
    pii_masked
FROM voice_assistant_logs
WHERE pii_masked = false
  AND (
    response_text LIKE '%@%' 
    OR response_text LIKE '%[0-9][0-9][0-9]-[0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]%'
    OR regexp_like(response_text, '[0-9]{4} [0-9]{4} [0-9]{4} [0-9]{4}')
    OR regexp_like(response_text, '[0-9]{13,16}')
  )
ORDER BY timestamp DESC
LIMIT 100;

-- 2. Find duplicate requests
SELECT 
    COALESCE(input_text, transcript) as input,
    COUNT(*) as count,
    MIN(timestamp) as first_seen,
    MAX(timestamp) as last_seen
FROM voice_assistant_logs
WHERE input_text IS NOT NULL OR transcript IS NOT NULL
GROUP BY COALESCE(input_text, transcript)
HAVING COUNT(*) > 1
ORDER BY count DESC
LIMIT 50;

-- 3. Find null/malformed fields
SELECT 
    timestamp,
    request_id,
    endpoint,
    CASE WHEN intent IS NULL THEN 'intent' END as missing_intent,
    CASE WHEN latency_ms.total_ms IS NULL THEN 'latency' END as missing_latency,
    CASE WHEN token_count IS NULL THEN 'tokens' END as missing_tokens,
    CASE WHEN estimated_cost_usd IS NULL THEN 'cost' END as missing_cost
FROM voice_assistant_logs
WHERE intent IS NULL
   OR latency_ms.total_ms IS NULL
   OR token_count IS NULL
   OR estimated_cost_usd IS NULL
ORDER BY timestamp DESC
LIMIT 100;

-- 4. Latency drift by day (P50, P95, P99)
SELECT 
    date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as day,
    approx_percentile(latency_ms.total_ms, 0.50) as p50_ms,
    approx_percentile(latency_ms.total_ms, 0.95) as p95_ms,
    approx_percentile(latency_ms.total_ms, 0.99) as p99_ms,
    AVG(latency_ms.total_ms) as avg_ms,
    COUNT(*) as request_count
FROM voice_assistant_logs
WHERE latency_ms.total_ms IS NOT NULL
GROUP BY year, month, day
ORDER BY year, month, day;

-- 5. Latency drift by stage (STT, LLM, TTS)
SELECT 
    date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as day,
    AVG(latency_ms.stt_ms) as avg_stt_ms,
    AVG(latency_ms.llm_ms) as avg_llm_ms,
    AVG(latency_ms.tts_ms) as avg_tts_ms,
    approx_percentile(latency_ms.stt_ms, 0.95) as p95_stt_ms,
    approx_percentile(latency_ms.llm_ms, 0.95) as p95_llm_ms,
    approx_percentile(latency_ms.tts_ms, 0.95) as p95_tts_ms
FROM voice_assistant_logs
WHERE latency_ms.stt_ms IS NOT NULL
   OR latency_ms.llm_ms IS NOT NULL
   OR latency_ms.tts_ms IS NOT NULL
GROUP BY year, month, day
ORDER BY year, month, day;

-- 6. Cost per day
SELECT 
    date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as day,
    SUM(estimated_cost_usd) as total_cost_usd,
    AVG(estimated_cost_usd) as avg_cost_per_request,
    COUNT(*) as request_count,
    SUM(token_count) as total_tokens
FROM voice_assistant_logs
WHERE estimated_cost_usd IS NOT NULL
GROUP BY year, month, day
ORDER BY year, month, day;

-- 7. Error rate by day
SELECT 
    date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as day,
    COUNT(*) as total_requests,
    SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as error_count,
    SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) * 1.0 / COUNT(*) as error_rate
FROM voice_assistant_logs
GROUP BY year, month, day
ORDER BY year, month, day;

-- 8. Errors by type
SELECT 
    error,
    COUNT(*) as count
FROM voice_assistant_logs
WHERE error IS NOT NULL
GROUP BY error
ORDER BY count DESC
LIMIT 20;

-- 9. Intent distribution over time
SELECT 
    date_parse(concat(year, '-', month, '-', day), '%Y-%m-%d') as day,
    intent,
    COUNT(*) as count
FROM voice_assistant_logs
WHERE intent IS NOT NULL
GROUP BY year, month, day, intent
ORDER BY year, month, day, count DESC;

-- 10. Endpoint latency stats
SELECT 
    endpoint,
    COUNT(*) as requests,
    AVG(latency_ms.total_ms) as avg_ms,
    approx_percentile(latency_ms.total_ms, 0.50) as p50_ms,
    approx_percentile(latency_ms.total_ms, 0.95) as p95_ms,
    approx_percentile(latency_ms.total_ms, 0.99) as p99_ms,
    AVG(latency_ms.stt_ms) as avg_stt_ms,
    AVG(latency_ms.llm_ms) as avg_llm_ms,
    AVG(latency_ms.tts_ms) as avg_tts_ms
FROM voice_assistant_logs
WHERE latency_ms.total_ms IS NOT NULL
GROUP BY endpoint
ORDER BY requests DESC;

-- 11. Hallucination score drift (from eval reports)
SELECT 
    date_parse(run_date, '%Y-%m-%d') as day,
    AVG(hallucination_score) as avg_hallucination,
    AVG(faithfulness_score) as avg_faithfulness,
    AVG(relevancy_score) as avg_relevancy,
    AVG(confirmation_score) as avg_confirmation,
    AVG(refusal_score) as avg_refusal,
    AVG(pii_masking_score) as avg_pii_masking
FROM voice_assistant_eval_reports
GROUP BY run_date
ORDER BY run_date;

-- 12. Safety attack success rate by category
SELECT 
    date_parse(run_date, '%Y-%m-%d') as day,
    category,
    SUM(CASE WHEN blocked THEN 1 ELSE 0 END) as blocked,
    COUNT(*) as total,
    (COUNT(*) - SUM(CASE WHEN blocked THEN 1 ELSE 0 END)) * 1.0 / COUNT(*) as attack_success_rate
FROM voice_assistant_safety_results
GROUP BY run_date, category
ORDER BY run_date, category;

-- 13. Performance test trends
SELECT 
    date_parse(run_date, '%Y-%m-%d') as day,
    endpoint,
    AVG(p95_ms) as avg_p95_ms,
    AVG(error_rate) as avg_error_rate,
    AVG(throughput_rps) as avg_throughput
FROM voice_assistant_perf_results
GROUP BY run_date, endpoint
ORDER BY run_date, endpoint;

-- 14. Session analysis
SELECT 
    session_id,
    COUNT(*) as turns,
    MIN(timestamp) as started_at,
    MAX(timestamp) as ended_at,
    date_diff('minute', MIN(timestamp), MAX(timestamp)) as duration_minutes
FROM voice_assistant_logs
WHERE session_id IS NOT NULL
GROUP BY session_id
HAVING COUNT(*) > 1
ORDER BY turns DESC
LIMIT 50;