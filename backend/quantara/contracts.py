from datetime import date
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Source = Literal["erp", "bank", "fx"]
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.-]{1,100}$")]
Role = Literal[
    "FINANCIAL_ANALYST", "DATA_ANALYST", "DATA_ENGINEER", "DATA_STEWARD", "ADMIN"
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Delivery(Strict):
    sequence: Annotated[int, Field(strict=True, gt=0)]
    kind: Identifier
    external_id: Identifier
    revision: Annotated[int, Field(strict=True, gt=0)]
    event_time: AwareDatetime
    payload: dict


class Page(Strict):
    source: Source
    contract: Literal["source/1"]
    records: Annotated[list[Delivery], Field(max_length=100)]


class Login(Strict):
    login: Identifier
    password: Annotated[str, Field(min_length=1, max_length=128)]


class User(Login):
    name: Annotated[str, Field(min_length=2, max_length=80)]
    password: Annotated[str, Field(min_length=12, max_length=128)]
    role: Role


class Period(Strict):
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self):
        if self.end < self.start or (self.end - self.start).days > 365:
            raise ValueError("Period must be ordered and no longer than 366 days")
        return self


class Csv(Strict):
    text: Annotated[str, Field(min_length=1, max_length=100000)]


class Mapping(Strict):
    aliases: Annotated[dict[str, str], Field(max_length=25)]

    @model_validator(mode="after")
    def bounded(self):
        for key, value in self.aliases.items():
            if (
                not key.strip()
                or not value.strip()
                or len(key) > 120
                or len(value) > 120
            ):
                raise ValueError("Invalid alias")
        return self


class Scenario(Strict):
    revenue_percent: Annotated[int, Field(strict=True, ge=-100, le=200)] = 0
    expense_percent: Annotated[int, Field(strict=True, ge=-100, le=200)] = 0
    cash_in_percent: Annotated[int, Field(strict=True, ge=-100, le=200)] = 0
