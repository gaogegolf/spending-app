"""Backup/Export API endpoints for full data backup."""

import json
import zipfile
from datetime import datetime
from io import BytesIO
from fastapi import APIRouter, Depends, Query, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.middleware.auth import get_current_active_user
from app.services.backup_service import BackupService

router = APIRouter()


@router.get("/backup/export")
def export_full_backup(
    format: str = Query("json", description="Export format: json or zip"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Export all user data as JSON or ZIP archive.

    This endpoint exports all data belonging to the authenticated user:
    - Accounts
    - Transactions
    - Rules
    - Merchant categories
    - Import records
    - Holdings snapshots
    - Positions
    - FX rates

    Security: Only exports data belonging to the authenticated user.

    Args:
        format: Export format - "json" (single file) or "zip" (multiple files)

    Returns:
        Streaming file download
    """
    if format.lower() not in ("json", "zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}. Supported formats: json, zip"
        )

    service = BackupService(db)

    date_suffix = datetime.now().strftime('%Y%m%d_%H%M%S')
    # Sanitize username for filename (remove special chars)
    safe_username = "".join(c if c.isalnum() else "_" for c in current_user.username)
    base_filename = f"spending_app_backup_{safe_username}_{date_suffix}"

    as_zip = format.lower() == "zip"
    content = service.export_full_backup(
        user_id=current_user.id,
        username=current_user.username,
        as_zip=as_zip
    )

    if as_zip:
        return StreamingResponse(
            content,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={base_filename}.zip"
            }
        )
    else:
        return StreamingResponse(
            content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename={base_filename}.json"
            }
        )


@router.get("/backup/preview")
def preview_backup(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Preview what will be included in the backup without downloading.

    Returns data counts for each entity type that would be included in
    a full backup export. Useful for displaying to the user before export.

    Returns:
        Dictionary with data_counts for each entity type
    """
    service = BackupService(db)
    preview = service.get_backup_preview(current_user.id)
    return preview


@router.post("/backup/restore")
async def restore_backup(
    file: UploadFile = File(...),
    conflict_mode: str = Query("skip", description="How to handle duplicates: skip or error"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Restore data from a backup file (JSON or ZIP).

    This endpoint imports all data from a previously exported backup file.
    The data will be associated with the authenticated user, regardless of
    the original user_id in the backup.

    Supported formats:
    - JSON: Single backup file exported from /backup/export
    - ZIP: Archive with multiple JSON files exported from /backup/export

    Conflict handling:
    - skip: Skip records that already exist (default)
    - error: Return error if any record already exists

    Args:
        file: Backup file (JSON or ZIP)
        conflict_mode: How to handle duplicates

    Returns:
        Restore result with status, message, and details per entity type
    """
    if conflict_mode.lower() not in ("skip", "error"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conflict_mode: {conflict_mode}. Use 'skip' or 'error'"
        )

    # Read file content
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file uploaded"
        )

    # File size limit (50MB)
    max_size = 50 * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is 50MB"
        )

    # Determine file type and parse
    filename = file.filename or ""
    backup_data = None

    try:
        if filename.lower().endswith(".zip"):
            # Parse ZIP file
            backup_data = _parse_zip_backup(content)
        else:
            # Try JSON
            backup_data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON format: {str(e)}"
        )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ZIP file"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse backup file: {str(e)}"
        )

    if not backup_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not parse backup data"
        )

    # Perform restore
    service = BackupService(db)
    result = service.restore_from_backup(
        user_id=current_user.id,
        backup_data=backup_data,
        conflict_mode=conflict_mode.lower()
    )

    # Return appropriate status code based on result
    if result["status"] == "error":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result
        )

    return result


def _parse_zip_backup(content: bytes) -> dict:
    """Parse a ZIP backup file into a unified backup dictionary.

    Args:
        content: Raw ZIP file bytes

    Returns:
        Parsed backup data dictionary
    """
    backup_data = {}

    with zipfile.ZipFile(BytesIO(content), 'r') as zf:
        # Read metadata first
        if 'metadata.json' in zf.namelist():
            metadata_content = zf.read('metadata.json').decode('utf-8')
            backup_data['export_metadata'] = json.loads(metadata_content)

        # Read each data file
        file_mapping = {
            'accounts.json': 'accounts',
            'transactions.json': 'transactions',
            'rules.json': 'rules',
            'merchant_categories.json': 'merchant_categories',
            'import_records.json': 'import_records',
            'holdings_snapshots.json': 'holdings_snapshots',
            'positions.json': 'positions',
            'fx_rates.json': 'fx_rates',
        }

        for zip_filename, key in file_mapping.items():
            if zip_filename in zf.namelist():
                file_content = zf.read(zip_filename).decode('utf-8')
                backup_data[key] = json.loads(file_content)
            else:
                backup_data[key] = []

    return backup_data
