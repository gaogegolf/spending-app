"""Merchant Categories API endpoints."""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.merchant_category import MerchantCategory
from app.models.transaction import Transaction
from app.models.account import Account
from app.models.user import User
from app.middleware.auth import get_current_active_user
from app.schemas.merchant_category import (
    MerchantCategoryCreate,
    MerchantCategoryUpdate,
    MerchantCategoryResponse,
    MerchantCategoryListResponse
)

router = APIRouter()


@router.get("/merchant-categories", response_model=MerchantCategoryListResponse)
def list_merchant_categories(
    merchant_search: Optional[str] = Query(None, description="Search merchant name"),
    source: Optional[str] = Query(None, description="Filter by source: USER, AUTO, LLM"),
    category: Optional[str] = Query(None, description="Filter by category"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List merchant category mappings with filters and pagination.

    Args:
        merchant_search: Search by merchant name (partial match)
        source: Filter by source (USER, AUTO, LLM)
        category: Filter by category name
        page: Page number (1-indexed)
        page_size: Items per page
        current_user: Authenticated user
        db: Database session

    Returns:
        Paginated list of merchant categories
    """
    query = db.query(MerchantCategory).filter(MerchantCategory.user_id == current_user.id)

    # Apply filters
    if merchant_search:
        query = query.filter(MerchantCategory.merchant_normalized.ilike(f"%{merchant_search}%"))
    if source:
        query = query.filter(MerchantCategory.source == source)
    if category:
        query = query.filter(MerchantCategory.category == category)

    # Get total count
    total = query.count()

    # Apply pagination and ordering
    offset = (page - 1) * page_size
    merchant_categories = query.order_by(
        MerchantCategory.times_applied.desc(),
        MerchantCategory.updated_at.desc()
    ).offset(offset).limit(page_size).all()

    has_more = (offset + len(merchant_categories)) < total

    return MerchantCategoryListResponse(
        merchant_categories=merchant_categories,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more
    )


@router.get("/merchant-categories/categories", response_model=List[str])
def list_unique_categories(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of unique categories used in merchant mappings.

    Args:
        current_user: Authenticated user

    Returns:
        List of unique category names
    """
    results = db.query(MerchantCategory.category).filter(
        MerchantCategory.user_id == current_user.id
    ).distinct().all()

    return sorted([r[0] for r in results])


@router.get("/merchant-categories/{mapping_id}", response_model=MerchantCategoryResponse)
def get_merchant_category(
    mapping_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get merchant category mapping by ID.

    Args:
        mapping_id: Merchant category mapping ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Merchant category details
    """
    mapping = db.query(MerchantCategory).filter(
        MerchantCategory.id == mapping_id,
        MerchantCategory.user_id == current_user.id
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Merchant category mapping {mapping_id} not found"
        )

    return mapping


@router.post("/merchant-categories", response_model=MerchantCategoryResponse, status_code=status.HTTP_201_CREATED)
def create_merchant_category(
    data: MerchantCategoryCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new merchant category mapping.

    If a mapping already exists for this merchant, it will be updated instead.

    Args:
        data: Merchant category creation data
        current_user: Authenticated user
        db: Database session

    Returns:
        Created or updated merchant category
    """
    # Check if mapping already exists
    existing = db.query(MerchantCategory).filter(
        MerchantCategory.user_id == current_user.id,
        MerchantCategory.merchant_normalized == data.merchant_normalized
    ).first()

    if existing:
        # Update existing mapping
        existing.category = data.category
        existing.confidence = data.confidence
        existing.source = data.source
        db.commit()
        db.refresh(existing)
        return existing

    # Create new mapping
    mapping = MerchantCategory(
        user_id=current_user.id,
        merchant_normalized=data.merchant_normalized,
        category=data.category,
        confidence=data.confidence,
        source=data.source,
        times_applied=0
    )

    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return mapping


@router.put("/merchant-categories/{mapping_id}", response_model=MerchantCategoryResponse)
def update_merchant_category(
    mapping_id: str,
    data: MerchantCategoryUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update a merchant category mapping.

    Args:
        mapping_id: Merchant category mapping ID
        data: Update data
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated merchant category
    """
    mapping = db.query(MerchantCategory).filter(
        MerchantCategory.id == mapping_id,
        MerchantCategory.user_id == current_user.id
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Merchant category mapping {mapping_id} not found"
        )

    # Update fields
    if data.category is not None:
        mapping.category = data.category
        mapping.source = 'USER'  # Mark as user-edited
    if data.confidence is not None:
        mapping.confidence = data.confidence

    db.commit()
    db.refresh(mapping)

    return mapping


@router.delete("/merchant-categories/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_merchant_category(
    mapping_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a merchant category mapping.

    Args:
        mapping_id: Merchant category mapping ID
        current_user: Authenticated user
        db: Database session
    """
    mapping = db.query(MerchantCategory).filter(
        MerchantCategory.id == mapping_id,
        MerchantCategory.user_id == current_user.id
    ).first()

    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Merchant category mapping {mapping_id} not found"
        )

    db.delete(mapping)
    db.commit()


@router.post("/merchant-categories/bulk-delete", response_model=dict)
def bulk_delete_merchant_categories(
    mapping_ids: List[str],
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete multiple merchant category mappings.

    Args:
        mapping_ids: List of mapping IDs to delete
        current_user: Authenticated user
        db: Database session

    Returns:
        Count of deleted mappings
    """
    deleted_count = db.query(MerchantCategory).filter(
        MerchantCategory.id.in_(mapping_ids),
        MerchantCategory.user_id == current_user.id
    ).delete(synchronize_session=False)

    db.commit()

    return {
        "deleted_count": deleted_count,
        "message": f"Successfully deleted {deleted_count} merchant category mappings"
    }


@router.post("/merchant-categories/refresh-counts", response_model=dict)
def refresh_merchant_counts(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Refresh times_applied counts for all merchant categories.

    Recalculates based on actual transaction counts per merchant.

    Args:
        current_user: Authenticated user
        db: Database session

    Returns:
        Summary of refreshed counts
    """
    # Get all merchant categories for this user
    merchant_categories = db.query(MerchantCategory).filter(
        MerchantCategory.user_id == current_user.id
    ).all()

    updated_mappings = []
    for mapping in merchant_categories:
        # Count only user's transactions with this merchant
        actual_count = db.query(Transaction).join(Account).filter(
            Transaction.merchant_normalized == mapping.merchant_normalized,
            Account.user_id == current_user.id
        ).count()

        # Update if different
        if mapping.times_applied != actual_count:
            old_count = mapping.times_applied
            mapping.times_applied = actual_count
            updated_mappings.append({
                "merchant": mapping.merchant_normalized,
                "old_count": old_count,
                "new_count": actual_count
            })

    db.commit()

    return {
        "total_merchants": len(merchant_categories),
        "updated_merchants": len(updated_mappings),
        "changes": updated_mappings,
        "message": f"Refreshed counts for {len(updated_mappings)} merchant mappings"
    }
