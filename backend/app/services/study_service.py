from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.entities import ActivityLog, Study, StudyConfiguration
from app.repositories.sqlalchemy import StudyConfigurationRepository, StudyRepository
from app.schemas.contracts import (
    ProtocolFieldDiff,
    StudyConfigurationCreate,
    StudyConfigurationDiff,
    StudyCreate,
    StudyUpdate,
)
from app.utilities.hashing import canonical_hash

logger = logging.getLogger(__name__)

# Protocol fields that contribute to completeness scoring.
# 10 fields × 10 pts = 100 total.
_COMPLETENESS_FIELDS: list[str] = [
    "ml_task",
    "domain",
    "research_objective",
    "research_question",
    "hypothesis",
    "target_column",
    "primary_metric",
    "baseline_model",
    "validation_strategy",
    "random_seed",
]

# All protocol fields included in version diffs.
_PROTOCOL_FIELDS: list[str] = [
    "ml_task",
    "domain",
    "data_quality_focus",
    "research_objective",
    "research_question",
    "hypothesis",
    "target_column",
    "primary_metric",
    "baseline_model",
    "validation_strategy",
    "random_seed",
    "feature_scope",
    "intended_use_case",
]


class StudyService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = StudyRepository(db)
        self.configuration_repository = StudyConfigurationRepository(db)

    # ── Public methods ────────────────────────────────────────────────────────

    def create(self, owner_id: int, payload: StudyCreate) -> Study:
        study = self.repository.add(Study(owner_id=owner_id, **payload.model_dump()))
        configuration = self._create_configuration_version(
            study=study,
            actor_id=owner_id,
            data=self._configuration_data_from_study(study),
            change_reason="Initial research protocol",
            source_configuration_id=None,
        )
        self.db.add(ActivityLog(
            study_id=study.id,
            actor_id=owner_id,
            action="study.created",
            entity_type="study",
            entity_id=study.id,
            details_json={"ml_task": study.ml_task},
        ))
        self.db.add(ActivityLog(
            study_id=study.id,
            actor_id=owner_id,
            action="study.configuration.created",
            entity_type="study_configuration",
            entity_id=configuration.id,
            details_json={
                "version_number": configuration.version_number,
                "protocol_hash": configuration.protocol_hash,
                "completeness_score": configuration.completeness_score,
            },
        ))
        self.db.commit()
        self.db.refresh(study)
        return study

    def update(self, study_id: int, owner_id: int, payload: StudyUpdate) -> Study:
        study = self.get_owned(study_id, owner_id)
        changes = payload.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(study, key, value)
        configuration = None
        if {"ml_task", "description", "problem_objective", "intended_use_case"} & set(changes):
            configuration = self._create_configuration_version(
                study=study,
                actor_id=owner_id,
                data=self._configuration_data_from_study(study),
                change_reason="Study protocol updated through legacy study endpoint",
                source_configuration_id=self._current_config_id(study_id),
                skip_if_unchanged=True,
            )
        self.db.add(ActivityLog(
            study_id=study.id,
            actor_id=owner_id,
            action="study.updated",
            entity_type="study",
            entity_id=study.id,
            details_json={"fields": sorted(changes.keys())},
        ))
        if configuration:
            self.db.add(ActivityLog(
                study_id=study.id,
                actor_id=owner_id,
                action="study.configuration.created",
                entity_type="study_configuration",
                entity_id=configuration.id,
                details_json={
                    "version_number": configuration.version_number,
                    "protocol_hash": configuration.protocol_hash,
                    "completeness_score": configuration.completeness_score,
                },
            ))
        self.db.commit()
        self.db.refresh(study)
        return study

    def list(self, owner_id: int, search: str | None = None, ml_task: str | None = None):
        return self.repository.list_for_owner(owner_id, search, ml_task)

    def get_owned(self, study_id: int, owner_id: int) -> Study:
        study = self.db.query(Study).filter(
            Study.id == study_id, Study.owner_id == owner_id,
        ).first()
        if not study:
            raise ValueError("Study not found")
        return study

    def current_configuration(self, study_id: int, owner_id: int) -> StudyConfiguration:
        self.get_owned(study_id, owner_id)
        configuration = self.configuration_repository.current_for_study(study_id)
        if configuration:
            return configuration
        # Backfill: create a configuration from legacy study fields
        study = self.get_owned(study_id, owner_id)
        configuration = self._create_configuration_version(
            study=study,
            actor_id=owner_id,
            data=self._configuration_data_from_study(study),
            change_reason="Backfilled current research protocol",
            source_configuration_id=None,
        )
        self.db.commit()
        self.db.refresh(configuration)
        return configuration

    def list_configurations(self, study_id: int, owner_id: int):
        self.get_owned(study_id, owner_id)
        return self.configuration_repository.list_for_study(study_id)

    def create_configuration(
        self, study_id: int, owner_id: int, payload: StudyConfigurationCreate,
    ) -> StudyConfiguration:
        study = self.get_owned(study_id, owner_id)
        current_id = self._current_config_id(study_id)
        data = payload.model_dump(exclude={"change_reason"}, exclude_none=True)
        if payload.ml_task:
            study.ml_task = payload.ml_task
        data = {**self._configuration_data_from_study(study), **data}
        self._sync_study_from_configuration(study, data)
        configuration = self._create_configuration_version(
            study=study,
            actor_id=owner_id,
            data=data,
            change_reason=payload.change_reason or "Research protocol version created",
            source_configuration_id=current_id,
            skip_if_unchanged=True,
        )
        self.db.add(ActivityLog(
            study_id=study.id,
            actor_id=owner_id,
            action="study.configuration.created",
            entity_type="study_configuration",
            entity_id=configuration.id,
            details_json={
                "version_number": configuration.version_number,
                "protocol_hash": configuration.protocol_hash,
                "change_reason": payload.change_reason,
                "completeness_score": configuration.completeness_score,
                "missing_fields": configuration.missing_fields,
            },
        ))
        self.db.commit()
        self.db.refresh(configuration)
        return configuration

    def get_configuration_by_version(
        self, study_id: int, owner_id: int, version_number: int,
    ) -> StudyConfiguration:
        """Return a specific configuration version by its sequential version number."""
        self.get_owned(study_id, owner_id)
        configuration = self.configuration_repository.get_by_version_number(
            study_id, version_number,
        )
        if not configuration:
            raise ValueError(
                f"Configuration version {version_number} not found for this study"
            )
        return configuration

    def diff_configurations(
        self,
        study_id: int,
        owner_id: int,
        from_version: int,
        to_version: int,
    ) -> StudyConfigurationDiff:
        """Produce a field-level diff between two configuration versions."""
        self.get_owned(study_id, owner_id)
        from_config, to_config = self.configuration_repository.get_pair_for_diff(
            study_id, from_version, to_version,
        )
        if not from_config:
            raise ValueError(f"Configuration version {from_version} not found")
        if not to_config:
            raise ValueError(f"Configuration version {to_version} not found")

        field_diffs: list[ProtocolFieldDiff] = []
        fields_changed: list[str] = []
        fields_added: list[str] = []
        fields_removed: list[str] = []

        for field in _PROTOCOL_FIELDS:
            from_val = getattr(from_config, field)
            to_val = getattr(to_config, field)
            changed = from_val != to_val
            if changed:
                fields_changed.append(field)
                if not from_val and to_val:
                    fields_added.append(field)
                elif from_val and not to_val:
                    fields_removed.append(field)
            field_diffs.append(ProtocolFieldDiff(
                field=field,
                from_value=from_val,
                to_value=to_val,
                changed=changed,
            ))

        return StudyConfigurationDiff(
            study_id=study_id,
            from_version=from_version,
            to_version=to_version,
            from_hash=from_config.protocol_hash,
            to_hash=to_config.protocol_hash,
            hash_changed=from_config.protocol_hash != to_config.protocol_hash,
            completeness_delta=to_config.completeness_score - from_config.completeness_score,
            from_completeness_score=from_config.completeness_score,
            to_completeness_score=to_config.completeness_score,
            fields_changed=fields_changed,
            fields_added=fields_added,
            fields_removed=fields_removed,
            field_diffs=field_diffs,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _current_config_id(self, study_id: int) -> int | None:
        """Return the ID of the current configuration without raising."""
        current = self.configuration_repository.current_for_study(study_id)
        return current.id if current else None

    def _create_configuration_version(
        self,
        study: Study,
        actor_id: int,
        data: dict,
        change_reason: str,
        source_configuration_id: int | None = None,
        skip_if_unchanged: bool = False,
    ) -> StudyConfiguration:
        protocol_json = self._protocol_json(data, change_reason)
        protocol_hash = canonical_hash({
            "schema_version": protocol_json["schema_version"],
            "fields": protocol_json["fields"],
        })
        current = self.configuration_repository.current_for_study(study.id)
        if skip_if_unchanged and current and current.protocol_hash == protocol_hash:
            return current

        now = datetime.now(tz=timezone.utc)

        if current:
            current.status = "archived"
            current.superseded_at = now
            self.db.flush()

        completeness_score, missing_fields = self._compute_completeness(data)

        configuration = StudyConfiguration(
            study_id=study.id,
            created_by=actor_id,
            source_configuration_id=source_configuration_id,
            version_number=self.configuration_repository.next_version_number(study.id),
            status="current",
            ml_task=data["ml_task"],
            domain=data.get("domain"),
            data_quality_focus=data.get("data_quality_focus"),
            research_objective=data.get("research_objective"),
            research_question=data.get("research_question"),
            hypothesis=data.get("hypothesis"),
            target_column=data.get("target_column"),
            primary_metric=data.get("primary_metric"),
            baseline_model=data.get("baseline_model"),
            validation_strategy=data.get("validation_strategy"),
            random_seed=data.get("random_seed"),
            feature_scope=data.get("feature_scope"),
            intended_use_case=data.get("intended_use_case"),
            protocol_json=protocol_json,
            protocol_hash=protocol_hash,
            change_reason=change_reason,
            completeness_score=completeness_score,
            missing_fields=missing_fields,
        )
        self.db.add(configuration)
        self.db.flush()
        logger.info(
            "study.configuration.version_created study_id=%s version=%s completeness=%s hash=%s",
            study.id,
            configuration.version_number,
            completeness_score,
            protocol_hash[:8],
        )
        return configuration

    @staticmethod
    def _compute_completeness(data: dict) -> tuple[int, list[str]]:
        """
        Compute protocol completeness (0–100) and list of missing field names.
        Each of the 10 fields in _COMPLETENESS_FIELDS contributes 10 points.
        Special case: random_seed=0 is valid (counts as present); None is missing.
        """
        missing: list[str] = []
        for field in _COMPLETENESS_FIELDS:
            value = data.get(field)
            if field == "random_seed":
                if value is None:
                    missing.append(field)
            else:
                if not value:
                    missing.append(field)
        score = max(0, 100 - len(missing) * 10)
        return score, missing

    @staticmethod
    def _parse_lines(text: str | None) -> dict[str, str]:
        values = {}
        for line in str(text or "").splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            values[key.strip().lower()] = value.strip()
        return values

    def _configuration_data_from_study(self, study: Study) -> dict:
        description = self._parse_lines(study.description)
        intended = self._parse_lines(study.intended_use_case)
        return {
            "ml_task": study.ml_task,
            "domain": description.get("domain"),
            "data_quality_focus": intended.get("data quality focus"),
            "research_objective": study.problem_objective,
            "research_question": description.get("research question"),
            "hypothesis": description.get("hypothesis"),
            "target_column": description.get("target or grouping goal"),
            "primary_metric": intended.get("primary metric"),
            "baseline_model": intended.get("controlled model"),
            "validation_strategy": intended.get("validation plan"),
            "random_seed": self._parse_seed(intended.get("random seed")),
            "feature_scope": intended.get("feature scope"),
            "intended_use_case": intended.get("intended research use") or study.intended_use_case,
        }

    @staticmethod
    def _parse_seed(value: str | None) -> int | None:
        if value is None or value == "":
            return None
        try:
            seed = int(value)
        except ValueError as exc:
            raise ValueError("Random seed must be an integer") from exc
        if seed < 0:
            raise ValueError("Random seed must be zero or greater")
        return seed

    @staticmethod
    def _protocol_json(data: dict, change_reason: str) -> dict:
        fields = {
            "ml_task": data.get("ml_task"),
            "domain": data.get("domain"),
            "data_quality_focus": data.get("data_quality_focus"),
            "research_objective": data.get("research_objective"),
            "research_question": data.get("research_question"),
            "hypothesis": data.get("hypothesis"),
            "target_column": data.get("target_column"),
            "primary_metric": data.get("primary_metric"),
            "baseline_model": data.get("baseline_model"),
            "validation_strategy": data.get("validation_strategy"),
            "random_seed": data.get("random_seed"),
            "feature_scope": data.get("feature_scope"),
            "intended_use_case": data.get("intended_use_case"),
        }
        return {
            "schema_version": "study-protocol-1.0",
            "change_reason": change_reason,
            "fields": fields,
        }

    @staticmethod
    def _sync_study_from_configuration(study: Study, data: dict) -> None:
        target = (
            data.get("feature_scope")
            if data.get("ml_task") == "clustering"
            else data.get("target_column")
        )
        study.ml_task = data.get("ml_task") or study.ml_task
        study.description = "\n".join(
            line for line in [
                f"Domain: {data.get('domain') or ''}",
                f"Task: {study.ml_task}",
                f"Research question: {data.get('research_question') or ''}",
                f"Hypothesis: {data.get('hypothesis') or ''}",
                f"Target or grouping goal: {target or ''}",
            ] if not line.endswith(": ")
        ) or None
        study.problem_objective = data.get("research_objective")
        study.intended_use_case = "\n".join(
            line for line in [
                f"Intended research use: {data.get('intended_use_case') or ''}",
                f"Data quality focus: {data.get('data_quality_focus') or ''}",
                f"Primary metric: {data.get('primary_metric') or ''}",
                f"Controlled model: {data.get('baseline_model') or ''}",
                f"Validation plan: {data.get('validation_strategy') or ''}",
                f"Random seed: {data.get('random_seed') if data.get('random_seed') is not None else ''}",
                f"Feature scope: {data.get('feature_scope') or ''}",
            ] if not line.endswith(": ")
        ) or None
