import pytest
from src.core.domain_events import DomainEvent
from src.core.event_bus import EventBus, event_handler
from src.core.event_store import EventStore


class DummyEvent(DomainEvent):
    pass


class FailingEvent(DomainEvent):
    pass


def test_event_bus_singleton():
    bus1 = EventBus.get_instance()
    bus2 = EventBus.get_instance()
    assert bus1 is bus2


def test_event_publish_subscribe(monkeypatch):
    # Mock EventStore.save to avoid db issues in unit tests
    monkeypatch.setattr(EventStore, "save", lambda event: None)

    handled_events = []

    @event_handler(DummyEvent)
    def handle_dummy(event: DummyEvent):
        handled_events.append(event)

    event = DummyEvent(payload={"test": "data"})
    EventBus.publish(event)

    assert len(handled_events) == 1
    assert handled_events[0] is event
    assert handled_events[0].payload["test"] == "data"


def test_failing_handler_does_not_block_others(monkeypatch, caplog):
    monkeypatch.setattr(EventStore, "save", lambda event: None)

    handled_events = []

    @event_handler(FailingEvent)
    def failing_handler(event: FailingEvent):
        raise ValueError("I failed")

    @event_handler(FailingEvent)
    def successful_handler(event: FailingEvent):
        handled_events.append(event)

    event = FailingEvent()
    EventBus.publish(event)

    # The successful handler should still execute even if failing_handler raised an exception
    assert len(handled_events) == 1
    assert handled_events[0] is event
    
    # Check that error was logged
    assert "Error executing handler failing_handler" in caplog.text
