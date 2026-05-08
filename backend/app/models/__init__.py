"""ORM model registry.

Importing this module is what registers all models with SQLAlchemy's
declarative metadata so ``Base.metadata.create_all`` can build the schema.
"""

from .api_cache import ApiCache
from .location import GeoLevel, Location
from .metric import Metric, MetricDirection
from .metric_value import MetricValue
from .preset import Preference, Preset

__all__ = [
    "ApiCache",
    "GeoLevel",
    "Location",
    "Metric",
    "MetricDirection",
    "MetricValue",
    "Preference",
    "Preset",
]
