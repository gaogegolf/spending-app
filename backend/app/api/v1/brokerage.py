"""Brokerage API endpoints for investment statement imports."""

from typing import Dict, Any, List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.brokerage_import_service import BrokerageImportService
from app.models.account import Account
from app.models.import_record import ImportRecord
from app.models.holdings_snapshot import HoldingsSnapshot
from app.models.user import User
from app.middleware.auth import get_current_active_user

router = APIRouter()


@router.post("/brokerage/upload", status_code=status.HTTP_201_CREATED)
async def upload_brokerage_statement(
    file: UploadFile = File(...),
    account_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Upload a brokerage statement PDF.

    Auto-detects the brokerage provider (Fidelity, Schwab).

    Args:
        file: PDF statement file
        account_id: Optional account ID if known
        current_user: Authenticated user
        db: Database session

    Returns:
        Upload status with detected provider
    """
    # Verify account belongs to user if provided
    if account_id:
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == current_user.id
        ).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found"
            )

    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        result = await service.upload(file, account_id)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )


@router.post("/brokerage/{import_id}/parse")
async def parse_brokerage_statement(
    import_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Parse uploaded brokerage statement and return preview.

    Args:
        import_id: Import record ID from upload
        current_user: Authenticated user
        db: Database session

    Returns:
        Parsed holdings preview with reconciliation status
    """
    # Verify import belongs to user via Account join
    import_record = db.query(ImportRecord).join(Account).filter(
        ImportRecord.id == import_id,
        Account.user_id == current_user.id
    ).first()
    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        result = await service.parse(import_id)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse statement: {str(e)}"
        )


@router.post("/brokerage/{import_id}/commit")
async def commit_brokerage_import(
    import_id: str,
    account_id: Optional[str] = Form(None),
    create_account: bool = Form(True),
    account_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Commit parsed holdings to database.

    Creates a HoldingsSnapshot with all positions.

    Args:
        import_id: Import record ID
        account_id: Optional existing account ID
        create_account: If True, create new account if needed
        account_name: Name for new account
        current_user: Authenticated user
        db: Database session

    Returns:
        Commit result with snapshot ID
    """
    # Verify import belongs to user via Account join
    import_record = db.query(ImportRecord).join(Account).filter(
        ImportRecord.id == import_id,
        Account.user_id == current_user.id
    ).first()
    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    # Verify account_id belongs to user if provided
    if account_id:
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == current_user.id
        ).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Account not found"
            )

    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        result = await service.commit(
            import_id,
            account_id=account_id,
            create_account=create_account,
            account_name=account_name
        )
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to commit import: {str(e)}"
        )


@router.get("/brokerage/snapshots")
async def list_snapshots(
    account_id: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """List holdings snapshots with optional filters.

    Args:
        account_id: Filter by account
        start_date: Filter by start date
        end_date: Filter by end date
        current_user: Authenticated user
        db: Database session

    Returns:
        List of snapshot summaries
    """
    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        snapshots = service.get_snapshots(
            account_id=account_id,
            start_date=start_date,
            end_date=end_date
        )
        return {"snapshots": snapshots, "count": len(snapshots)}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list snapshots: {str(e)}"
        )


@router.get("/brokerage/snapshots/{snapshot_id}")
async def get_snapshot(
    snapshot_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get snapshot with positions.

    Args:
        snapshot_id: Snapshot ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Snapshot with full position details
    """
    # Verify snapshot belongs to user via Account join
    snapshot = db.query(HoldingsSnapshot).join(Account).filter(
        HoldingsSnapshot.id == snapshot_id,
        Account.user_id == current_user.id
    ).first()
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found"
        )

    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        result = service.get_snapshot_detail(snapshot_id)
        return result

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get snapshot: {str(e)}"
        )


@router.delete("/brokerage/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_snapshot(
    snapshot_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a holdings snapshot and its positions.

    Args:
        snapshot_id: Snapshot ID to delete
        current_user: Authenticated user
        db: Database session
    """
    from app.models.position import Position

    # Verify snapshot belongs to user via Account join
    snapshot = db.query(HoldingsSnapshot).join(Account).filter(
        HoldingsSnapshot.id == snapshot_id,
        Account.user_id == current_user.id
    ).first()
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Snapshot {snapshot_id} not found"
        )

    # Delete positions first
    db.query(Position).filter(Position.snapshot_id == snapshot_id).delete()
    # Delete snapshot
    db.delete(snapshot)
    db.commit()


@router.delete("/brokerage/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_brokerage_account(
    account_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete a brokerage account and all its snapshots/positions.

    Args:
        account_id: Account ID to delete
        current_user: Authenticated user
        db: Database session
    """
    from app.models.position import Position

    # Verify account belongs to user
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == current_user.id
    ).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Account {account_id} not found"
        )

    # Get all snapshots for this account
    snapshots = db.query(HoldingsSnapshot).filter(HoldingsSnapshot.account_id == account_id).all()
    snapshot_ids = [s.id for s in snapshots]

    # Delete positions
    if snapshot_ids:
        db.query(Position).filter(Position.snapshot_id.in_(snapshot_ids)).delete(synchronize_session=False)

    # Delete snapshots
    db.query(HoldingsSnapshot).filter(HoldingsSnapshot.account_id == account_id).delete(synchronize_session=False)

    # Delete account
    db.delete(account)
    db.commit()


@router.get("/brokerage/net-worth")
async def get_net_worth(
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get net worth across brokerage accounts.

    Returns current total and history for charting.

    Args:
        account_ids: Optional comma-separated list of account IDs
        current_user: Authenticated user
        db: Database session

    Returns:
        Net worth summary with history
    """
    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        account_id_list = account_ids.split(",") if account_ids else None
        result = service.get_net_worth(account_ids=account_id_list)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate net worth: {str(e)}"
        )


@router.get("/brokerage/net-worth/by-account")
async def get_net_worth_by_account(
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get net worth history broken down by account.

    Returns history with per-account values for stacked charts.

    Args:
        account_ids: Optional comma-separated list of account IDs
        current_user: Authenticated user
        db: Database session

    Returns:
        History with per-account breakdown
    """
    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        account_id_list = account_ids.split(",") if account_ids else None
        result = service.get_net_worth_by_account(account_ids=account_id_list)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get net worth by account: {str(e)}"
        )


@router.get("/brokerage/net-worth/by-asset-class")
async def get_asset_class_breakdown(
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """Get asset class breakdown of holdings.

    Returns current breakdown and history by asset class.

    Args:
        account_ids: Optional comma-separated list of account IDs
        current_user: Authenticated user
        db: Database session

    Returns:
        Current and historical breakdown by asset class
    """
    service = BrokerageImportService(db, user_id=current_user.id)

    try:
        account_id_list = account_ids.split(",") if account_ids else None
        result = service.get_asset_class_breakdown(account_ids=account_id_list)
        return result

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get asset class breakdown: {str(e)}"
        )
