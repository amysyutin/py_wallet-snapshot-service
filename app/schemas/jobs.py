from pydantic import BaseModel, model_validator

from app.enums import JobStatus, ScopeType, TriggerType


class SnapshotJobCreate(BaseModel):
    user_id: int
    trigger_type: TriggerType
    scope_type: ScopeType
    group_id: int | None = None
    wallet_id: int | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "SnapshotJobCreate":
        if self.scope_type == ScopeType.GROUP and self.group_id is None:
            raise ValueError("group_id is required for scope_type=group")
        if self.scope_type == ScopeType.WALLET and self.wallet_id is None:
            raise ValueError("wallet_id is required for scope_type=wallet")
        return self


class SnapshotJobCreateResponse(BaseModel):
    job_id: int
    status: JobStatus

