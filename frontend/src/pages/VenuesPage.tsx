/**
 * Venues management page.
 *
 * Allows vendors to manage their market/venue locations.
 */

import { useState, useEffect } from 'react';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import {
  listVenues,
  createVenue,
  updateVenue,
  deleteVenue,
  Venue,
  CreateVenueData,
} from '../services/venueService';

export function VenuesPage() {
  const [venues, setVenues] = useState<Venue[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingVenue, setEditingVenue] = useState<Venue | null>(null);
  const [filterActive, setFilterActive] = useState<boolean | undefined>(
    undefined
  );

  // Load venues on mount and when filter changes
  useEffect(() => {
    loadVenues();
  }, [filterActive]);

  const loadVenues = async () => {
    setIsLoading(true);
    setError('');
    try {
      const data = await listVenues(filterActive);
      setVenues(data);
    } catch (err: any) {
      setError(err.message || 'Failed to load venues');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreate = async (data: CreateVenueData) => {
    try {
      await createVenue(data);
      setShowCreateModal(false);
      await loadVenues();
    } catch (err: any) {
      throw new Error(err.message || 'Failed to create venue');
    }
  };

  const handleUpdate = async (id: string, data: Partial<CreateVenueData>) => {
    try {
      await updateVenue(id, data);
      setEditingVenue(null);
      await loadVenues();
    } catch (err: any) {
      throw new Error(err.message || 'Failed to update venue');
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Are you sure you want to delete "${name}"?`)) {
      return;
    }

    try {
      await deleteVenue(id);
      await loadVenues();
    } catch (err: any) {
      setError(err.message || 'Failed to delete venue');
    }
  };

  const handleToggleActive = async (venue: Venue) => {
    try {
      await updateVenue(venue.id, { is_active: !venue.is_active });
      await loadVenues();
    } catch (err: any) {
      setError(err.message || 'Failed to update venue');
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Venues</h1>
          <p className="mt-1 text-sm text-gray-600">
            Manage your market and venue locations
          </p>
        </div>
        <Button onClick={() => setShowCreateModal(true)}>Add Venue</Button>
      </div>

      {/* Filters */}
      <div className="flex gap-2">
        <button
          onClick={() => setFilterActive(undefined)}
          className={`px-3 py-1 rounded text-sm ${
            filterActive === undefined
              ? 'bg-green-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          All
        </button>
        <button
          onClick={() => setFilterActive(true)}
          className={`px-3 py-1 rounded text-sm ${
            filterActive === true
              ? 'bg-green-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Active
        </button>
        <button
          onClick={() => setFilterActive(false)}
          className={`px-3 py-1 rounded text-sm ${
            filterActive === false
              ? 'bg-green-600 text-white'
              : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
          }`}
        >
          Inactive
        </button>
      </div>

      {/* Error message */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md">
          <p className="text-sm text-red-800">{error}</p>
        </div>
      )}

      {/* Loading state */}
      {isLoading && (
        <div className="flex justify-center py-12">
          <div className="spinner h-8 w-8"></div>
        </div>
      )}

      {/* Venues list */}
      {!isLoading && venues.length === 0 && (
        <Card>
          <div className="p-12 text-center">
            <p className="text-gray-600">No venues found</p>
            <Button onClick={() => setShowCreateModal(true)} className="mt-4">
              Add Your First Venue
            </Button>
          </div>
        </Card>
      )}

      {!isLoading && venues.length > 0 && (
        <div className="grid gap-4">
          {venues.map((venue) => (
            <VenueCard
              key={venue.id}
              venue={venue}
              isEditing={editingVenue?.id === venue.id}
              onEdit={() => setEditingVenue(venue)}
              onCancelEdit={() => setEditingVenue(null)}
              onUpdate={(data) => handleUpdate(venue.id, data)}
              onDelete={() => handleDelete(venue.id, venue.name)}
              onToggleActive={() => handleToggleActive(venue)}
            />
          ))}
        </div>
      )}

      {/* Create modal */}
      {showCreateModal && (
        <VenueModal
          onClose={() => setShowCreateModal(false)}
          onSave={handleCreate}
        />
      )}
    </div>
  );
}

// Venue card component
interface VenueCardProps {
  venue: Venue;
  isEditing: boolean;
  onEdit: () => void;
  onCancelEdit: () => void;
  onUpdate: (data: Partial<CreateVenueData>) => Promise<void>;
  onDelete: () => void;
  onToggleActive: () => void;
}

function VenueCard({
  venue,
  isEditing,
  onEdit,
  onCancelEdit,
  onUpdate,
  onDelete,
  onToggleActive,
}: VenueCardProps) {
  const [formData, setFormData] = useState({
    name: venue.name,
    location: venue.location,
    typical_attendance: venue.typical_attendance || '',
    notes: venue.notes || '',
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    setIsSaving(true);
    setError('');
    try {
      await onUpdate({
        name: formData.name,
        location: formData.location,
        typical_attendance: formData.typical_attendance
          ? Number(formData.typical_attendance)
          : undefined,
        notes: formData.notes || undefined,
      });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  if (isEditing) {
    return (
      <Card>
        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          <Input
            label="Venue Name"
            value={formData.name}
            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            required
          />

          <Input
            label="Location"
            value={formData.location}
            onChange={(e) =>
              setFormData({ ...formData, location: e.target.value })
            }
            required
          />

          <Input
            label="Typical Attendance"
            type="number"
            value={formData.typical_attendance}
            onChange={(e) =>
              setFormData({ ...formData, typical_attendance: e.target.value })
            }
          />

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Notes
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) =>
                setFormData({ ...formData, notes: e.target.value })
              }
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500"
            />
          </div>

          <div className="flex gap-2">
            <Button onClick={handleSave} isLoading={isSaving}>
              Save
            </Button>
            <Button onClick={onCancelEdit} variant="secondary">
              Cancel
            </Button>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card>
      <div className="p-6">
        <div className="flex justify-between items-start">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-semibold text-gray-900">
                {venue.name}
              </h3>
              <span
                className={`px-2 py-1 text-xs rounded ${
                  venue.is_active
                    ? 'bg-green-100 text-green-800'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {venue.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>

            <p className="mt-1 text-sm text-gray-600">{venue.location}</p>

            {venue.typical_attendance && (
              <p className="mt-1 text-sm text-gray-500">
                Typical attendance: {venue.typical_attendance.toLocaleString()}{' '}
                customers
              </p>
            )}

            {venue.notes && (
              <p className="mt-2 text-sm text-gray-700">{venue.notes}</p>
            )}

            <p className="mt-2 text-xs text-gray-500">
              Added {new Date(venue.created_at).toLocaleDateString()}
            </p>
          </div>

          <div className="flex gap-2 ml-4">
            <button
              onClick={onToggleActive}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              {venue.is_active ? 'Deactivate' : 'Activate'}
            </button>
            <button
              onClick={onEdit}
              className="text-sm text-blue-600 hover:text-blue-800"
            >
              Edit
            </button>
            <button
              onClick={onDelete}
              className="text-sm text-red-600 hover:text-red-800"
            >
              Delete
            </button>
          </div>
        </div>
      </div>
    </Card>
  );
}

// Venue modal component
interface VenueModalProps {
  onClose: () => void;
  onSave: (data: CreateVenueData) => Promise<void>;
}

function VenueModal({ onClose, onSave }: VenueModalProps) {
  const [formData, setFormData] = useState({
    name: '',
    location: '',
    typical_attendance: '',
    notes: '',
    is_active: true,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError('');

    try {
      await onSave({
        name: formData.name,
        location: formData.location,
        typical_attendance: formData.typical_attendance
          ? Number(formData.typical_attendance)
          : undefined,
        notes: formData.notes || undefined,
        is_active: formData.is_active,
      });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
      <Card>
        <div className="p-6 max-w-md w-full">
          <h2 className="text-xl font-bold text-gray-900 mb-4">
            Add New Venue
          </h2>

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Venue Name"
              value={formData.name}
              onChange={(e) =>
                setFormData({ ...formData, name: e.target.value })
              }
              placeholder="Farmers Market at Main St"
              required
            />

            <Input
              label="Location"
              value={formData.location}
              onChange={(e) =>
                setFormData({ ...formData, location: e.target.value })
              }
              placeholder="123 Main St, City, State"
              required
            />

            <Input
              label="Typical Attendance"
              type="number"
              value={formData.typical_attendance}
              onChange={(e) =>
                setFormData({ ...formData, typical_attendance: e.target.value })
              }
              placeholder="500"
              helperText="Approximate number of customers"
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Notes
              </label>
              <textarea
                value={formData.notes}
                onChange={(e) =>
                  setFormData({ ...formData, notes: e.target.value })
                }
                rows={3}
                placeholder="Any additional details about this venue..."
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-green-500"
              />
            </div>

            <div className="flex items-center">
              <input
                type="checkbox"
                id="is_active"
                checked={formData.is_active}
                onChange={(e) =>
                  setFormData({ ...formData, is_active: e.target.checked })
                }
                className="h-4 w-4 text-green-600 focus:ring-green-500 border-gray-300 rounded"
              />
              <label
                htmlFor="is_active"
                className="ml-2 block text-sm text-gray-900"
              >
                Active venue (currently attending)
              </label>
            </div>

            <div className="flex gap-2 pt-4">
              <Button type="submit" fullWidth isLoading={isSaving}>
                Create Venue
              </Button>
              <Button
                type="button"
                onClick={onClose}
                variant="secondary"
                fullWidth
              >
                Cancel
              </Button>
            </div>
          </form>
        </div>
      </Card>
    </div>
  );
}
