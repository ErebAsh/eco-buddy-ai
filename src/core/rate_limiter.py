import os
import time
import sqlite3
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass
from src.core.database_connection import database_connection
from src.core.errors import RateLimitExceeded

DB_NAME = os.getenv("ECO_BUDDY_DB", "eco_buddy.db")

@dataclass
class RateLimitPolicy:
    role: str
    limit: int
    window_seconds: int = 60

class SlidingWindowCounter:
    """
    Sliding Window Counter rate limiter over SQLite.
    Tracks requests in discrete windows and estimates the current rate 
    based on the overlap with the previous window.
    """
    @staticmethod
    def check_limit(key_id: int, policy: RateLimitPolicy, endpoint: str) -> Tuple[bool, Dict[str, str]]:
        now = time.time()
        window_sec = policy.window_seconds
        limit = policy.limit
        
        current_window_start = int(now // window_sec) * window_sec
        previous_window_start = current_window_start - window_sec
        
        overlap_weight = (window_sec - (now % window_sec)) / float(window_sec)
        
        is_allowed = False
        remaining = 0
        retry_after = 0
        
        with database_connection(DB_NAME) as conn:
            conn.execute("BEGIN EXCLUSIVE TRANSACTION")
            cursor = conn.cursor()
            
            # Clean up old windows to keep the table small
            cursor.execute(
                "DELETE FROM api_rate_limits WHERE key_id = ? AND window_start < ?",
                (key_id, previous_window_start)
            )
            
            # Get current and previous window counts
            cursor.execute(
                "SELECT window_start, request_count FROM api_rate_limits WHERE key_id = ?",
                (key_id,)
            )
            rows = cursor.fetchall()
            
            counts = {r[0]: r[1] for r in rows}
            prev_count = counts.get(previous_window_start, 0)
            curr_count = counts.get(current_window_start, 0)
            
            # Sliding window estimation
            estimated_count = curr_count + (prev_count * overlap_weight)
            
            if estimated_count < limit:
                is_allowed = True
                curr_count += 1
                cursor.execute(
                    """
                    INSERT INTO api_rate_limits (key_id, window_start, request_count) 
                    VALUES (?, ?, 1)
                    ON CONFLICT(key_id, window_start) 
                    DO UPDATE SET request_count = request_count + 1
                    """, (key_id, current_window_start)
                )
                remaining = int(limit - estimated_count - 1)
                if remaining < 0:
                    remaining = 0
            else:
                is_allowed = False
                remaining = 0
                retry_after = int(window_sec - (now % window_sec))
                if retry_after <= 0:
                    retry_after = 1
                    
            # Always log the request in rate_limit_log for usage stats
            status_code = 200 if is_allowed else 429
            cursor.execute(
                "INSERT INTO rate_limit_log (key_id, endpoint, timestamp, status_code) VALUES (?, ?, ?, ?)",
                (key_id, endpoint, now, status_code)
            )
            conn.commit()
            
        reset_time = int(current_window_start + window_sec)
        
        headers = RateLimitMiddleware.build_headers(limit, remaining, reset_time)
        if not is_allowed:
            headers["Retry-After"] = str(retry_after)
            
        return is_allowed, headers

class RateLimitMiddleware:
    """Middleware for checking rate limits and adding headers."""
    
    @staticmethod
    def build_headers(limit: int, remaining: int, reset: int) -> Dict[str, str]:
        """Utility function to inject rate limit headers."""
        return {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset)
        }

    @staticmethod
    def check_request(key_id: int, rate_limit: int, role: str, endpoint: str) -> Dict[str, str]:
        """
        Check rate limit and return headers. 
        Raises RateLimitExceeded if limit is reached.
        """
        # Create policy based on quota
        policy = RateLimitPolicy(role=role, limit=rate_limit)
        
        is_allowed, headers = SlidingWindowCounter.check_limit(key_id, policy, endpoint)
        
        if not is_allowed:
            # We raise RateLimitExceeded so the caller can short-circuit
            raise RateLimitExceeded("Rate limit exceeded.", details=str(headers))
            
        return headers

    @staticmethod
    def get_usage_stats(key_id: Optional[int] = None, limit: int = 100) -> list:
        """Fetch rate limit logs, optionally filtered by key_id."""
        with database_connection(DB_NAME) as conn:
            cursor = conn.cursor()
            if key_id:
                cursor.execute(
                    "SELECT timestamp, endpoint, status_code FROM rate_limit_log WHERE key_id = ? ORDER BY timestamp DESC LIMIT ?", 
                    (key_id, limit)
                )
            else:
                cursor.execute(
                    "SELECT key_id, timestamp, endpoint, status_code FROM rate_limit_log ORDER BY timestamp DESC LIMIT ?", 
                    (limit,)
                )
            
            rows = cursor.fetchall()
            
            if key_id:
                return [{"timestamp": r[0], "endpoint": r[1], "status_code": r[2]} for r in rows]
            else:
                return [{"key_id": r[0], "timestamp": r[1], "endpoint": r[2], "status_code": r[3]} for r in rows]
