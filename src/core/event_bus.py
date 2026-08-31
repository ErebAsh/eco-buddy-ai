import logging
import inspect
from typing import Callable, Any, TypeVar, Type, Dict, List
from functools import wraps

from src.core.domain_events import DomainEvent
from src.core.event_store import EventStore

logger = logging.getLogger(__name__)

TEvent = TypeVar('TEvent', bound=DomainEvent)
EventHandler = Callable[[TEvent], Any]


class EventBus:
    """
    Singleton Event Bus for pub/sub domain events.
    """
    _instance = None
    _subscribers: Dict[Type[DomainEvent], List[EventHandler]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EventBus, cls).__new__(cls)
            cls._instance._subscribers = {}
        return cls._instance

    @classmethod
    def get_instance(cls) -> "EventBus":
        if cls._instance is None:
            cls()
        return cls._instance

    @classmethod
    def subscribe(cls, event_type: Type[TEvent], handler: EventHandler) -> None:
        """
        Subscribe a handler to a specific event type.
        """
        instance = cls.get_instance()
        if event_type not in instance._subscribers:
            instance._subscribers[event_type] = []
            
        if handler not in instance._subscribers[event_type]:
            instance._subscribers[event_type].append(handler)
            logger.debug(f"Subscribed {handler.__name__} to {event_type.__name__}")

    @classmethod
    def publish(cls, event: DomainEvent) -> None:
        """
        Publish an event to all subscribed handlers synchronously.
        Saves the event to the EventStore.
        If a handler fails, it logs the error but continues executing others.
        """
        instance = cls.get_instance()
        
        # Save to store
        EventStore.save(event)

        event_type = type(event)
        handlers = instance._subscribers.get(event_type, [])
        
        for handler in handlers:
            try:
                # Check if the handler accepts arguments
                sig = inspect.signature(handler)
                if len(sig.parameters) > 0:
                    handler(event)
                else:
                    handler()
            except Exception as e:
                logger.error(f"Error executing handler {handler.__name__} for event {event_type.__name__}: {e}", exc_info=True)


def event_handler(event_type: Type[TEvent]):
    """
    Decorator to register a function as an event handler.
    
    Usage:
        @event_handler(AssessmentSaved)
        def my_handler(event: AssessmentSaved):
            ...
    """
    def decorator(func: EventHandler):
        EventBus.subscribe(event_type, func)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator
