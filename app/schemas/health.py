from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    build_sha: str
    environment: str
    database: str
