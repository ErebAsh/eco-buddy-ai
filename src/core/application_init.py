from .optimized_loader import StartupOptimizer, LoadPriority, LoadTask, LazyProxy
from .startup_decorators import (
    get_optimizer,
    lazy_load,
    background_load,
    priority_load,
    cache_result,
    async_init,
    throttled_load,
    batch_load,
    preload,
    startup_phase,
    measure_load_time,
    retry_on_failure
)

from .event_subscribers import register_all_subscribers

# Register event subscribers on application init
register_all_subscribers()

__all__ = [
    'StartupOptimizer',
    'LoadPriority',
    'LoadTask',
    'LazyProxy',
    'get_optimizer',
    'lazy_load',
    'background_load',
    'priority_load',
    'cache_result',
    'async_init',
    'throttled_load',
    'batch_load',
    'preload',
    'startup_phase',
    'measure_load_time',
    'retry_on_failure'
]

@startup_phase("feature_flags")
@background_load(priority=LoadPriority.HIGH)
@retry_on_failure(retries=3, delay=1.0)
def preload_feature_flags():
    """Ensure active flags are loaded into cache on startup."""
    from src.core.feature_flags import FeatureFlagStore
    # List flags which will query DB and could be cached
    FeatureFlagStore.list_flags()
