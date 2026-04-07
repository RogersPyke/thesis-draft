"""Base classes for dataset time-reverse operators."""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict


class BaseTimeReverseOperator(ABC):
    """Base interface for reversible dataset adapters."""

    def __call__(self, filepath: str) -> str:
        """Create reversed copy beside input path.

        @input:
            - filepath: str, existing dataset directory path.
        @output:
            - str, output dataset directory path ending with ``-rev``.
        @scenario:
            - Common entrypoint for all dataset-specific operators.
        """
        input_dir = Path(filepath).resolve()
        if not input_dir.exists():
            raise FileNotFoundError(f"Input path does not exist: {input_dir}")
        if not input_dir.is_dir():
            raise NotADirectoryError(f"Input path must be a directory: {input_dir}")

        output_dir = input_dir.parent / f"{input_dir.name}-rev"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        shutil.copytree(input_dir, output_dir)
        layout = self._detect_layout(input_dir=input_dir, output_dir=output_dir)

        self._reverse_instructions(layout)
        self._reverse_hdf5(layout)
        self._reverse_pkl(layout)
        self._reverse_video(layout)
        return str(output_dir)

    @abstractmethod
    def _detect_layout(self, input_dir: Path, output_dir: Path) -> Dict[str, Any]:
        """Resolve dataset structure and return operator context."""

    @abstractmethod
    def _reverse_instructions(self, layout: Dict[str, Any]) -> None:
        """Reverse or replace instruction artifacts."""

    @abstractmethod
    def _reverse_hdf5(self, layout: Dict[str, Any]) -> None:
        """Reverse HDF5 episode files in place under output dir."""

    @abstractmethod
    def _reverse_pkl(self, layout: Dict[str, Any]) -> None:
        """Reverse trajectory pickle files in place under output dir."""

    @abstractmethod
    def _reverse_video(self, layout: Dict[str, Any]) -> None:
        """Reverse episode videos in place under output dir."""
