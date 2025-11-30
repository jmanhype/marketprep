/**
 * Settings page with profile management.
 */

import { useState, FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../components/Card';
import { Button } from '../components/Button';
import { Input } from '../components/Input';
import { useAuth } from '../contexts/AuthContext';
import { apiClient } from '../lib/api-client';

export function SettingsPage() {
  const { vendor, updateVendorProfile } = useAuth();
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [formData, setFormData] = useState({
    business_name: vendor?.business_name || '',
    phone: '',
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setIsSaving(true);

    try {
      const response = await apiClient.patch('/api/v1/vendors/me', {
        business_name: formData.business_name,
        phone: formData.phone || undefined,
      });

      // Update vendor in auth context
      updateVendorProfile(response);

      setSuccess('Profile updated successfully');
      setIsEditing(false);
    } catch (err: any) {
      setError(err.message || 'Failed to update profile');
    } finally {
      setIsSaving(false);
    }
  };

  const handleCancel = () => {
    setFormData({
      business_name: vendor?.business_name || '',
      phone: '',
    });
    setIsEditing(false);
    setError('');
    setSuccess('');
  };

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold text-gray-900">Settings</h1>

      {/* Profile Section */}
      <Card>
        <div className="p-6">
          <div className="flex justify-between items-start mb-6">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">Profile</h2>
              <p className="mt-1 text-sm text-gray-600">
                Manage your account information
              </p>
            </div>
            {!isEditing && (
              <Button onClick={() => setIsEditing(true)} variant="secondary">
                Edit
              </Button>
            )}
          </div>

          {error && (
            <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {success && (
            <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-md">
              <p className="text-sm text-green-800">{success}</p>
            </div>
          )}

          {isEditing ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label="Business Name"
                value={formData.business_name}
                onChange={(e) =>
                  setFormData({ ...formData, business_name: e.target.value })
                }
                required
              />

              <Input
                label="Phone Number"
                type="tel"
                value={formData.phone}
                onChange={(e) =>
                  setFormData({ ...formData, phone: e.target.value })
                }
                placeholder="(555) 555-5555"
              />

              <div className="pt-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Email
                </label>
                <p className="text-sm text-gray-900">{vendor?.email}</p>
                <p className="text-xs text-gray-500 mt-1">
                  Email cannot be changed
                </p>
              </div>

              <div className="flex gap-2 pt-4">
                <Button type="submit" isLoading={isSaving}>
                  Save Changes
                </Button>
                <Button
                  type="button"
                  onClick={handleCancel}
                  variant="secondary"
                >
                  Cancel
                </Button>
              </div>
            </form>
          ) : (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Business Name
                </label>
                <p className="text-sm text-gray-900">
                  {vendor?.business_name}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Email
                </label>
                <p className="text-sm text-gray-900">{vendor?.email}</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Subscription
                </label>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-1 text-xs font-medium bg-green-100 text-green-800 rounded">
                    {vendor?.subscription_tier?.toUpperCase()}
                  </span>
                  <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-800 rounded">
                    {vendor?.subscription_status}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Integration Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        <Link to="/settings/square">
          <Card hover padding>
            <h3 className="text-lg font-semibold mb-2">
              Square Integration
            </h3>
            <p className="text-gray-600">
              Connect and manage your Square account integration
            </p>
          </Card>
        </Link>

        <Card padding className="opacity-50">
          <h3 className="text-lg font-semibold mb-2">Advanced</h3>
          <p className="text-gray-600">
            Data export, account deletion (coming soon)
          </p>
        </Card>
      </div>
    </div>
  );
}
