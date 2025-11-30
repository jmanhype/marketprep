/**
 * Venue API service.
 *
 * Provides methods for venue CRUD operations.
 */

import { apiClient } from '../lib/api-client';

export interface Venue {
  id: string;
  vendor_id: string;
  name: string;
  location: string;
  latitude?: number;
  longitude?: number;
  typical_attendance?: number;
  notes?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateVenueData {
  name: string;
  location: string;
  latitude?: number;
  longitude?: number;
  typical_attendance?: number;
  notes?: string;
  is_active?: boolean;
}

export interface UpdateVenueData {
  name?: string;
  location?: string;
  latitude?: number;
  longitude?: number;
  typical_attendance?: number;
  notes?: string;
  is_active?: boolean;
}

/**
 * List all venues for the current vendor.
 */
export async function listVenues(isActive?: boolean): Promise<Venue[]> {
  const params = new URLSearchParams();
  if (isActive !== undefined) {
    params.append('is_active', String(isActive));
  }

  const url = `/api/v1/venues${params.toString() ? `?${params}` : ''}`;
  return apiClient.get<Venue[]>(url);
}

/**
 * Get a single venue by ID.
 */
export async function getVenue(id: string): Promise<Venue> {
  return apiClient.get<Venue>(`/api/v1/venues/${id}`);
}

/**
 * Create a new venue.
 */
export async function createVenue(data: CreateVenueData): Promise<Venue> {
  return apiClient.post<Venue>('/api/v1/venues', data);
}

/**
 * Update an existing venue.
 */
export async function updateVenue(
  id: string,
  data: UpdateVenueData
): Promise<Venue> {
  return apiClient.patch<Venue>(`/api/v1/venues/${id}`, data);
}

/**
 * Delete a venue.
 */
export async function deleteVenue(id: string): Promise<void> {
  return apiClient.delete(`/api/v1/venues/${id}`);
}
