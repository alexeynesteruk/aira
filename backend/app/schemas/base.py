"""Shared strict types. This package performs no I/O."""

from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

SCHEMA_VERSION: Final = "0.1.0"

type Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")]
type NonEmptyText = Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]
type Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
type PositiveInt = Annotated[int, Field(ge=1)]
type NonNegativeInt = Annotated[int, Field(ge=0)]
type FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)


class VersionedModel(StrictModel):
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
