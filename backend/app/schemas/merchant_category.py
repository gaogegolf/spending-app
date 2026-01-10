"""Pydantic schemas for MerchantCategory API."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class MerchantCategoryBase(BaseModel):
    """Base merchant category schema with common fields."""

    merchant_normalized: str = Field(..., min_length=1, max_length=255, description="Normalized merchant name")
    category: str = Field(..., min_length=1, max_length=100, description="Category name")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score 0-1")
    source: str = Field(default="USER", description="Source: USER, AUTO, or LLM")


class MerchantCategoryCreate(MerchantCategoryBase):
    """Schema for creating a new merchant category mapping."""

    pass


class MerchantCategoryUpdate(BaseModel):
    """Schema for updating a merchant category mapping."""

    category: Optional[str] = Field(None, min_length=1, max_length=100)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)


class MerchantCategoryResponse(MerchantCategoryBase):
    """Schema for merchant category responses."""

    id: str
    user_id: str
    times_applied: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MerchantCategoryListResponse(BaseModel):
    """Schema for list of merchant categories."""

    merchant_categories: list[MerchantCategoryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
