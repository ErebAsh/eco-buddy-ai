import logging

logger = logging.getLogger(__name__)


def register_all_subscribers() -> None:
    """
    Auto-discovers and registers all event handlers across the application.
    Importing modules containing @event_handler decorators will automatically
    register them with the EventBus.
    """
    logger.info("Registering event subscribers...")
    
    # Import modules that contain @event_handler decorated functions
    import src.core.invalidation
    
    # Add other modules here as needed in the future
    # import src.gamification.subscribers
    # import src.notifications.subscribers
    
    logger.info("Event subscribers registered successfully.")
