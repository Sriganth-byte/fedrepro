from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class Repository(ABC, Generic[T]):
    @abstractmethod
    def get(self, entity_id: int) -> T | None: ...

    @abstractmethod
    def add(self, entity: T) -> T: ...


class StudyRepositoryPort(Repository):
    @abstractmethod
    def list_for_owner(self, owner_id: int, search: str | None = None, ml_task: str | None = None): ...


class DatasetRepositoryPort(Repository):
    @abstractmethod
    def list_for_study(self, study_id: int): ...
