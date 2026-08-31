import os
import uuid
import time
import sqlite3
import pytest

from src.core.rate_limiter import RateLimitMiddleware, SlidingWindowCounter, RateLimitPolicy
from src.core.errors import RateLimitExceeded
from src.core.api_auth import init_api_keys_db, generate_api_key
from src.core.database_connection import database_connection
import migrations.migrate_v17

@pytest.fixture
def setup_isolated_db() -> str:
    """Fixture to create and configure an isolated, unique SQLite test database."""
    unique_db_name = f"test_eco_buddy_{uuid.uuid4().hex[:8]}.db"
    
    # Store original and set new env var
    original_db = os.environ.get("ECO_BUDDY_DB")
    os.environ["ECO_BUDDY_DB"] = unique_db_name

    import src.core.rate_limiter as rl
    import src.core.api_auth as auth
    
    rl.DB_NAME = unique_db_name
    auth.DB_NAME = unique_db_name

    # Initialize the tables
    init_api_keys_db()
    
    with database_connection(unique_db_name) as conn:
        migrations.migrate_v17.migrate(conn)
    
    yield unique_db_name

    # Cleanup
    if os.path.exists(unique_db_name):
        try:
            os.remove(unique_db_name)
        except OSError:
            pass
            
    if original_db is not None:
        os.environ["ECO_BUDDY_DB"] = original_db
    else:
        del os.environ["ECO_BUDDY_DB"]


def test_rate_limiter_allows_under_limit(setup_isolated_db):
    key_info = generate_api_key("Test App", rate_limit=5)
    key_id = key_info["id"]
    
    headers = RateLimitMiddleware.check_request(key_id, rate_limit=5, role="developer", endpoint="/test")
    
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert int(headers["X-RateLimit-Remaining"]) == 4

def test_rate_limiter_blocks_over_limit(setup_isolated_db):
    key_info = generate_api_key("Test App", rate_limit=2)
    key_id = key_info["id"]
    
    # Allowed
    RateLimitMiddleware.check_request(key_id, rate_limit=2, role="developer", endpoint="/test")
    RateLimitMiddleware.check_request(key_id, rate_limit=2, role="developer", endpoint="/test")
    
    # Blocked
    with pytest.raises(RateLimitExceeded) as exc_info:
        RateLimitMiddleware.check_request(key_id, rate_limit=2, role="developer", endpoint="/test")
        
    assert "Rate limit exceeded" in str(exc_info.value)
    
    # The details field should contain the headers including Retry-After
    import ast
    details = ast.literal_eval(exc_info.value.details)
    assert "Retry-After" in details
    assert "X-RateLimit-Remaining" in details
    assert int(details["X-RateLimit-Remaining"]) == 0

def test_rate_limiter_zero_limit(setup_isolated_db):
    key_info = generate_api_key("Test App", rate_limit=0)
    key_id = key_info["id"]
    
    with pytest.raises(RateLimitExceeded):
        RateLimitMiddleware.check_request(key_id, rate_limit=0, role="developer", endpoint="/test")

def test_rate_limiter_stats(setup_isolated_db):
    key_info = generate_api_key("Test App", rate_limit=10)
    key_id = key_info["id"]
    
    RateLimitMiddleware.check_request(key_id, rate_limit=10, role="developer", endpoint="/test1")
    RateLimitMiddleware.check_request(key_id, rate_limit=10, role="developer", endpoint="/test2")
    
    stats = RateLimitMiddleware.get_usage_stats(key_id=key_id)
    assert len(stats) == 2
    assert stats[0]["endpoint"] == "/test2"
    assert stats[1]["endpoint"] == "/test1"
