"""Pydantic schemas for Account API."""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from app.models.account import AccountType


class AccountBase(BaseModel):
    """Base account schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Account name")
    institution: Optional[str] = Field(None, max_length=255, description="Bank or card issuer")
    account_type: AccountType = Field(..., description="Type of account")
    account_number_last4: Optional[str] = Field(None, min_length=4, max_length=4, description="Last 4 digits")
    currency: str = Field(default="USD", min_length=3, max_length=3, description="Currency code")


class AccountCreate(AccountBase):
    """Schema for creating a new account."""

    pass


class AccountUpdate(BaseModel):
    """Schema for updating an existing account."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    institution: Optional[str] = Field(None, max_length=255)
    account_number_last4: Optional[str] = Field(None, min_length=4, max_length=4)
    is_active: Optional[bool] = None


class AccountResponse(AccountBase):
    """Schema for account responses."""

    id: str
    user_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2 (was orm_mode in v1)


class AccountListResponse(BaseModel):
    """Schema for list of accounts."""

    accounts: list[AccountResponse]
    total: int
