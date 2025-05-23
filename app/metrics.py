from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from aws_embedded_metrics.logger.metrics_logger import MetricsLogger
from aws_embedded_metrics.logger.metrics_logger_factory import create_metrics_logger

from app.config import settings


class MetricsProvider(ABC):
    """Abstract base class for metrics providers."""

    @abstractmethod
    def put_metric(self, name: str, value: int | float) -> None:
        """Record a metric with the given name and value."""

    @abstractmethod
    def set_property(self, name: str, value: str) -> None:
        """Set a property/dimension for metrics."""


class CloudWatchMetricsProvider(MetricsProvider):
    """Implementation that uses CloudWatch metrics via aws_embedded_metrics."""

    def __init__(self, metrics_logger: MetricsLogger):
        self.metrics = metrics_logger

    def put_metric(self, name: str, value: int | float) -> None:
        """Record a metric with the given name and value in CloudWatch."""
        self.metrics.put_metric(name, value)

    def set_property(self, name: str, value: str) -> None:
        """Set a property/dimension for metrics."""
        self.metrics.set_property(name, value)


class NoopMetricsProvider(MetricsProvider):
    """Metrics provider that does nothing - for testing."""

    def put_metric(self, name: str, value: int | float) -> None:
        """Does nothing."""

    def set_property(self, name: str, value: str) -> None:
        """Does nothing."""


@asynccontextmanager
async def get_metrics_provider() -> AsyncGenerator[MetricsProvider]:
    """Context manager that provides the appropriate metrics provider.

    When metrics are enabled, creates a CloudWatch metrics provider and ensures
    proper flushing. When disabled, provides a no-op implementation.
    """
    if settings.metrics_enabled:
        metrics_logger = create_metrics_logger()
        metrics_logger.set_namespace("CompilerExplorer")
        provider = CloudWatchMetricsProvider(metrics_logger)
        try:
            yield provider
        finally:
            await metrics_logger.flush()
    else:
        yield NoopMetricsProvider()
