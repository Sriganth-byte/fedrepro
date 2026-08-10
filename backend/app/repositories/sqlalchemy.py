from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.models.entities import Dataset, DatasetVersion, Study, StudyConfiguration
from app.repositories.base import DatasetRepositoryPort, StudyRepositoryPort


class SQLAlchemyRepository:
    model = None

    def __init__(self, db: Session):
        self.db = db

    def get(self, entity_id: int):
        return self.db.get(self.model, entity_id)

    def add(self, entity):
        self.db.add(entity)
        self.db.flush()
        return entity


class StudyRepository(SQLAlchemyRepository, StudyRepositoryPort):
    model = Study

    def list_for_owner(self, owner_id: int, search: str | None = None, ml_task: str | None = None):
        query = self.db.query(Study).filter(Study.owner_id == owner_id)
        if search:
            query = query.filter(func.lower(Study.name).contains(search.lower()))
        if ml_task:
            query = query.filter(Study.ml_task == ml_task)
        return query.order_by(Study.updated_at.desc()).all()


class StudyConfigurationRepository(SQLAlchemyRepository):
    model = StudyConfiguration

    def current_for_study(self, study_id: int) -> StudyConfiguration | None:
        return self.db.query(StudyConfiguration).filter(
            StudyConfiguration.study_id == study_id,
            StudyConfiguration.status == "current",
        ).order_by(StudyConfiguration.version_number.desc()).first()

    def list_for_study(self, study_id: int):
        return self.db.query(StudyConfiguration).filter(
            StudyConfiguration.study_id == study_id,
        ).order_by(StudyConfiguration.version_number.desc()).all()

    def next_version_number(self, study_id: int) -> int:
        latest = self.db.query(StudyConfiguration).filter(
            StudyConfiguration.study_id == study_id,
        ).order_by(StudyConfiguration.version_number.desc()).first()
        return (latest.version_number + 1) if latest else 1

    def get_by_version_number(
        self, study_id: int, version_number: int
    ) -> StudyConfiguration | None:
        """Return a specific configuration version by its version number."""
        return self.db.query(StudyConfiguration).filter(
            StudyConfiguration.study_id == study_id,
            StudyConfiguration.version_number == version_number,
        ).first()

    def get_pair_for_diff(
        self, study_id: int, from_version: int, to_version: int
    ) -> tuple[StudyConfiguration | None, StudyConfiguration | None]:
        """Return two configuration versions in a single DB round-trip."""
        rows = self.db.query(StudyConfiguration).filter(
            StudyConfiguration.study_id == study_id,
            StudyConfiguration.version_number.in_([from_version, to_version]),
        ).all()
        index = {row.version_number: row for row in rows}
        return index.get(from_version), index.get(to_version)


class DatasetRepository(SQLAlchemyRepository, DatasetRepositoryPort):
    model = Dataset

    def list_for_study(self, study_id: int):
        return self.db.query(Dataset).filter(Dataset.study_id == study_id).options(selectinload(Dataset.versions).selectinload(DatasetVersion.fingerprint)).order_by(Dataset.updated_at.desc()).all()

    def latest_version(self, dataset_id: int):
        return self.db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id).order_by(DatasetVersion.version_number.desc()).first()
