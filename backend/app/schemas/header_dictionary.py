"""Schemas for ERP header dictionary admin API."""

from typing import Dict, List

from pydantic import BaseModel, Field


class HeaderDictionaryPayload(BaseModel):
    """JSON body for GET/PUT header dictionary."""

    customer: List[str] = Field(..., min_length=1)
    product: List[str] = Field(..., min_length=1)
    quantity: List[str] = Field(..., min_length=1)


class HeaderDictionaryUpdateMeta(BaseModel):
    added: Dict[str, List[str]]
    removed: Dict[str, List[str]]


class HeaderDictionaryUpdateResponse(BaseModel):
    dictionary: HeaderDictionaryPayload
    changes: HeaderDictionaryUpdateMeta
