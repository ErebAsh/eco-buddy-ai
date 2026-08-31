import pytest
import time
import json
from datetime import datetime, timezone, timedelta
from src.business.sustainability_api import process_api_request, _route
from src.business.api_usage_meter import usage_meter, UsageRecord, flush_usage_records_task
from src.business.api_usage_aggregator import UsageAggregator
from src.business.api_billing_tiers import BillingTierCalculator
from src.core.database_connection import database_connection
import src.core.database as database

@pytest.fixture(autouse=True)
def setup_metering_tables():
    # Setup test DB tables
    from migrations.migrate_v18 import migrate
    with database_connection(database.DB_NAME) as conn:
        migrate(conn)
        
        # Clear out existing test data
        conn.execute("DELETE FROM api_usage_records")
        conn.execute("DELETE FROM api_usage_rollups")
        conn.execute("DELETE FROM api_billing_tiers")
        
        # Insert a test billing tier mapping
        conn.execute(
            "INSERT INTO api_billing_tiers (key_id, tier_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ("test_pro_key", "pro", datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat())
        )
        conn.commit()

def test_api_metering_hook():
    # Create an API request
    headers = {}
    body = {}
    
    # Clean the buffer before tests
    usage_meter._buffer.clear()

    # Send request
    res = process_api_request("GET", _route("/health"), headers, body=body)
    assert res[0] == 200
    
    # We should have one usage record in the buffer
    assert len(usage_meter._buffer) == 1
    
    record = usage_meter._buffer[-1]
    assert record.endpoint == _route("/health")
    assert record.method == "GET"
    assert record.status_code == 200
    assert record.latency >= 0
    assert record.payload_size > 0
    
    # Clear buffer for next tests
    usage_meter._buffer.clear()

def test_background_flush_task():
    records = [
        {"key_id": "test_key", "endpoint": "/api/v1/health", "method": "GET", 
         "status_code": 200, "latency": 15.5, "payload_size": 100, 
         "timestamp": datetime.now(timezone.utc).isoformat()}
    ]
    
    # Run the flush task directly
    flush_usage_records_task(records)
    
    # Check if record is in database
    with database_connection(database.DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM api_usage_records WHERE key_id = 'test_key'")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["latency"] == 15.5

def test_usage_aggregator():
    now = datetime.now(timezone.utc)
    records = []
    
    # Insert 10 records with varying latencies
    latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    
    for i, latency in enumerate(latencies):
        status = 200 if i < 8 else 400
        records.append({
            "key_id": "test_agg_key", 
            "endpoint": "/api/v1/test", 
            "method": "POST", 
            "status_code": status, 
            "latency": latency, 
            "payload_size": 100, 
            "timestamp": now.isoformat()
        })
        
    flush_usage_records_task(records)
    
    # Aggregate daily
    summary = UsageAggregator.aggregate_daily("test_agg_key")
    
    assert summary["total_requests"] == 10
    assert summary["error_rate"] == 0.2
    
    # Percentiles: latencies are sorted: 10, 20, 30, 40, 50, 60, 70, 80, 90, 100
    # p50 index: int(10 * 0.5) = 5 -> 60.0
    # p95 index: int(10 * 0.95) = 9 -> 100.0
    # p99 index: int(10 * 0.99) = 9 -> 100.0
    
    assert summary["p50_latency"] == 60.0
    assert summary["p95_latency"] == 100.0
    assert summary["p99_latency"] == 100.0

def test_billing_tiers():
    # test_pro_key is 'pro' which has 100,000 limit
    status = BillingTierCalculator.check_billing_status("test_pro_key", 50000)
    assert status["tier"] == "pro"
    assert status["is_over_limit"] is False
    assert status["status"] == "active"
    
    status = BillingTierCalculator.check_billing_status("test_pro_key", 105000)
    assert status["tier"] == "pro"
    assert status["is_over_limit"] is True
    assert status["overage_allowed"] is True
    assert status["overage_count"] == 5000
    assert status["status"] == "active"

    # Default key is 'free' which has 1,000 limit
    status = BillingTierCalculator.check_billing_status("unknown_key", 1500)
    assert status["tier"] == "free"
    assert status["is_over_limit"] is True
    assert status["overage_allowed"] is False
    assert status["overage_count"] == 500
    assert status["status"] == "blocked"
