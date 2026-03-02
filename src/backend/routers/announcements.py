"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    expiration_date: str
    start_date: Optional[str] = None


class AnnouncementUpdatePayload(BaseModel):
    message: str = Field(min_length=1, max_length=300)
    expiration_date: str
    start_date: Optional[str] = None


def _ensure_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _parse_iso_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must use YYYY-MM-DD format"
        ) from exc


def _validate_announcement_dates(start_date_value: Optional[str], expiration_date_value: str) -> Dict[str, Optional[str]]:
    expiration_date_parsed = _parse_iso_date(expiration_date_value, "expiration_date")

    normalized_start = None
    if start_date_value:
        start_date_parsed = _parse_iso_date(start_date_value, "start_date")
        if expiration_date_parsed < start_date_parsed:
            raise HTTPException(
                status_code=400,
                detail="expiration_date must be on or after start_date"
            )
        normalized_start = start_date_parsed.isoformat()

    return {
        "start_date": normalized_start,
        "expiration_date": expiration_date_parsed.isoformat()
    }


def _serialize_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": announcement.get("_id"),
        "message": announcement.get("message", ""),
        "start_date": announcement.get("start_date"),
        "expiration_date": announcement.get("expiration_date", ""),
        "created_by": announcement.get("created_by", "")
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get active announcements for public display."""
    today = date.today().isoformat()

    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$exists": False}},
            {"start_date": {"$lte": today}}
        ]
    }

    announcements: List[Dict[str, Any]] = []
    for announcement in announcements_collection.find(query).sort("expiration_date", 1):
        announcements.append(_serialize_announcement(announcement))

    return announcements


@router.get("", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for announcement management UI."""
    _ensure_teacher(teacher_username)

    announcements: List[Dict[str, Any]] = []
    for announcement in announcements_collection.find({}).sort("expiration_date", 1):
        announcements.append(_serialize_announcement(announcement))

    return announcements


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement."""
    teacher = _ensure_teacher(teacher_username)

    validated_dates = _validate_announcement_dates(payload.start_date, payload.expiration_date)
    message = payload.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    announcement_id = uuid4().hex
    announcement = {
        "_id": announcement_id,
        "message": message,
        "start_date": validated_dates["start_date"],
        "expiration_date": validated_dates["expiration_date"],
        "created_by": teacher["username"]
    }

    announcements_collection.insert_one(announcement)

    return _serialize_announcement(announcement)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementUpdatePayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement."""
    _ensure_teacher(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    validated_dates = _validate_announcement_dates(payload.start_date, payload.expiration_date)
    message = payload.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="message cannot be empty")

    announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": message,
                "start_date": validated_dates["start_date"],
                "expiration_date": validated_dates["expiration_date"]
            }
        }
    )

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement."""
    _ensure_teacher(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
