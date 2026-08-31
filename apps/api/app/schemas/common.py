from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    limit: Annotated[int, Field(default=25, ge=1, le=100)]
    offset: Annotated[int, Field(default=0, ge=0)]


class PaginatedResponse(BaseModel):
    total: int
    limit: int
    offset: int


class RecoveryCaseSort(str, Enum):
    PRIORITY_DESC = "priority_desc"
    AMOUNT_DESC = "amount_desc"
    OPENED_DESC = "opened_desc"


class DashboardSourceFilter(str, Enum):
    ALL = "all"
    SYNTHETIC = "synthetic"
    RAZORPAY_TEST = "razorpay_test"
