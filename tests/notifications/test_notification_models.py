"""
Tests for Notification Models.
"""

import pytest
from datetime import datetime, time
from src.notifications.models import NotificationPreference, NotificationPayload, NotificationTemplate

def test_preference_defaults():
    pref = NotificationPreference(user_id=1)
    assert pref.email_enabled is True
    assert pref.in_app_enabled is True
    assert pref.quiet_hours_start is None
    assert pref.weekly_digest_enabled is True
    
def test_preference_to_from_dict():
    pref = NotificationPreference(
        user_id=42,
        quiet_hours_start=time(22, 0),
        quiet_hours_end=time(8, 0),
        opted_out_categories=["digest"]
    )
    d = pref.to_dict()
    assert d["user_id"] == 42
    assert d["quiet_hours_start"] == "22:00"
    
    restored = NotificationPreference.from_dict(d)
    assert restored.user_id == 42
    assert restored.quiet_hours_start == time(22, 0)
    assert restored.opted_out_categories == ["digest"]

def test_template_render():
    tpl = NotificationTemplate(
        template_id="goal_due",
        category="goals",
        title_template="Goal {goal_name} Due!",
        body_template="You have {days} days left."
    )
    
    title, body = tpl.render({"goal_name": "Zero Waste", "days": 3})
    assert title == "Goal Zero Waste Due!"
    assert body == "You have 3 days left."
    
    with pytest.raises(ValueError):
        tpl.render({"goal_name": "Zero Waste"})  # Missing days

def test_payload_db_conversion():
    payload = NotificationPayload(
        user_id=1,
        title="Test",
        metadata={"link": "https://example.com"}
    )
    
    db_tuple = payload.to_db_tuple()
    assert len(db_tuple) == 18
    
    restored = NotificationPayload.from_db_row(db_tuple)
    assert restored.id == payload.id
    assert restored.user_id == 1
    assert restored.metadata == {"link": "https://example.com"}
