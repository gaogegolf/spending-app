"""Rules API endpoints."""

import re
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.rule import Rule, RuleType
from app.models.transaction import Transaction
from app.schemas.rule import (
    RuleCreate,
    RuleUpdate,
    RuleResponse,
    RuleListResponse
)
from app.services.classifier.rule_engine import RuleEngine

router = APIRouter()


def validate_pattern(rule_type: RuleType, pattern: str) -> None:
    """Validate pattern based on rule type.

    Args:
        rule_type: Type of rule
        pattern: Pattern to validate

    Raises:
        HTTPException: If pattern is invalid
    """
    if rule_type == RuleType.DESCRIPTION_REGEX:
        try:
            re.compile(pattern)
        except re.error as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid regex pattern: {str(e)}"
            )
    elif rule_type == RuleType.AMOUNT_RANGE:
        import json
        try:
            data = json.loads(pattern)
            if not isinstance(data, dict):
                raise ValueError("Pattern must be a JSON object")
            if 'min' not in data and 'max' not in data:
                raise ValueError("Pattern must have 'min' and/or 'max' fields")
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount range pattern must be valid JSON with 'min' and/or 'max' fields"
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )


@router.get("/rules", response_model=RuleListResponse)
def list_rules(
    rule_type: Optional[RuleType] = Query(None, description="Filter by rule type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by rule name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """List rules with filters and pagination.

    Args:
        rule_type: Filter by rule type
        is_active: Filter by active status
        search: Search by rule name
        page: Page number (1-indexed)
        page_size: Items per page
        db: Database session

    Returns:
        Paginated list of rules
    """
    query = db.query(Rule).filter(Rule.user_id == 'default_user')

    # Apply filters
    if rule_type:
        query = query.filter(Rule.rule_type == rule_type)
    if is_active is not None:
        query = query.filter(Rule.is_active == is_active)
    if search:
        query = query.filter(Rule.name.ilike(f"%{search}%"))

    # Get total count
    total = query.count()

    # Apply pagination and ordering (by priority, then created_at)
    offset = (page - 1) * page_size
    rules = query.order_by(
        Rule.priority.asc(),
        Rule.created_at.desc()
    ).offset(offset).limit(page_size).all()

    return RuleListResponse(
        rules=rules,
        total=total
    )


@router.get("/rules/{rule_id}", response_model=RuleResponse)
def get_rule(
    rule_id: str,
    db: Session = Depends(get_db)
):
    """Get rule by ID.

    Args:
        rule_id: Rule ID
        db: Database session

    Returns:
        Rule details
    """
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.user_id == 'default_user'
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found"
        )

    return rule


@router.post("/rules", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
def create_rule(
    data: RuleCreate,
    db: Session = Depends(get_db)
):
    """Create a new classification rule.

    Args:
        data: Rule creation data
        db: Database session

    Returns:
        Created rule
    """
    # Validate pattern based on rule type
    validate_pattern(data.rule_type, data.pattern)

    # Create rule
    rule = Rule(
        user_id='default_user',
        name=data.name,
        rule_type=data.rule_type,
        pattern=data.pattern,
        action=data.action.model_dump(),
        priority=data.priority,
        is_active=data.is_active,
        description=data.description,
        match_count=0
    )

    db.add(rule)
    db.commit()
    db.refresh(rule)

    return rule


@router.put("/rules/{rule_id}", response_model=RuleResponse)
def update_rule(
    rule_id: str,
    data: RuleUpdate,
    db: Session = Depends(get_db)
):
    """Update a rule.

    Args:
        rule_id: Rule ID
        data: Update data
        db: Database session

    Returns:
        Updated rule
    """
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.user_id == 'default_user'
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found"
        )

    # Validate pattern if being updated
    if data.pattern is not None:
        # Use existing rule_type if not being updated
        rule_type = rule.rule_type
        validate_pattern(rule_type, data.pattern)

    # Update fields
    if data.name is not None:
        rule.name = data.name
    if data.pattern is not None:
        rule.pattern = data.pattern
    if data.action is not None:
        rule.action = data.action.model_dump()
    if data.priority is not None:
        rule.priority = data.priority
    if data.is_active is not None:
        rule.is_active = data.is_active
    if data.description is not None:
        rule.description = data.description

    db.commit()
    db.refresh(rule)

    return rule


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db)
):
    """Delete a rule.

    Args:
        rule_id: Rule ID
        db: Database session
    """
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.user_id == 'default_user'
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found"
        )

    db.delete(rule)
    db.commit()


@router.post("/rules/{rule_id}/toggle", response_model=RuleResponse)
def toggle_rule(
    rule_id: str,
    db: Session = Depends(get_db)
):
    """Toggle rule active status.

    Args:
        rule_id: Rule ID
        db: Database session

    Returns:
        Updated rule
    """
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.user_id == 'default_user'
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found"
        )

    rule.is_active = not rule.is_active
    db.commit()
    db.refresh(rule)

    return rule


@router.post("/rules/bulk-delete", response_model=dict)
def bulk_delete_rules(
    rule_ids: List[str],
    db: Session = Depends(get_db)
):
    """Delete multiple rules.

    Args:
        rule_ids: List of rule IDs to delete
        db: Database session

    Returns:
        Count of deleted rules
    """
    deleted_count = db.query(Rule).filter(
        Rule.id.in_(rule_ids),
        Rule.user_id == 'default_user'
    ).delete(synchronize_session=False)

    db.commit()

    return {
        "deleted_count": deleted_count,
        "message": f"Successfully deleted {deleted_count} rules"
    }


@router.get("/rules/{rule_id}/match-count", response_model=dict)
def get_rule_match_count(
    rule_id: str,
    db: Session = Depends(get_db)
):
    """Get count of existing transactions that match this rule.

    Args:
        rule_id: Rule ID
        db: Database session

    Returns:
        Count of matching transactions
    """
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.user_id == 'default_user'
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found"
        )

    # Get all transactions and count matches
    rule_engine = RuleEngine(db)
    transactions = db.query(Transaction).all()

    match_count = 0
    for transaction in transactions:
        if rule_engine._rule_matches(rule, transaction):
            match_count += 1

    return {
        "rule_id": rule_id,
        "match_count": match_count,
        "message": f"Rule matches {match_count} existing transactions"
    }


@router.post("/rules/{rule_id}/apply", response_model=dict)
def apply_rule_to_transactions(
    rule_id: str,
    db: Session = Depends(get_db)
):
    """Apply a rule to all matching existing transactions.

    Args:
        rule_id: Rule ID
        db: Database session

    Returns:
        Count of updated transactions
    """
    rule = db.query(Rule).filter(
        Rule.id == rule_id,
        Rule.user_id == 'default_user'
    ).first()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule {rule_id} not found"
        )

    # Get all transactions
    rule_engine = RuleEngine(db)
    transactions = db.query(Transaction).all()

    updated_count = 0
    for transaction in transactions:
        if rule_engine._rule_matches(rule, transaction):
            # Apply the rule's action to this transaction
            rule_engine.apply_rule(rule, transaction)
            updated_count += 1

    # Update rule match statistics
    rule.match_count += updated_count
    rule.last_matched_at = datetime.utcnow()

    db.commit()

    return {
        "rule_id": rule_id,
        "updated_count": updated_count,
        "message": f"Successfully applied rule to {updated_count} transactions"
    }
