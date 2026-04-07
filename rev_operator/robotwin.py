"""RoboTwin implementation for dataset time-reverse operations."""

from __future__ import annotations

import json
import pickle
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .base import BaseTimeReverseOperator

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover
    np = None  # type: ignore[assignment]


class RobotwinTimeReverseOperator(BaseTimeReverseOperator):
    """Time-reverse operator for RoboTwin datasets."""

    REVERSE_TASK_MAP: Dict[str, str] = {
        "stack_blocks_three": "unstack_blocks_three",
        "unstack_blocks_three": "stack_blocks_three",
        "stack_bowls_three": "unstack_bowls_three",
        "unstack_bowls_three": "stack_bowls_three",
        "move_pillbottle_pad": "unmove_pillbottle_pad",
        "unmove_pillbottle_pad": "move_pillbottle_pad",
        "hanging_mug": "unhanging_mug",
        "unhanging_mug": "hanging_mug",
    }

    VALID_SPLITS = {"demo_clean", "demo_randomized"}

    def _detect_layout(self, input_dir: Path, output_dir: Path) -> Dict[str, Any]:
        split_name = input_dir.name
        if split_name not in self.VALID_SPLITS:
            raise ValueError(
                f"Unsupported RoboTwin split: {split_name}. "
                f"Expected one of {sorted(self.VALID_SPLITS)}."
            )

        task_name = input_dir.parent.name
        if task_name not in self.REVERSE_TASK_MAP:
            raise KeyError(
                f"Reverse task mapping not found for task: {task_name}. "
                "Please add it to RobotwinTimeReverseOperator.REVERSE_TASK_MAP."
            )

        robotwin_data_root = input_dir.parent.parent
        reverse_task_name = self.REVERSE_TASK_MAP[task_name]
        reverse_instructions_dir = (
            robotwin_data_root / reverse_task_name / split_name / "instructions"
        )
        if not reverse_instructions_dir.is_dir():
            raise FileNotFoundError(
                f"Reverse instructions directory does not exist: "
                f"{reverse_instructions_dir}"
            )

        return {
            "input_dir": input_dir,
            "output_dir": output_dir,
            "split_name": split_name,
            "task_name": task_name,
            "reverse_task_name": reverse_task_name,
            "reverse_instructions_dir": reverse_instructions_dir,
            "output_instructions_dir": output_dir / "instructions",
            "output_data_dir": output_dir / "data",
            "output_traj_dir": output_dir / "_traj_data",
            "output_video_dir": output_dir / "video",
        }

    def _reverse_instructions(self, layout: Dict[str, Any]) -> None:
        output_instructions_dir = layout["output_instructions_dir"]
        reverse_instructions_dir = layout["reverse_instructions_dir"]

        if output_instructions_dir.exists():
            shutil.rmtree(output_instructions_dir)
        shutil.copytree(reverse_instructions_dir, output_instructions_dir)

    def _reverse_hdf5(self, layout: Dict[str, Any]) -> None:
        data_dir = layout["output_data_dir"]
        if not data_dir.is_dir():
            raise FileNotFoundError(f"Missing data directory: {data_dir}")

        try:
            import h5py
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError(
                "h5py is required for RoboTwin HDF5 reversal."
            ) from exc

        for hdf5_path in sorted(data_dir.glob("episode*.hdf5")):
            with h5py.File(hdf5_path, "r+") as h5f:
                datasets: List[Any] = []
                time_candidates: List[int] = []

                def collect(name: str, obj: Any) -> None:
                    if not isinstance(obj, h5py.Dataset):
                        return
                    datasets.append(obj)
                    if obj.ndim > 0 and obj.shape[0] > 1:
                        time_candidates.append(int(obj.shape[0]))

                h5f.visititems(collect)
                if not time_candidates:
                    continue

                time_len = max(time_candidates)
                for ds in datasets:
                    if ds.ndim > 0 and ds.shape[0] == time_len and time_len > 1:
                        ds[...] = ds[::-1]

    def _reverse_pkl(self, layout: Dict[str, Any]) -> None:
        traj_dir = layout["output_traj_dir"]
        if not traj_dir.is_dir():
            raise FileNotFoundError(f"Missing trajectory directory: {traj_dir}")

        for pkl_path in sorted(traj_dir.glob("episode*.pkl")):
            with open(pkl_path, "rb") as infile:
                obj = pickle.load(infile)

            time_len = self._infer_time_len(obj)
            reversed_obj = self._reverse_python_object(obj=obj, time_len=time_len)

            with open(pkl_path, "wb") as outfile:
                pickle.dump(reversed_obj, outfile, protocol=pickle.HIGHEST_PROTOCOL)

    def _reverse_video(self, layout: Dict[str, Any]) -> None:
        video_dir = layout["output_video_dir"]
        if not video_dir.is_dir():
            raise FileNotFoundError(f"Missing video directory: {video_dir}")

        try:
            import cv2
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError(
                "opencv-python is required for RoboTwin video reversal."
            ) from exc

        for video_path in sorted(video_dir.glob("episode*.mp4")):
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise RuntimeError(f"Failed to open video file: {video_path}")

            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            frames: List[Any] = []

            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                frames.append(frame)
            cap.release()

            if not frames:
                continue

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(video_path), fourcc, fps, (width, height))
            if not writer.isOpened():
                raise RuntimeError(f"Failed to open video writer: {video_path}")

            for frame in reversed(frames):
                writer.write(frame)
            writer.release()

    def _infer_time_len(self, obj: Any) -> Optional[int]:
        lengths: List[int] = []
        self._collect_lengths(obj=obj, lengths=lengths)
        if not lengths:
            return None
        return max(lengths)

    def _collect_lengths(self, obj: Any, lengths: List[int]) -> None:
        if isinstance(obj, dict):
            for value in obj.values():
                self._collect_lengths(value, lengths)
            return

        if isinstance(obj, list) or isinstance(obj, tuple):
            if len(obj) > 1:
                lengths.append(len(obj))
            for item in obj:
                self._collect_lengths(item, lengths)
            return

        if np is not None and isinstance(obj, np.ndarray):
            if obj.ndim > 0 and obj.shape[0] > 1:
                lengths.append(int(obj.shape[0]))

    def _reverse_python_object(self, obj: Any, time_len: Optional[int]) -> Any:
        if isinstance(obj, dict):
            return {
                key: self._reverse_python_object(value, time_len=time_len)
                for key, value in obj.items()
            }

        if isinstance(obj, list):
            values = [self._reverse_python_object(x, time_len=time_len) for x in obj]
            if time_len is not None and len(values) == time_len:
                values.reverse()
            return values

        if isinstance(obj, tuple):
            values = tuple(
                self._reverse_python_object(x, time_len=time_len) for x in obj
            )
            if time_len is not None and len(values) == time_len:
                return tuple(reversed(values))
            return values

        if np is not None and isinstance(obj, np.ndarray):
            if obj.ndim > 0 and time_len is not None and obj.shape[0] == time_len:
                return obj[::-1].copy()
            return obj

        return obj
