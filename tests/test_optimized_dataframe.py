"""
Comprehensive Unit Tests for Optimized DataFrame Operations
Issue: #1282
Tests vectorized operations, edge cases, and performance.
"""

import pandas as pd
import pytest
from src.utils.optimized_dataframe_utils import process_user_data_optimized, calculate_dashboard_metrics_optimized


# ==============================================================================
# SECTION 1: Testing Basic DataFrame Processing
# ==============================================================================

class TestProcessUserData:
    def test_basic_processing(self):
        """Should process a basic DataFrame."""
        df = pd.DataFrame({
            "user_id": [1, 2, 3],
            "age": [20, 25, 30],
            "score": [10, 20, 30],
            "active": [True, False, True]
        })
        result, avg_age = process_user_data_optimized(df)
        assert len(result) == 3

    def test_score_increases_for_active_users(self):
        """Active users should get +1 score."""
        df = pd.DataFrame({
            "user_id": [1, 2],
            "age": [20, 25],
            "score": [10, 20],
            "active": [True, False]
        })
        result, _ = process_user_data_optimized(df)
        assert result.loc[result["user_id"] == 1, "score"].values[0] == 11
        assert result.loc[result["user_id"] == 2, "score"].values[0] == 20

    def test_filters_users_below_18(self):
        """Users below 18 should be removed."""
        df = pd.DataFrame({
            "user_id": [1, 2, 3],
            "age": [15, 25, 17],
            "score": [10, 20, 30],
            "active": [True, False, True]
        })
        result, _ = process_user_data_optimized(df)
        assert len(result) == 1
        assert result.iloc[0]["user_id"] == 2

    def test_missing_columns_added(self):
        """Missing columns should be added with default 0 values."""
        df = pd.DataFrame({
            "user_id": [1, 2],
            "score": [10, 20]
        })
        result, _ = process_user_data_optimized(df)
        assert "age" in result.columns
        assert "active" in result.columns


# ==============================================================================
# SECTION 2: Testing Edge Cases
# ==============================================================================

class TestEdgeCases:
    def test_empty_dataframe(self):
        """Should handle an empty DataFrame without crashing."""
        df = pd.DataFrame()
        result, avg_age = process_user_data_optimized(df)
        assert len(result) == 0

    def test_dataframe_with_nulls(self):
        """Should handle NaN values gracefully."""
        df = pd.DataFrame({
            "user_id": [1, 2],
            "age": [20, None],
            "score": [10, None],
            "active": [True, False]
        })
        result, _ = process_user_data_optimized(df)
        assert len(result) == 2

    def test_all_users_inactive(self):
        """Should handle all users being inactive."""
        df = pd.DataFrame({
            "user_id": [1, 2],
            "age": [20, 25],
            "score": [10, 20],
            "active": [False, False]
        })
        result, _ = process_user_data_optimized(df)
        assert result["score"].sum() == 30


# ==============================================================================
# SECTION 3: Testing Dashboard Metrics
# ==============================================================================

class TestDashboardMetrics:
    def test_basic_metrics(self):
        """Should calculate correct basic metrics."""
        df = pd.DataFrame({
            "user_id": [1, 2, 3],
            "age": [20, 25, 30],
            "score": [10, 20, 30],
            "active": [True, False, True]
        })
        metrics = calculate_dashboard_metrics_optimized(df)
        assert metrics["total_users"] == 3
        assert metrics["active_users"] == 2
        assert metrics["inactive_users"] == 1
        assert metrics["average_score"] == 20.0

    def test_metrics_all_active(self):
        """Should handle all users being active."""
        df = pd.DataFrame({
            "user_id": [1, 2],
            "age": [20, 25],
            "score": [10, 20],
            "active": [True, True]
        })
        metrics = calculate_dashboard_metrics_optimized(df)
        assert metrics["active_users"] == 2
        assert metrics["inactive_users"] == 0

    def test_metrics_empty_dataframe(self):
        """Should handle metrics for empty DataFrame."""
        df = pd.DataFrame()
        metrics = calculate_dashboard_metrics_optimized(df)
        assert metrics["total_users"] == 0
        assert metrics["average_score"] == 0


# ==============================================================================
# SECTION 4: Testing Performance (Simulating Large Datasets)
# ==============================================================================

class TestPerformance:
    def test_large_dataset_processing(self):
        """Should process a large dataset quickly."""
        import time
        # Create 10,000 rows
        df = pd.DataFrame({
            "user_id": range(10000),
            "age": [20] * 10000,
            "score": [10] * 10000,
            "active": [True] * 10000
        })
        
        start_time = time.time()
        result, _ = process_user_data_optimized(df)
        end_time = time.time()
        
        assert len(result) == 10000
        assert end_time - start_time < 1.0  # Should process in under 1 second

    def test_large_dataset_metrics(self):
        """Should calculate metrics for large dataset."""
        df = pd.DataFrame({
            "user_id": range(5000),
            "age": [20] * 5000,
            "score": [10] * 5000,
            "active": [True] * 5000
        })
        metrics = calculate_dashboard_metrics_optimized(df)
        assert metrics["total_users"] == 5000