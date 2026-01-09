"""Pydantic schemas for Rule API."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any

from app.models.rule import RuleType


class RuleAction(BaseModel):
    """Schema for rule action (what to do when rule matches)."""

    transaction_type: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    is_spend: Optional[bool] = None
    is_income: Optional[bool] = None


class RuleBase(BaseModel):
    """Base rule schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255)
    rule_type: RuleType
    pattern: str = Field(..., min_length=1, description="Pattern to match")
    action: RuleAction
    priority: int = Field(default=100, ge=0, description="Lower = higher priority")
    description: Optional[str] = None


class RuleCreate(RuleBase):
    """Schema for creating a new rule."""

    is_active: bool = Field(default=True)


class RuleUpdate(BaseModel):
    """Schema for updating a rule."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    pattern: Optional[str] = None
    action: Optional[RuleAction] = None
    priority: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    description: Optional[str] = None


class RuleResponse(RuleBase):
    """Schema for rule responses."""

    id: str
    user_id: str
    is_active: bool
    match_count: int
    created_at: datetime
    updated_at: datetime
    last_matched_at: Optional[datetime]

    class Config:
        from_attributes = True


class RuleListResponse(BaseModel):
    """Schema for list of rules."""

    rules: list[RuleResponse]
    total: int


class ApplyRulesRequest(BaseModel):
    """Schema for applying rules to existing transactions."""

    transaction_ids: Optional[list[str]] = Field(
        None,
        description="Specific transactions to re-classify. If None, apply to all."
    )
    rule_ids: Optional[list[str]] = Field(
        None,
        description="Specific rules to apply. If None, apply all active rules."
    )
