"""Imports API endpoints."""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.import_service import ImportService
from app.schemas.import_record import (
    ImportStatusResponse,
    ImportPreview,
    ImportCommit,
    ImportListResponse
)
from app.models.import_record import ImportRecord
from app.models.account import Account
from app.models.user import User
from app.middleware.auth import get_current_active_user

router = APIRouter()


@router.post("/imports/upload", response_model=ImportStatusResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    account_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a CSV or PDF file for import.

    Args:
        file: Uploaded file (CSV or PDF)
        account_id: Account ID to associate with import (optional, for auto-detect mode)
        current_user: Authenticated user
        db: Database session

    Returns:
        Import record with PENDING status
    """
    # If account_id provided, verify it belongs to user
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

    import_service = ImportService(db, current_user.id)

    try:
        import_record = await import_service.process_upload(file, account_id)
        return import_record

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


@router.post("/imports/{import_id}/parse", response_model=Dict[str, Any])
async def parse_file(
    import_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Parse uploaded file and return preview.

    Args:
        import_id: Import record ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Preview with transactions, detected columns, duplicate count, detected institution
    """
    # Handle imports with or without account (left outer join for pending imports)
    import_record = db.query(ImportRecord).outerjoin(Account).filter(
        ImportRecord.id == import_id
    ).first()

    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    # Verify ownership: either through account or through user_id on import
    if import_record.account_id:
        account = db.query(Account).filter(
            Account.id == import_record.account_id,
            Account.user_id == current_user.id
        ).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Import {import_id} not found"
            )
    elif import_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    import_service = ImportService(db, current_user.id)

    try:
        preview = await import_service.parse_file(import_id)
        return preview

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
            detail=f"Failed to parse file: {str(e)}"
        )


@router.post("/imports/{import_id}/commit", response_model=ImportStatusResponse)
async def commit_import(
    import_id: str,
    account_id: Optional[str] = Form(None),
    create_account: bool = Form(True),
    account_name: Optional[str] = Form(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Finalize import - classify and insert transactions into database.

    Args:
        import_id: Import record ID
        account_id: Account ID to use (optional, overrides detected account)
        create_account: If True and no account_id, auto-create account from detection
        account_name: Custom name for auto-created account (optional)
        current_user: Authenticated user
        db: Database session

    Returns:
        Import record with SUCCESS/PARTIAL/FAILED status
    """
    # Handle imports with or without account
    import_record = db.query(ImportRecord).outerjoin(Account).filter(
        ImportRecord.id == import_id
    ).first()

    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    # Verify ownership
    if import_record.account_id:
        account = db.query(Account).filter(
            Account.id == import_record.account_id,
            Account.user_id == current_user.id
        ).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Import {import_id} not found"
            )
    elif import_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    # If account_id provided, verify it belongs to user
    if account_id:
        account = db.query(Account).filter(
            Account.id == account_id,
            Account.user_id == current_user.id
        ).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Specified account not found"
            )

    import_service = ImportService(db, current_user.id)

    try:
        import_record = await import_service.commit_import(
            import_id,
            account_id=account_id,
            create_account=create_account,
            account_name=account_name
        )

        # Look up account name for response
        acct_name = None
        if import_record.account_id:
            acct = db.query(Account).filter(Account.id == import_record.account_id).first()
            if acct:
                acct_name = acct.name

        return ImportStatusResponse(
            id=import_record.id,
            account_id=import_record.account_id,
            account_name=acct_name,
            user_id=import_record.user_id,
            source_type=import_record.source_type,
            filename=import_record.filename,
            status=import_record.status,
            error_message=import_record.error_message,
            transactions_imported=import_record.transactions_imported,
            transactions_duplicate=import_record.transactions_duplicate,
            created_at=import_record.created_at,
            completed_at=import_record.completed_at,
        )

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


@router.get("/imports/{import_id}", response_model=ImportStatusResponse)
def get_import_status(
    import_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get import status by ID.

    Args:
        import_id: Import record ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Import record details
    """
    # Handle imports with or without account
    import_record = db.query(ImportRecord).outerjoin(Account).filter(
        ImportRecord.id == import_id
    ).first()

    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    # Verify ownership
    if import_record.account_id:
        account = db.query(Account).filter(
            Account.id == import_record.account_id,
            Account.user_id == current_user.id
        ).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Import {import_id} not found"
            )
    elif import_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    return import_record


@router.get("/imports", response_model=ImportListResponse)
def list_imports(
    account_id: str = None,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List all imports.

    Args:
        account_id: Filter by account ID (optional)
        current_user: Authenticated user
        db: Database session

    Returns:
        List of import records
    """
    from sqlalchemy import or_

    # List user's imports - either via account ownership or direct user_id
    query = db.query(ImportRecord).outerjoin(Account).filter(
        or_(
            Account.user_id == current_user.id,
            ImportRecord.user_id == current_user.id
        )
    )

    if account_id:
        query = query.filter(ImportRecord.account_id == account_id)

    imports = query.order_by(ImportRecord.created_at.desc()).all()

    return ImportListResponse(
        imports=imports,
        total=len(imports)
    )


@router.delete("/imports/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_import(
    import_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Delete an import record and its file.

    Args:
        import_id: Import record ID
        current_user: Authenticated user
        db: Database session
    """
    # Handle imports with or without account
    import_record = db.query(ImportRecord).outerjoin(Account).filter(
        ImportRecord.id == import_id
    ).first()

    if not import_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    # Verify ownership
    if import_record.account_id:
        account = db.query(Account).filter(
            Account.id == import_record.account_id,
            Account.user_id == current_user.id
        ).first()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Import {import_id} not found"
            )
    elif import_record.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Import {import_id} not found"
        )

    import_service = ImportService(db, current_user.id)

    try:
        await import_service.delete_import(import_id)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete import: {str(e)}"
        )
