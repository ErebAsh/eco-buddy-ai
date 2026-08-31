from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any, Optional


@dataclass
class DomainEvent:
    """Base class for all domain events."""
    payload: dict[str, Any] = field(default_factory=dict)
    source_module: str = "unknown"
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def event_type(self) -> str:
        """Return the class name as the event type."""
        return self.__class__.__name__


@dataclass
class AssessmentSaved(DomainEvent):
    pass


@dataclass
class AssessmentUndone(DomainEvent):
    pass


@dataclass
class ApplianceChanged(DomainEvent):
    pass


@dataclass
class SolarConfigSaved(DomainEvent):
    pass


@dataclass
class ChallengeEnrolled(DomainEvent):
    pass


@dataclass
class ChallengeProgressed(DomainEvent):
    pass


@dataclass
class ChallengeCompleted(DomainEvent):
    pass


@dataclass
class XPAwarded(DomainEvent):
    source_type: Optional[str] = None
    
    def __post_init__(self):
        # Allow payload to contain source_type for convenience
        if self.source_type is None and "source_type" in self.payload:
            self.source_type = self.payload["source_type"]


@dataclass
class BadgeUnlocked(DomainEvent):
    pass


@dataclass
class SkillTreeUpdated(DomainEvent):
    pass


@dataclass
class JourneySaved(DomainEvent):
    pass


@dataclass
class JourneyDeleted(DomainEvent):
    pass


@dataclass
class OffsetSaved(DomainEvent):
    pass


@dataclass
class OffsetDeleted(DomainEvent):
    pass


@dataclass
class OffsetCleared(DomainEvent):
    pass


@dataclass
class WaterAssessmentSaved(DomainEvent):
    pass


@dataclass
class ReductionGoalChanged(DomainEvent):
    pass


@dataclass
class FreezeTokenChanged(DomainEvent):
    pass


@dataclass
class TimeCapsuleChanged(DomainEvent):
    pass
