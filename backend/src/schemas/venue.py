"""Venue schemas for API validation."""
from typing import Optional
from uuid import UUID
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class VenueBase(BaseModel):
    """Base venue schema."""

    name: str = Field(..., max_length=255, description="Market or venue name")
    location: str = Field(..., max_length=500, description="Address or location description")
    latitude: Optional[Decimal] = Field(None, description="Latitude coordinate")
    longitude: Optional[Decimal] = Field(None, description="Longitude coordinate")
    typical_attendance: Optional[int] = Field(None, description="Typical number of customers")
    notes: Optional[str] = Field(None, description="Vendor notes about this venue")
    is_active: bool = Field(True, description="Whether vendor still attends this venue")


class VenueCreate(VenueBase):
    """Schema for creating a venue."""

    pass


class VenueUpdate(BaseModel):
    """Schema for updating a venue."""

    name: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=500)
    latitude: Optional[Decimal] = None
    longitude: Optional[Decimal] = None
    typical_attendance: Optional[int] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class VenueResponse(VenueBase):
    """Schema for venue response."""

    id: UUID
    vendor_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
