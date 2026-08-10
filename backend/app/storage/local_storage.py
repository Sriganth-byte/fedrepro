import re
import shutil
from pathlib import Path
from uuid import uuid4

import pandas as pd
from fastapi import UploadFile

from app.core.config import get_settings


class LocalFileStorage:
    def __init__(self, root: Path | None = None):
        self.root = (root or get_settings().upload_root).resolve()
        self.staging = self.root / "staging"
        self.datasets = self.root / "datasets"
        self.staging.mkdir(parents=True, exist_ok=True)
        self.datasets.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _slug(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")[:80] or "dataset"

    async def stage_csv(self, upload: UploadFile) -> tuple[Path, pd.DataFrame]:
        filename = Path(upload.filename or "dataset.csv").name
        if Path(filename).suffix.lower() != ".csv":
            raise ValueError("Only CSV files are accepted in Phase 1")
        target = self.staging / f"{uuid4().hex}-{self._slug(Path(filename).stem)}.csv"
        size = 0
        with target.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > get_settings().max_upload_bytes:
                    handle.close()
                    target.unlink(missing_ok=True)
                    raise ValueError("CSV exceeds the configured upload limit")
                handle.write(chunk)
        if size == 0:
            target.unlink(missing_ok=True)
            raise ValueError("Uploaded CSV is empty")
        try:
            frame = pd.read_csv(target)
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise ValueError(f"CSV could not be parsed: {exc}") from exc
        if not len(frame.columns):
            target.unlink(missing_ok=True)
            raise ValueError("CSV must contain at least one column")
        if len(set(frame.columns)) != len(frame.columns):
            target.unlink(missing_ok=True)
            raise ValueError("CSV contains duplicate column names")
        return target, frame

    def promote(self, staged_path: str, study_id: int, dataset_id: int, version_number: int) -> Path:
        source = Path(staged_path).resolve()
        if self.staging not in source.parents or not source.is_file():
            raise ValueError("Invalid staged dataset path")
        destination_dir = self.datasets / f"study-{study_id}" / f"dataset-{dataset_id}"
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"v{version_number}.csv"
        if destination.exists():
            raise ValueError("Immutable dataset version already exists")
        shutil.move(str(source), destination)
        return destination.resolve()

    def delete_version_file(self, file_path: str) -> None:
        target = Path(file_path).resolve()
        if self.datasets not in target.parents:
            raise ValueError("Invalid dataset version path")
        target.unlink(missing_ok=True)
