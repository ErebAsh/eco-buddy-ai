import json
import logging
import sqlite3
from typing import Optional
from datetime import datetime

from src.core.database_connection import database_connection
from src.core.domain_events import DomainEvent

logger = logging.getLogger(__name__)

# Fallback DB name if not available from database module directly.
# The app uses os.getenv("ECO_BUDDY_DB", "eco_buddy.db") in src.core.database.py
import os
DB_NAME = os.getenv("ECO_BUDDY_DB", "eco_buddy.db")


class EventStore:
    """
    Append-only store for domain events, backed by SQLite.
    """

    @classmethod
    def save(cls, event: DomainEvent) -> None:
        """
        Persists a DomainEvent to the database.
        
        Args:
            event: The DomainEvent instance to save.
        """
        try:
            with database_connection(DB_NAME) as conn:
                cursor = conn.cursor()
                
                # Convert payload to JSON string safely
                try:
                    payload_json = json.dumps(event.payload)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Could not JSON serialize event payload for {event.event_type}: {e}")
                    payload_json = "{}"

                cursor.execute(
                    """
                    INSERT INTO domain_events 
                    (event_type, timestamp, payload, source_module, correlation_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_type,
                        event.timestamp.isoformat(),
                        payload_json,
                        event.source_module,
                        event.correlation_id,
                    )
                )
                
        except sqlite3.OperationalError as e:
            # Handle the case where the table might not exist yet (e.g. before migrations)
            if "no such table: domain_events" in str(e):
                logger.warning(f"EventStore failed to save {event.event_type}: domain_events table does not exist.")
            else:
                logger.error(f"EventStore database error saving {event.event_type}: {e}")
        except Exception as e:
            logger.error(f"EventStore error saving {event.event_type}: {e}")
