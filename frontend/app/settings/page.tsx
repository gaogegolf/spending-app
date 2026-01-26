'use client';

import { useState, useEffect } from 'react';
import { useAuth, getAuthHeader } from '@/lib/auth-context';
import PasswordStrengthIndicator from '@/app/components/PasswordStrengthIndicator';

// shadcn/ui components
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';

interface Session {
  id: string;
  device_info: string | null;
  ip_address: string | null;
  created_at: string;
  last_activity: string;
  is_current: boolean;
}

interface BackupPreview {
  data_counts: {
    accounts: number;
    transactions: number;
    rules: number;
    merchant_categories: number;
    import_records: number;
    holdings_snapshots: number;
    positions: number;
    fx_rates: number;
  };
}

interface RestoreResult {
  status: 'success' | 'partial' | 'error';
  message: string;
  details: {
    [key: string]: { created: number; skipped: number; errors: number };
  };
  errors: string[];
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

  // Backup state
  const [backupPreview, setBackupPreview] = useState<BackupPreview | null>(null);
  const [backupLoading, setBackupLoading] = useState(true);
  const [exportLoading, setExportLoading] = useState<'json' | 'zip' | null>(null);

  // Restore state
  const [restoreFile, setRestoreFile] = useState<File | null>(null);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [restoreResult, setRestoreResult] = useState<RestoreResult | null>(null);
  const [conflictMode, setConflictMode] = useState<'skip' | 'error'>('skip');

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

