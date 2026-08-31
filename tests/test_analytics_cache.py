"""
Comprehensive Unit Tests for Analytics Cache
Tests caching behavior, expiration, edge cases, and decorator usage.
"""

import time
import pytest
from src.utils.analytics_cache import TTLCache, cached, cache_analytics_data, get_cached_analytics_data


# ==============================================================================
# SECTION 1: Testing Basic Cache Operations
# ==============================================================================

class TestBasicCacheOperations:
    def test_set_and_get(self):
        """Should store and retrieve values."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_get_missing_key(self):
        """Should return None for missing keys."""
        cache = TTLCache(ttl_seconds=60)
        assert cache.get("missing") is None

    def test_overwrite_value(self):
        """Should allow overwriting values."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key", "value1")
        cache.set("key", "value2")
        assert cache.get("key") == "value2"


# ==============================================================================
# SECTION 2: Testing Cache Expiration
# ==============================================================================

class TestExpiration:
    def test_value_expires_after_ttl(self):
        """Should return None after TTL expires."""
        cache = TTLCache(ttl_seconds=1)
        cache.set("key", "value")
        time.sleep(1.2)
        assert cache.get("key") is None

    def test_value_removed_after_expiry(self):
        """Should remove expired keys from the store."""
        cache = TTLCache(ttl_seconds=1)
        cache.set("key", "value")
        time.sleep(1.2)
        cache.get("key")  # Triggers cleanup
        assert "key" not in cache.cache_store

    def test_zero_ttl(self):
        """Should expire immediately with zero TTL."""
        cache = TTLCache(ttl_seconds=0)
        cache.set("key", "value")
        time.sleep(0.1)
        assert cache.get("key") is None


# ==============================================================================
# SECTION 3: Testing the Cached Decorator
# ==============================================================================

class TestCachedDecorator:
    def test_function_called_once(self):
        """Should only call the function once when using cache."""
        call_count = 0

        @cached(ttl_seconds=60)
        def my_function():
            nonlocal call_count
            call_count += 1
            return call_count

        # Call twice within TTL
        assert my_function() == 1
        assert my_function() == 1
        assert call_count == 1

    def test_function_called_again_after_expiry(self):
        """Should call the function again after TTL expires."""
        call_count = 0

        @cached(ttl_seconds=1)
        def my_function():
            nonlocal call_count
            call_count += 1
            return call_count

        assert my_function() == 1
        time.sleep(1.2)
        assert my_function() == 2
        assert call_count == 2

    def test_decorator_works_with_arguments(self):
        """Should cache based on arguments."""
        call_count = 0

        @cached(ttl_seconds=60)
        def add(a, b):
            nonlocal call_count
            call_count += 1
            return a + b

        assert add(1, 2) == 3
        assert add(1, 2) == 3
        assert add(2, 3) == 5
        assert call_count == 2  # Called twice because inputs are different


# ==============================================================================
# SECTION 4: Testing Global Cache
# ==============================================================================

class TestGlobalCache:
    def test_store_and_retrieve(self):
        """Should store and retrieve from global cache."""
        cache_analytics_data("user_stats", {"total": 10})
        assert get_cached_analytics_data("user_stats") == {"total": 10}

    def test_missing_global_key(self):
        """Should return None for missing global key."""
        assert get_cached_analytics_data("missing_data") is None

    def test_global_cache_ttl(self):
        """Global cache should expire."""
        cache_analytics_data("temp_data", "value")
        time.sleep(310)
        assert get_cached_analytics_data("temp_data") is None


# ==============================================================================
# SECTION 5: Testing Edge Cases
# ==============================================================================

class TestEdgeCases:
    def test_cache_none_value(self):
        """Should handle caching None values."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key", None)
        assert cache.get("key") is None

    def test_cache_empty_string(self):
        """Should handle caching empty strings."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key", "")
        assert cache.get("key") == ""

    def test_cache_lists_and_dicts(self):
        """Should handle complex data types."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("list", [1, 2, 3])
        cache.set("dict", {"a": 1})
        assert cache.get("list") == [1, 2, 3]
        assert cache.get("dict") == {"a": 1}

    def test_cache_with_many_keys(self):
        """Should handle multiple keys."""
        cache = TTLCache(ttl_seconds=60)
        for i in range(100):
            cache.set(f"key_{i}", i)
        assert cache.get("key_99") == 99


# ==============================================================================
# SECTION 6: Performance Tests
# ==============================================================================

class TestPerformance:
    def test_cache_reduces_computation_time(self):
        """Cache should make repeated calls faster."""
        import time

        @cached(ttl_seconds=60)
        def slow_function():
            time.sleep(0.5)  # Simulate heavy computation
            return 42

        start_time = time.time()
        result = slow_function()
        first_call_time = time.time() - start_time

        start_time = time.time()
        result = slow_function()
        second_call_time = time.time() - start_time

        assert result == 42
        assert second_call_time < first_call_time