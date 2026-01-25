'use client';

import { useState, useEffect } from 'react';
import { useAuth, getAuthHeader } from '@/lib/auth-context';
import PasswordStrengthIndicator from '@/app/components/PasswordStrengthIndicator';

interface Session {
  id: string;
  device_info: string | null;
  ip_address: string | null;
  created_at: string;
  last_activity: string;
  is_current: boolean;
}

const API_BASE_URL = '/api/v1';

export default function SettingsPage() {
  const { user, accessToken, refreshTokenValue, logout, updateUser } = useAuth();

  // Profile form state
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileMessage, setProfileMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Password form state
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Sessions state
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(true);

  // Delete account state
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Initialize form with user data
  useEffect(() => {
    if (user) {
      setEmail(user.email);
      setUsername(user.username);
    }
  }, [user]);

  // Fetch sessions
  useEffect(() => {
    fetchSessions();
  }, [accessToken]);

  async function fetchSessions() {
    if (!accessToken) return;

    try {
      const response = await fetch(`${API_BASE_URL}/auth/sessions`, {
        headers: getAuthHeader(),
      });

      if (response.ok) {
        const data = await response.json();
        setSessions(data.sessions);
      }
    } catch (error) {
      console.error('Failed to fetch sessions:', error);
    } finally {
      setSessionsLoading(false);
    }
  }

  async function handleProfileUpdate(e: React.FormEvent) {
    e.preventDefault();
    setProfileLoading(true);
    setProfileMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/profile`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({ email, username }),
      });

      if (response.ok) {
        const updatedUser = await response.json();
        updateUser(updatedUser);
        setProfileMessage({ type: 'success', text: 'Profile updated successfully' });
      } else {
        const error = await response.json();
        setProfileMessage({ type: 'error', text: error.detail || 'Failed to update profile' });
      }
    } catch (error) {
      setProfileMessage({ type: 'error', text: 'An error occurred' });
    } finally {
      setProfileLoading(false);
    }
  }

  async function handlePasswordChange(e: React.FormEvent) {
    e.preventDefault();

    if (newPassword !== confirmPassword) {
      setPasswordMessage({ type: 'error', text: 'Passwords do not match' });
      return;
    }

    if (newPassword.length < 8) {
      setPasswordMessage({ type: 'error', text: 'Password must be at least 8 characters' });
      return;
    }

    setPasswordLoading(true);
    setPasswordMessage(null);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });

      if (response.ok) {
        setPasswordMessage({ type: 'success', text: 'Password changed successfully' });
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
      } else {
        const error = await response.json();
        setPasswordMessage({ type: 'error', text: error.detail || 'Failed to change password' });
      }
    } catch (error) {
      setPasswordMessage({ type: 'error', text: 'An error occurred' });
    } finally {
      setPasswordLoading(false);
    }
  }

  async function handleRevokeSession(sessionId: string) {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: getAuthHeader(),
      });

      if (response.ok) {
        setSessions(sessions.filter(s => s.id !== sessionId));
      }
    } catch (error) {
      console.error('Failed to revoke session:', error);
    }
  }

  async function handleLogoutAll() {
    if (!refreshTokenValue) return;

    try {
      const response = await fetch(`${API_BASE_URL}/auth/logout-all`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({ refresh_token: refreshTokenValue }),
      });

      if (response.ok) {
        fetchSessions();
      }
    } catch (error) {
      console.error('Failed to logout all:', error);
    }
  }

  async function handleDeleteAccount() {
    setDeleteLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/auth/account`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({ password: deletePassword }),
      });

      if (response.ok) {
        logout();
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to delete account');
      }
    } catch (error) {
      alert('An error occurred');
    } finally {
      setDeleteLoading(false);
      setShowDeleteConfirm(false);
      setDeletePassword('');
    }
  }

  function formatDate(dateString: string) {
    return new Date(dateString).toLocaleString();
  }

  function parseUserAgent(ua: string | null) {
    if (!ua) return 'Unknown device';
    if (ua.includes('Chrome')) return 'Chrome Browser';
    if (ua.includes('Firefox')) return 'Firefox Browser';
    if (ua.includes('Safari')) return 'Safari Browser';
    if (ua.includes('curl')) return 'API Client';
    return ua.substring(0, 50);
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-8">
      <h1 className="text-2xl font-bold text-gray-900">Account Settings</h1>

      {/* Profile Section */}
      <section className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Profile Information</h2>

        <form onSubmit={handleProfileUpdate} className="space-y-4">
          {profileMessage && (
            <div className={`px-4 py-3 rounded-lg ${
              profileMessage.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}>
              {profileMessage.text}
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700">
              Email
            </label>
            <input
              type="email"
              id="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700">
              Username
            </label>
            <input
              type="text"
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              minLength={3}
              maxLength={100}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <button
            type="submit"
            disabled={profileLoading}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {profileLoading ? 'Saving...' : 'Save Changes'}
          </button>
        </form>
      </section>

      {/* Password Section */}
      <section className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Change Password</h2>

        <form onSubmit={handlePasswordChange} className="space-y-4">
          {passwordMessage && (
            <div className={`px-4 py-3 rounded-lg ${
              passwordMessage.type === 'success'
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}>
              {passwordMessage.text}
            </div>
          )}

          <div>
            <label htmlFor="currentPassword" className="block text-sm font-medium text-gray-700">
              Current Password
            </label>
            <input
              type="password"
              id="currentPassword"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <div>
            <label htmlFor="newPassword" className="block text-sm font-medium text-gray-700">
              New Password
            </label>
            <input
              type="password"
              id="newPassword"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
            />
            <PasswordStrengthIndicator password={newPassword} />
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700">
              Confirm New Password
            </label>
            <input
              type="password"
              id="confirmPassword"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          <button
            type="submit"
            disabled={passwordLoading}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
          >
            {passwordLoading ? 'Changing...' : 'Change Password'}
          </button>
        </form>
      </section>

      {/* Sessions Section */}
      <section className="bg-white rounded-lg shadow p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Active Sessions</h2>
          {sessions.length > 1 && (
            <button
              onClick={handleLogoutAll}
              className="text-sm text-red-600 hover:text-red-700"
            >
              Logout all other sessions
            </button>
          )}
        </div>

        {sessionsLoading ? (
          <p className="text-gray-500">Loading sessions...</p>
        ) : sessions.length === 0 ? (
          <p className="text-gray-500">No active sessions</p>
        ) : (
          <div className="space-y-3">
            {sessions.map((session, index) => (
              <div
                key={session.id}
                className="flex items-center justify-between p-4 border border-gray-200 rounded-lg"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">
                      {parseUserAgent(session.device_info)}
                    </span>
                    {index === 0 && (
                      <span className="text-xs bg-green-100 text-green-800 px-2 py-0.5 rounded">
                        Current
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-500">
                    {session.ip_address && <span>{session.ip_address} &middot; </span>}
                    Last active: {formatDate(session.last_activity)}
                  </div>
                </div>
                {index !== 0 && (
                  <button
                    onClick={() => handleRevokeSession(session.id)}
                    className="text-sm text-red-600 hover:text-red-700"
                  >
                    Revoke
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Delete Account Section */}
      <section className="bg-white rounded-lg shadow p-6 border-2 border-red-200">
        <h2 className="text-lg font-semibold text-red-600 mb-2">Danger Zone</h2>
        <p className="text-sm text-gray-600 mb-4">
          Once you delete your account, there is no going back. All your data will be permanently removed.
        </p>

        {!showDeleteConfirm ? (
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
          >
            Delete Account
          </button>
        ) : (
          <div className="space-y-4">
            <div>
              <label htmlFor="deletePassword" className="block text-sm font-medium text-gray-700">
                Enter your password to confirm
              </label>
              <input
                type="password"
                id="deletePassword"
                value={deletePassword}
                onChange={(e) => setDeletePassword(e.target.value)}
                className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-lg shadow-sm focus:outline-none focus:ring-red-500 focus:border-red-500"
              />
            </div>
            <div className="flex gap-3">
              <button
                onClick={handleDeleteAccount}
                disabled={deleteLoading || !deletePassword}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleteLoading ? 'Deleting...' : 'Confirm Delete'}
              </button>
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeletePassword('');
                }}
                className="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
