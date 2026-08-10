import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.entities import User
from app.repositories.sqlalchemy import StudyConfigurationRepository
from app.schemas.contracts import (
    DashboardRead,
    StudyConfigurationCreate,
    StudyConfigurationDiff,
    StudyConfigurationRead,
    StudyCreate,
    StudyRead,
    StudyUpdate,
)
from app.services.executive_report_service import ExecutiveReportService
from app.services.reporting_service import ReportingService
from app.services.study_service import StudyService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["studies"])


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return ReportingService(db).dashboard(user.id)


@router.post("/studies", response_model=StudyRead, status_code=201)
def create_study(
    payload: StudyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return StudyService(db).create(user.id, payload)


@router.get("/studies", response_model=list[StudyRead])
def list_studies(
    search: str | None = Query(None, max_length=120),
    ml_task: str | None = Query(None, pattern="^(classification|regression|clustering)$"),
    include_configuration: bool = Query(
        False,
        description="Attach the current configuration to each study in the response",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = StudyService(db)
    studies = service.list(user.id, search, ml_task)
    if include_configuration:
        repo = StudyConfigurationRepository(db)
        for study in studies:
            study.current_configuration = repo.current_for_study(study.id)
    return studies


@router.get("/studies/{study_id}", response_model=StudyRead)
def study_detail(
    study_id: int,
    include_configuration: bool = Query(
        False,
        description="Attach the current configuration to the response",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = StudyService(db)
    study = service.get_owned(study_id, user.id)
    if include_configuration:
        study.current_configuration = StudyConfigurationRepository(db).current_for_study(study_id)
    return study


@router.get("/studies/{study_id}/configuration", response_model=StudyConfigurationRead)
def current_study_configuration(
    study_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return StudyService(db).current_configuration(study_id, user.id)


@router.get("/studies/{study_id}/configurations", response_model=list[StudyConfigurationRead])
def study_configuration_history(
    study_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return StudyService(db).list_configurations(study_id, user.id)


# NOTE: the /diff route MUST be registered before /{version_number} so that
# FastAPI matches the literal path segment "diff" before attempting integer conversion.
@router.get(
    "/studies/{study_id}/configurations/diff",
    response_model=StudyConfigurationDiff,
)
def study_configuration_diff(
    study_id: int,
    from_version: int = Query(..., ge=1, description="Base version number (older)"),
    to_version: int = Query(..., ge=1, description="Target version number (newer)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Return a field-level diff between two protocol versions.

    Example: GET /api/studies/1/configurations/diff?from_version=1&to_version=3
    """
    if from_version == to_version:
        raise ValueError("from_version and to_version must be different")
    return StudyService(db).diff_configurations(study_id, user.id, from_version, to_version)


@router.get(
    "/studies/{study_id}/configurations/{version_number}",
    response_model=StudyConfigurationRead,
)
def study_configuration_by_version(
    study_id: int,
    version_number: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return a specific protocol version by its sequential version number."""
    return StudyService(db).get_configuration_by_version(study_id, user.id, version_number)


@router.post(
    "/studies/{study_id}/configurations",
    response_model=StudyConfigurationRead,
    status_code=201,
)
def create_study_configuration(
    study_id: int,
    payload: StudyConfigurationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return StudyService(db).create_configuration(study_id, user.id, payload)


@router.patch("/studies/{study_id}", response_model=StudyRead)
def update_study(
    study_id: int,
    payload: StudyUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return StudyService(db).update(study_id, user.id, payload)


@router.get("/studies/{study_id}/findings")
def study_findings(
    study_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    StudyService(db).get_owned(study_id, user.id)
    return ReportingService(db).study_findings(study_id)


@router.get("/studies/{study_id}/executive-report")
def executive_report(
    study_id: int,
    include_ai: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    study = StudyService(db).get_owned(study_id, user.id)
    path = ExecutiveReportService(db).build(study, include_ai=include_ai)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@router.get("/research-findings")
def all_findings(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = StudyService(db)
    return [
        {
            "study": StudyRead.model_validate(study),
            "evidence": ReportingService(db).study_findings(study.id),
        }
        for study in service.list(user.id)
    ]
