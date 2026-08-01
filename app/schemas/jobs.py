from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator

from app.enums import JobStatus, ScopeType, TriggerType


class SnapshotJobCreate(BaseModel):
    user_id: int
    trigger_type: TriggerType
    scope_type: ScopeType
    group_id: int | None = None
    wallet_id: int | None = None
    activation_channel: Literal["web", "telegram"] | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "SnapshotJobCreate":
        if self.scope_type == ScopeType.GROUP and self.group_id is None:
            raise ValueError("group_id is required for scope_type=group")
        if self.scope_type == ScopeType.WALLET and self.wallet_id is None:
            raise ValueError("wallet_id is required for scope_type=wallet")
        if self.activation_channel is not None and (
            self.trigger_type != TriggerType.AUTO or self.scope_type != ScopeType.WALLET
        ):
            raise ValueError("activation_channel is only valid for auto wallet snapshot jobs")
        return self


class SnapshotJobCreateResponse(BaseModel):
    job_id: int
    status: JobStatus
    reused: bool = False


class SnapshotJobStatusResponse(BaseModel):
    job_id: int
    user_id: int
    trigger_type: TriggerType
    scope_type: ScopeType
    status: JobStatus
    group_id: int | None
    wallet_id: int | None
    parent_run_id: int | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
