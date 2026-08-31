"""
Dependency-aware cache invalidation registry for EcoBuddy AI.

Maps domain events to the set of cached functions they should invalidate.
This replaces scattered `.clear()` calls with a centralized, maintainable registry.
"""

import streamlit as st

from collections.abc import Callable
from typing import Any

from src.core.event_bus import event_handler
from src.core.domain_events import (
    AssessmentSaved,
    AssessmentUndone,
    ApplianceChanged,
    SolarConfigSaved,
    ChallengeEnrolled,
    ChallengeProgressed,
    ChallengeCompleted,
    XPAwarded,
    BadgeUnlocked,
    SkillTreeUpdated,
    JourneySaved,
    JourneyDeleted,
    OffsetSaved,
    OffsetDeleted,
    OffsetCleared,
    WaterAssessmentSaved,
    ReductionGoalChanged,
    FreezeTokenChanged,
    TimeCapsuleChanged,
)

# Registry of all cached functions, populated by the @cached decorator
_CACHED_FUNCTION_REGISTRY = {}


def register_cached_function(func: Callable[..., Any], category: str) -> None:
    """
    Register a cached function in the global registry.

    Called automatically by the @cached decorator in src.core.cache.py.
    """
    name = getattr(func, '_cache_name', func.__qualname__)
    _CACHED_FUNCTION_REGISTRY[name] = {
        'func': func,
        'category': category,
    }


def get_cached_functions_for_category(category: str) -> list[Callable[..., Any]]:
    """
    Retrieve all cached functions registered under a given category.

    Args:
        category: The cache category string.

    Returns:
        List of cached function objects.
    """
    return [
        entry['func']
        for entry in _CACHED_FUNCTION_REGISTRY.values()
        if entry['category'] == category
    ]


def get_all_cached_functions() -> dict[str, Callable[..., Any]]:
    """
    Retrieve all registered cached functions.

    Returns:
        Dict of {name: func_object} for all registered cached functions.
    """
    return {name: entry['func'] for name, entry in _CACHED_FUNCTION_REGISTRY.items()}


# ---------------------------------------------------------------------------
# Write-operation invalidation helpers
# Each function acts as an event handler and clears dependent caches.
# ---------------------------------------------------------------------------

@event_handler(AssessmentSaved)
@event_handler(AssessmentUndone)
def invalidate_on_assessment_save(event=None) -> None:
    """Invalidate caches dependent on assessment writes or undo."""
    _clear_by_name([
        'get_assessments',
        'get_diet_history',
        'get_total_xp',
    ])


@event_handler(ApplianceChanged)
def invalidate_on_appliance_change(event=None) -> None:
    """Invalidate caches dependent on appliance add/delete."""
    _clear_by_name([
        'get_appliances',
    ])


@event_handler(SolarConfigSaved)
def invalidate_on_solar_config_save(event=None) -> None:
    """Invalidate caches dependent on solar config changes."""
    _clear_by_name([
        'get_solar_config',
    ])


@event_handler(ChallengeEnrolled)
@event_handler(ChallengeProgressed)
@event_handler(ChallengeCompleted)
def invalidate_on_challenge_enroll(event=None) -> None:
    """Invalidate caches dependent on challenge enrollment/progress/completion."""
    _clear_by_name([
        'get_user_challenges',
    ])


@event_handler(XPAwarded)
def invalidate_on_xp_award(event: XPAwarded = None) -> None:
    """Invalidate caches dependent on XP award."""
    names = ['get_total_xp']
    source_type = event.source_type if event else None
    if source_type == 'challenge':
        names.append('get_user_challenges')
    elif source_type == 'badge':
        names.append('get_unlocked_badges')
    _clear_by_name(names)


@event_handler(BadgeUnlocked)
def invalidate_on_badge_unlock(event=None) -> None:
    """Invalidate caches dependent on badge unlock."""
    _clear_by_name([
        'get_unlocked_badges',
        'get_total_xp',
    ])


@event_handler(SkillTreeUpdated)
def invalidate_on_skill_tree_update(event=None) -> None:
    """Invalidate caches dependent on skill tree node update."""
    _clear_by_name([
        'get_skill_tree_progress',
    ])


@event_handler(JourneySaved)
@event_handler(JourneyDeleted)
def invalidate_on_journey_save(event=None) -> None:
    """Invalidate caches dependent on journey profile save or delete."""
    _clear_by_name([
        'get_journey_profiles',
    ])


@event_handler(OffsetSaved)
@event_handler(OffsetDeleted)
@event_handler(OffsetCleared)
def invalidate_on_offset_save(event=None) -> None:
    """Invalidate caches dependent on offset transaction save/delete/clear."""
    _clear_by_name([
        'get_offset_transactions',
        'get_total_offsets',
        'get_total_spend',
    ])


@event_handler(WaterAssessmentSaved)
def invalidate_on_water_assessment_save(event=None) -> None:
    """Invalidate caches dependent on water assessment save."""
    _clear_by_name([
        'get_water_assessments',
    ])


@event_handler(FreezeTokenChanged)
def invalidate_on_freeze_token_change(event=None) -> None:
    """Invalidate caches dependent on freeze token or streak freeze changes."""
    _clear_by_name([
        'get_freeze_token_balance',
        'get_streak_freeze_dates',
        'get_total_freeze_tokens_earned',
    ])


@event_handler(ReductionGoalChanged)
def invalidate_on_reduction_goal_change(event=None) -> None:
    """Invalidate caches dependent on reduction goal create/archive/complete."""
    _clear_by_name([
        'get_active_goal',
        'get_goal_history',
    ])


@event_handler(TimeCapsuleChanged)
def invalidate_on_time_capsule_change(event=None) -> None:
    """Invalidate caches dependent on time capsule operations."""
    _clear_by_name([
        'get_time_capsules',
    ])


def invalidate_all_db_caches() -> None:
    """
    Invalidate ALL database read caches.

    Used during bulk data import (src.data.data_io.import_data_json) where
    any table could have changed.
    """
    db_read_names = [
        'get_assessments',
        'get_appliances',
        'get_solar_config',
        'get_user_challenges',
        'get_total_xp',
        'get_unlocked_badges',
        'get_skill_tree_progress',
        'get_journey_profiles',
        'get_offset_transactions',
        'get_total_offsets',
        'get_total_spend',
        'get_diet_history',
        'get_water_assessments',
        'get_freeze_token_balance',
        'get_streak_freeze_dates',
        'get_total_freeze_tokens_earned',
        'get_active_goal',
        'get_goal_history',
        'get_time_capsules',
    ]
    _clear_by_name(db_read_names)


def invalidate_export_caches() -> None:
    """Invalidate export caches (used after data import)."""
    _clear_by_name([
        'export_data_json',
        'export_data_csv_zip',
    ])


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _clear_by_name(names: list[str]) -> None:
    """
    Clear cache for functions by their registered name.

    Falls back to trying module-level lookups if not in registry.
    """
    for name in names:
        # Try registry first
        if name in _CACHED_FUNCTION_REGISTRY:
            func = _CACHED_FUNCTION_REGISTRY[name]['func']
            if hasattr(func, 'clear'):
                func.clear()
            continue

        # Fallback: try to find in common modules
        for module_name in ['database', 'data_io']:
            try:
                import importlib
                module = importlib.import_module(module_name)
                func = getattr(module, name, None)
                if func and hasattr(func, 'clear'):
                    func.clear()
                    break
            except ImportError:
                pass
