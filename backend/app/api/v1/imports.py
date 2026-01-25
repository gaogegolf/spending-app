"""Imports API endpoints."""

from typing import Dict, Any
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
    account_id: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Upload a CSV or PDF file for import.

    Args:
        account_id: Account ID to associate with import
        file: Uploaded file (CSV or PDF)
        current_user: Authenticated user
        db: Database session

    Returns:
        Import record with PENDING status
    """
    # Verify account belongs to user
    account = db.query(Account).filter(
        Account.id == account_id,
        Account.user_id == current_user.id
    ).first()
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found"
        )

    import_service = ImportService(db)

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
        Preview with transactions, detected columns, duplicate count
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

    import_service = ImportService(db)

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
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Finalize import - classify and insert transactions into database.

    Args:
        import_id: Import record ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Import record with SUCCESS/PARTIAL/FAILED status
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

    import_service = ImportService(db)

    try:
        import_record = await import_service.commit_import(import_id)
        return import_record

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
    # Only list user's imports via Account join
    query = db.query(ImportRecord).join(Account).filter(Account.user_id == current_user.id)

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

    import_service = ImportService(db)

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
