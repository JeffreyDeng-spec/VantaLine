"""Strict requests for existing Agent policy and cancellation routes."""
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=0)
    enabled: StrictBool
    budget: StrictInt = Field(ge=0,le=10**12)
    cloud_targets: list[str] = Field(default_factory=list,max_length=50)


class CancelOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: StrictInt = Field(ge=1)
