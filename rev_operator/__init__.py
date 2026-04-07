"""Public APIs for data time-reverse operators."""

from .base import BaseTimeReverseOperator
from .robotwin import RobotwinTimeReverseOperator


def get_time_reverse_operator(dataset_type: str) -> BaseTimeReverseOperator:
    """Factory for dataset-specific time-reverse operators.

    @input:
        - dataset_type: str, supported value currently ``robotwin``.
    @output:
        - BaseTimeReverseOperator instance.
    @scenario:
        - Provide extensible entrypoint for future dataset types.
    """
    normalized = dataset_type.strip().lower()
    if normalized == "robotwin":
        return RobotwinTimeReverseOperator()
    raise ValueError(f"Unsupported dataset_type: {dataset_type}")


__all__ = [
    "BaseTimeReverseOperator",
    "RobotwinTimeReverseOperator",
    "get_time_reverse_operator",
]
