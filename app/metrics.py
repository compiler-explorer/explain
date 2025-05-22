from abc import ABC, abstractmethod

from aws_embedded_metrics.logger.metrics_logger import MetricsLogger


class MetricsProvider(ABC):
    """Abstract base class for metrics providers."""

    @abstractmethod
    def put_metric(self, name: str, value: int | float) -> None:
        """Record a metric with the given name and value."""
        pass

    @abstractmethod
    def set_property(self, name: str, value: str) -> None:
        """Set a property/dimension for metrics."""
        pass


class CloudWatchMetricsProvider(MetricsProvider):
    """Implementation that uses CloudWatch metrics via aws_embedded_metrics."""

    def __init__(self, metrics_logger: MetricsLogger):
        self.metrics = metrics_logger

    def put_metric(self, name: str, value: int | float) -> None:
        self.metrics.put_metric(name, value)

    def set_property(self, name: str, value: str) -> None:
        self.metrics.set_property(name, value)


class NoopMetricsProvider(MetricsProvider):
    """Metrics provider that does nothing - for testing."""

    def put_metric(self, name: str, value: int | float) -> None:
        pass

    def set_property(self, name: str, value: str) -> None:
        pass