  // Fetch backup preview
  useEffect(() => {
    fetchBackupPreview();
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

  async function fetchBackupPreview() {
    if (!accessToken) return;

    try {
      const response = await fetch(`${API_BASE_URL}/backup/preview`, {
        headers: getAuthHeader(),
      });

      if (response.ok) {
        const data = await response.json();
        setBackupPreview(data);
      }
    } catch (error) {
      console.error('Failed to fetch backup preview:', error);
    } finally {
      setBackupLoading(false);
    }
  }

  async function handleExportBackup(format: 'json' | 'zip') {
    setExportLoading(format);

    try {
      const response = await fetch(`${API_BASE_URL}/backup/export?format=${format}`, {
        headers: getAuthHeader(),
      });

      if (response.ok) {
        // Get filename from Content-Disposition header or create default
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `spending_app_backup.${format}`;
        if (contentDisposition) {
          const match = contentDisposition.match(/filename=(.+)/);
          if (match) {
            filename = match[1].replace(/"/g, '');
          }
        }

        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } else {
        console.error('Failed to export backup');
      }
    } catch (error) {
      console.error('Failed to export backup:', error);
    } finally {
      setExportLoading(null);
    }
  }

  async function handleRestore() {
    if (!restoreFile) return;

    setRestoreLoading(true);
    setRestoreResult(null);

    try {
      const formData = new FormData();
      formData.append('file', restoreFile);

      const response = await fetch(
        `${API_BASE_URL}/backup/restore?conflict_mode=${conflictMode}`,
        {
          method: 'POST',
          headers: getAuthHeader(),
          body: formData,
        }
      );

      const data = await response.json();

      if (response.ok) {
        setRestoreResult(data);
        // Refresh the backup preview to show new counts
        fetchBackupPreview();
      } else {
        // Handle error response - detail might be the full result object or a string
        const errorDetail = data.detail;
        if (typeof errorDetail === 'object') {
          setRestoreResult(errorDetail);
        } else {
          setRestoreResult({
            status: 'error',
            message: errorDetail || 'Restore failed',
            details: {},
            errors: [errorDetail || 'Unknown error'],
          });
        }
      }
    } catch (error) {
      setRestoreResult({
        status: 'error',
        message: 'Failed to restore backup',
        details: {},
        errors: [String(error)],
      });
    } finally {
      setRestoreLoading(false);
      setRestoreFile(null);
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
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Account Settings</h1>
        <p className="text-muted-foreground">Manage your account settings and preferences</p>
      </div>

      {/* Profile Section */}
      <Card>
        <CardHeader>
          <CardTitle>Profile Information</CardTitle>
          <CardDescription>Update your account details</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleProfileUpdate} className="space-y-4">
            {profileMessage && (
              <Alert variant={profileMessage.type === 'error' ? 'destructive' : 'default'}>
                <AlertDescription>{profileMessage.text}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                type="email"
                id="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                type="text"
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                minLength={3}
                maxLength={100}
              />
            </div>

            <Button type="submit" disabled={profileLoading}>
              {profileLoading ? 'Saving...' : 'Save Changes'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Password Section */}
      <Card>
        <CardHeader>
          <CardTitle>Change Password</CardTitle>
          <CardDescription>Update your password to keep your account secure</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handlePasswordChange} className="space-y-4">
            {passwordMessage && (
              <Alert variant={passwordMessage.type === 'error' ? 'destructive' : 'default'}>
                <AlertDescription>{passwordMessage.text}</AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="currentPassword">Current Password</Label>
              <Input
                type="password"
                id="currentPassword"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="newPassword">New Password</Label>
              <Input
                type="password"
                id="newPassword"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
              />
              <PasswordStrengthIndicator password={newPassword} />
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPassword">Confirm New Password</Label>
              <Input
                type="password"
                id="confirmPassword"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
              />
            </div>

            <Button type="submit" disabled={passwordLoading}>
              {passwordLoading ? 'Changing...' : 'Change Password'}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Sessions Section */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <div>
              <CardTitle>Active Sessions</CardTitle>
              <CardDescription>Manage your active login sessions</CardDescription>
            </div>
            {sessions.length > 1 && (
              <Button variant="ghost" size="sm" onClick={handleLogoutAll} className="text-destructive hover:text-destructive">
                Logout all other sessions
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {sessionsLoading ? (
            <p className="text-muted-foreground">Loading sessions...</p>
          ) : sessions.length === 0 ? (
            <p className="text-muted-foreground">No active sessions</p>
          ) : (
            <div className="space-y-3">
              {sessions.map((session, index) => (
                <div
                  key={session.id}
                  className="flex items-center justify-between p-4 border rounded-lg"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium">
                        {parseUserAgent(session.device_info)}
                      </span>
                      {index === 0 && (
                        <Badge variant="secondary" className="bg-emerald-100 text-emerald-800">
                          Current
                        </Badge>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {session.ip_address && <span>{session.ip_address} &middot; </span>}
                      Last active: {formatDate(session.last_activity)}
                    </div>
                  </div>
                  {index !== 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRevokeSession(session.id)}
                      className="text-destructive hover:text-destructive"
                    >
                      Revoke
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Data Backup Section */}
      <Card>
        <CardHeader>
          <CardTitle>Data Backup</CardTitle>
          <CardDescription>
            Export all your data for backup or migration purposes
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {backupLoading ? (
            <p className="text-muted-foreground">Loading data summary...</p>
          ) : backupPreview ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                <div className="p-3 bg-muted rounded-lg">
                  <div className="font-medium text-foreground">{backupPreview.data_counts.accounts}</div>
                  <div className="text-muted-foreground">Accounts</div>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <div className="font-medium text-foreground">{backupPreview.data_counts.transactions.toLocaleString()}</div>
                  <div className="text-muted-foreground">Transactions</div>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <div className="font-medium text-foreground">{backupPreview.data_counts.rules}</div>
                  <div className="text-muted-foreground">Rules</div>
                </div>
                <div className="p-3 bg-muted rounded-lg">
                  <div className="font-medium text-foreground">{backupPreview.data_counts.merchant_categories}</div>
                  <div className="text-muted-foreground">Categories</div>
                </div>
              </div>

              {(backupPreview.data_counts.holdings_snapshots > 0 || backupPreview.data_counts.positions > 0) && (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="font-medium text-foreground">{backupPreview.data_counts.holdings_snapshots}</div>
                    <div className="text-muted-foreground">Snapshots</div>
                  </div>
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="font-medium text-foreground">{backupPreview.data_counts.positions}</div>
                    <div className="text-muted-foreground">Positions</div>
                  </div>
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="font-medium text-foreground">{backupPreview.data_counts.fx_rates}</div>
                    <div className="text-muted-foreground">FX Rates</div>
                  </div>
                  <div className="p-3 bg-muted rounded-lg">
                    <div className="font-medium text-foreground">{backupPreview.data_counts.import_records}</div>
                    <div className="text-muted-foreground">Imports</div>
                  </div>
                </div>
              )}

              <Separator />

              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={() => handleExportBackup('json')}
                  disabled={exportLoading !== null}
                >
                  {exportLoading === 'json' ? 'Downloading...' : 'Download JSON Backup'}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => handleExportBackup('zip')}
                  disabled={exportLoading !== null}
                >
                  {exportLoading === 'zip' ? 'Downloading...' : 'Download ZIP Archive'}
                </Button>
              </div>

              <p className="text-xs text-muted-foreground">
                JSON: Single file with all data. ZIP: Multiple files organized by type.
              </p>

              <Separator className="my-6" />

              {/* Restore Section */}
              <div className="space-y-4">
                <div>
                  <h4 className="font-medium text-foreground">Restore from Backup</h4>
                  <p className="text-sm text-muted-foreground">
                    Upload a previously exported backup file to restore your data
                  </p>
                </div>

                <div className="space-y-3">
                  <div className="space-y-2">
                    <Label htmlFor="restoreFile">Backup File</Label>
                    <Input
                      id="restoreFile"
                      type="file"
                      accept=".json,.zip"
                      onChange={(e) => {
                        setRestoreFile(e.target.files?.[0] || null);
                        setRestoreResult(null);
                      }}
                      disabled={restoreLoading}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Conflict Handling</Label>
                    <div className="flex gap-4">
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="radio"
                          name="conflictMode"
                          value="skip"
                          checked={conflictMode === 'skip'}
                          onChange={() => setConflictMode('skip')}
                          disabled={restoreLoading}
                        />
                        Skip duplicates
                      </label>
                      <label className="flex items-center gap-2 text-sm">
                        <input
                          type="radio"
                          name="conflictMode"
                          value="error"
                          checked={conflictMode === 'error'}
                          onChange={() => setConflictMode('error')}
                          disabled={restoreLoading}
                        />
                        Fail on conflict
                      </label>
                    </div>
                  </div>

                  <Button
                    onClick={handleRestore}
                    disabled={!restoreFile || restoreLoading}
                    variant="outline"
                  >
                    {restoreLoading ? 'Restoring...' : 'Restore from Backup'}
                  </Button>
                </div>

                {restoreResult && (
                  <Alert variant={restoreResult.status === 'error' ? 'destructive' : 'default'}>
                    <AlertDescription>
                      <div className="space-y-2">
                        <p className="font-medium">{restoreResult.message}</p>
                        {Object.keys(restoreResult.details).length > 0 && (
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                            {Object.entries(restoreResult.details).map(([key, counts]) => (
                              <div key={key} className="p-2 bg-muted/50 rounded">
                                <div className="font-medium capitalize">{key.replace('_', ' ')}</div>
                                <div>+{counts.created} created</div>
                                {counts.skipped > 0 && <div>{counts.skipped} skipped</div>}
                                {counts.errors > 0 && <div className="text-destructive">{counts.errors} errors</div>}
                              </div>
                            ))}
                          </div>
                        )}
                        {restoreResult.errors.length > 0 && (
                          <details className="text-xs">
                            <summary className="cursor-pointer text-destructive">
                              {restoreResult.errors.length} error(s)
                            </summary>
                            <ul className="mt-1 list-disc list-inside">
                              {restoreResult.errors.slice(0, 10).map((err, i) => (
                                <li key={i}>{err}</li>
                              ))}
                              {restoreResult.errors.length > 10 && (
                                <li>... and {restoreResult.errors.length - 10} more</li>
                              )}
                            </ul>
                          </details>
                        )}
                      </div>
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            </>
          ) : (
            <p className="text-muted-foreground">Unable to load data summary</p>
          )}
        </CardContent>
      </Card>

      {/* Delete Account Section */}
      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle className="text-destructive">Danger Zone</CardTitle>
          <CardDescription>
            Once you delete your account, there is no going back. All your data will be permanently removed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!showDeleteConfirm ? (
            <Button variant="destructive" onClick={() => setShowDeleteConfirm(true)}>
              Delete Account
            </Button>
          ) : (
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="deletePassword">Enter your password to confirm</Label>
                <Input
                  type="password"
                  id="deletePassword"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                />
              </div>
              <div className="flex gap-3">
                <Button
                  variant="destructive"
                  onClick={handleDeleteAccount}
                  disabled={deleteLoading || !deletePassword}
                >
                  {deleteLoading ? 'Deleting...' : 'Confirm Delete'}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setShowDeleteConfirm(false);
                    setDeletePassword('');
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
