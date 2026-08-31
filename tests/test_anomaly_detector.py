"""
Unit tests for Anomaly Detector and Alert Manager.
"""

import pytest
from src.services.anomaly_detector import AnomalyDetector
from src.services.alert_manager import AlertManager


def test_calculate_statistics():
    detector = AnomalyDetector()
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = detector.calculate_statistics(data)

    assert stats["mean"] == 30.0
    assert stats["std_dev"] == 15.81  # Approximate


def test_calculate_statistics_empty():
    detector = AnomalyDetector()
    stats = detector.calculate_statistics([])
    assert stats["mean"] == 0.0
    assert stats["std_dev"] == 0.0


def test_detect_anomalies_sparse_data():
    detector = AnomalyDetector()
    data = [
        {"date": "2023-01", "carbon_kg": 100},
        {"date": "2023-02", "carbon_kg": 110},
    ]
    results = detector.detect_anomalies(data)

    # Should not flag anomalies with less than 3 data points
    assert all(not entry["is_anomaly"] for entry in results)
    assert all(entry["z_score"] == 0.0 for entry in results)


def test_detect_anomalies_valid_spike():
    detector = AnomalyDetector(z_score_threshold=2.0)
    data = [
        {"date": "2023-01", "carbon_kg": 100},
        {"date": "2023-02", "carbon_kg": 100},
        {"date": "2023-03", "carbon_kg": 100},
        {"date": "2023-04", "carbon_kg": 100},
        {"date": "2023-05", "carbon_kg": 500},  # Massive spike
    ]
    results = detector.detect_anomalies(data)

    # The last entry should be flagged as an anomaly
    assert results[-1]["is_anomaly"] is True
    assert results[-1]["z_score"] > 2.0
    assert results[-1]["mean_baseline"] == 180.0  # (100*4 + 500) / 5


def test_alert_manager_severity():
    manager = AlertManager()
    assert manager.determine_severity(1.5) == "low"
    assert manager.determine_severity(2.5) == "medium"
    assert manager.determine_severity(3.5) == "high"


def test_alert_manager_generation():
    manager = AlertManager()
    anomaly_data = {
        "date": "2023-05",
        "carbon_kg": 500,
        "z_score": 3.5,
        "mean_baseline": 100,
    }
    alert = manager.generate_alert(anomaly_data)

    assert alert["severity"] == "high"
    assert alert["deviation_pct"] == 400.0
    assert "Immediate Action" in alert["recommendations"][0]
    assert alert["resolved"] is False
