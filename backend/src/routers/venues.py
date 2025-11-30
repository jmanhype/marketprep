"""Venues API routes.

Endpoints:
- GET /venues - List vendor's venues
- POST /venues - Create new venue
- GET /venues/{venue_id} - Get venue details
- PATCH /venues/{venue_id} - Update venue
- DELETE /venues/{venue_id} - Delete venue
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from src.database import get_db
from src.middleware.auth import get_current_vendor
from src.models.venue import Venue
from src.schemas.venue import VenueCreate, VenueUpdate, VenueResponse


router = APIRouter(prefix="/venues", tags=["venues"])


@router.get("", response_model=List[VenueResponse])
def list_venues(
    vendor_id: UUID = Depends(get_current_vendor),
    db: Session = Depends(get_db),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
) -> List[VenueResponse]:
    """List all venues for the current vendor.

    Args:
        vendor_id: Current vendor ID from auth
        db: Database session
        is_active: Optional filter for active venues only

    Returns:
        List of venues belonging to the vendor
    """
    query = db.query(Venue).filter(Venue.vendor_id == vendor_id)

    if is_active is not None:
        query = query.filter(Venue.is_active == is_active)

    venues = query.order_by(Venue.name).all()

    return venues


@router.post("", response_model=VenueResponse, status_code=status.HTTP_201_CREATED)
def create_venue(
    venue: VenueCreate,
    vendor_id: UUID = Depends(get_current_vendor),
    db: Session = Depends(get_db),
) -> VenueResponse:
    """Create a new venue for the current vendor.

    Args:
        venue: Venue data
        vendor_id: Current vendor ID from auth
        db: Database session

    Returns:
        Created venue

    Raises:
        HTTPException: 400 if venue data is invalid
    """
    # Create new venue
    new_venue = Venue(
        vendor_id=vendor_id,
        name=venue.name,
        location=venue.location,
        latitude=venue.latitude,
        longitude=venue.longitude,
        typical_attendance=venue.typical_attendance,
        notes=venue.notes,
        is_active=venue.is_active,
    )

    db.add(new_venue)
    db.commit()
    db.refresh(new_venue)

    return new_venue


@router.get("/{venue_id}", response_model=VenueResponse)
def get_venue(
    venue_id: UUID,
    vendor_id: UUID = Depends(get_current_vendor),
    db: Session = Depends(get_db),
) -> VenueResponse:
    """Get details for a specific venue.

    Args:
        venue_id: Venue UUID
        vendor_id: Current vendor ID from auth
        db: Database session

    Returns:
        Venue details

    Raises:
        HTTPException: 404 if venue not found or doesn't belong to vendor
    """
    venue = (
        db.query(Venue)
        .filter(Venue.id == venue_id, Venue.vendor_id == vendor_id)
        .first()
    )

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    return venue


@router.patch("/{venue_id}", response_model=VenueResponse)
def update_venue(
    venue_id: UUID,
    venue_update: VenueUpdate,
    vendor_id: UUID = Depends(get_current_vendor),
    db: Session = Depends(get_db),
) -> VenueResponse:
    """Update a venue.

    Args:
        venue_id: Venue UUID
        venue_update: Updated venue data
        vendor_id: Current vendor ID from auth
        db: Database session

    Returns:
        Updated venue

    Raises:
        HTTPException: 404 if venue not found or doesn't belong to vendor
    """
    venue = (
        db.query(Venue)
        .filter(Venue.id == venue_id, Venue.vendor_id == vendor_id)
        .first()
    )

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    # Update only provided fields
    update_data = venue_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(venue, field, value)

    db.commit()
    db.refresh(venue)

    return venue


@router.delete("/{venue_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_venue(
    venue_id: UUID,
    vendor_id: UUID = Depends(get_current_vendor),
    db: Session = Depends(get_db),
) -> None:
    """Delete a venue.

    Args:
        venue_id: Venue UUID
        vendor_id: Current vendor ID from auth
        db: Database session

    Raises:
        HTTPException: 404 if venue not found or doesn't belong to vendor
    """
    venue = (
        db.query(Venue)
        .filter(Venue.id == venue_id, Venue.vendor_id == vendor_id)
        .first()
    )

    if not venue:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Venue not found",
        )

    db.delete(venue)
    db.commit()

    return None
