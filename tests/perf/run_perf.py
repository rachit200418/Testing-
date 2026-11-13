#!/usr/bin/env python3
"""
Performance Test Runner for Voice Assistant QA Platform.

Runs Locust load tests programmatically and generates HTML report.
"""

import os
import sys
import time
import subprocess
from pathlib import Path


def run_locust(
    host: str = "http://localhost:8000",
    users: int = 10,
    spawn_rate: int = 2,
    run_time: str = "60s",
    html_report: str = "reports/perf/locust_report.html",
    headless: bool = True,
):
    """Run Locust load test."""
    
    # Ensure report directory exists
    Path(html_report).parent.mkdir(parents=True, exist_ok=True)
    
    # Build command
    cmd = [
        "locust",
        "-f", "tests/perf/locustfile.py",
        "--host", host,
        "-u", str(users),
        "-r", str(spawn_rate),
        "-t", run_time,
    ]
    
    if headless:
        cmd.append("--headless")
    
    if html_report:
        cmd.extend(["--html", html_report])
    
    print(f"Running: {' '.join(cmd)}")
    
    # Run locust
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    return result.returncode == 0


def run_locust_with_custom_metrics(
    host: str = "http://localhost:8000",
    users: int = 10,
    spawn_rate: int = 2,
    run_time: str = "60s",
):
    """Run Locust with custom metrics collection."""
    from locust import HttpUser, task, between
    from locust.env import Environment
    from locust.stats import stats_printer, stats_history
    from locust.log import setup_logging
    import gevent
    
    setup_logging("INFO", None)
    
    # Create environment
    env = Environment(user_classes=[VoiceAssistantUser])
    env.create_local_runner()
    
    # Start test
    env.runner.start(users, spawn_rate=spawn_rate)
    
    # Run for specified time
    gevent.spawn_later(parse_time(run_time), lambda: env.runner.quit())
    
    # Start stats printer
    gevent.spawn(stats_printer(env.stats))
    gevent.spawn(stats_history(env.runner))
    
    # Wait for completion
    env.runner.greenlet.join()
    
    # Print summary
    print("\n=== Final Stats ===")
    for name, entry in env.stats.entries.items():
        if entry.num_requests > 0:
            print(f"{name}: {entry.num_requests} reqs, "
                  f"{entry.num_failures} failures, "
                  f"avg={entry.avg_response_time:.0f}ms, "
                  f"p95={entry.get_response_time_percentile(0.95):.0f}ms")
    
    return env.stats


def parse_time(time_str: str) -> int:
    """Parse time string like '60s', '1m', '1h' to seconds."""
    time_str = time_str.lower().strip()
    if time_str.endswith('s'):
        return int(time_str[:-1])
    elif time_str.endswith('m'):
        return int(time_str[:-1]) * 60
    elif time_str.endswith('h'):
        return int(time_str[:-1]) * 3600
    else:
        return int(time_str)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run performance tests")
    parser.add_argument("--host", default="http://localhost:8000", help="Target host")
    parser.add_argument("--users", type=int, default=10, help="Number of users")
    parser.add_argument("--spawn-rate", type=int, default=2, help="Spawn rate per second")
    parser.add_argument("--time", default="60s", help="Run time (e.g., 60s, 1m, 1h)")
    parser.add_argument("--html", default="reports/perf/locust_report.html", help="HTML report path")
    parser.add_argument("--no-headless", action="store_true", help="Run with UI")
    
    args = parser.parse_args()
    
    success = run_locust(
        host=args.host,
        users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.time,
        html_report=args.html,
        headless=not args.no_headless,
    )
    
    sys.exit(0 if success else 1)