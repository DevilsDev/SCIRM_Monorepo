import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useToast } from '../components/Toast';
import Toggle from '../components/Toggle';

const LANGUAGES = [
  { code: 'en', label: 'English' }, { code: 'es', label: 'Espanol' },
  { code: 'fr', label: 'Francais' }, { code: 'de', label: 'Deutsch' },
  { code: 'pt', label: 'Portugues' }, { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' }, { code: 'ko', label: '한국어' },
  { code: 'ar', label: 'العربية' }, { code: 'hi', label: 'हिन्दी' },
  { code: 'it', label: 'Italiano' }, { code: 'nl', label: 'Nederlands' },
];

export default function SettingsPage() {
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const { addToast } = useToast();
  const { i18n } = useTranslation();

  const [language, setLanguage] = useState(() => i18n.language || 'en');
  const [emailAlerts, setEmailAlerts] = useState(() => localStorage.getItem('scirm_email_alerts') !== 'false');
  const [slackAlerts, setSlackAlerts] = useState(() => localStorage.getItem('scirm_slack_alerts') !== 'false');
  const [criticalOnly, setCriticalOnly] = useState(() => localStorage.getItem('scirm_critical_only') === 'true');

  // Password change
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordError, setPasswordError] = useState('');

  const handleLanguageChange = (code: string) => {
    setLanguage(code);
    i18n.changeLanguage(code);
    addToast('success', 'Language updated', `Language set to ${LANGUAGES.find((l) => l.code === code)?.label}`);
  };

  const handleNotificationSave = () => {
    localStorage.setItem('scirm_email_alerts', String(emailAlerts));
    localStorage.setItem('scirm_slack_alerts', String(slackAlerts));
    localStorage.setItem('scirm_critical_only', String(criticalOnly));
    addToast('success', 'Notification preferences saved');
  };

  const handlePasswordChange = () => {
    setPasswordError('');
    if (newPassword.length < 8) {
      setPasswordError('Password must be at least 8 characters');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('Passwords do not match');
      return;
    }
    // In production, call API to change password
    addToast('success', 'Password updated', 'Your password has been changed successfully.');
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Settings</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Manage your account, preferences, and notifications</p>
      </div>

      {/* Profile */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Profile</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Name</label>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{user?.name || 'N/A'}</p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Email</label>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{user?.email || 'N/A'}</p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Roles</label>
            <div className="flex gap-1">
              {user?.roles?.map((role) => (
                <span key={role} className="px-2 py-0.5 bg-blue-100 text-blue-800 text-xs rounded-full capitalize">{role}</span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Appearance */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Appearance</h2>
        <Toggle
          enabled={theme === 'dark'}
          onChange={toggleTheme}
          label="Dark Mode"
          description="Switch between light and dark theme"
        />
      </div>

      {/* Language */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Language</h2>
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => handleLanguageChange(lang.code)}
              className={`p-2 rounded-lg text-sm font-medium border transition-colors ${
                language === lang.code
                  ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                  : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {lang.label}
            </button>
          ))}
        </div>
      </div>

      {/* Notifications */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Notifications</h2>
        <div className="space-y-4">
          <Toggle enabled={emailAlerts} onChange={setEmailAlerts} label="Email alerts" description="Receive risk alerts via email" />
          <Toggle enabled={slackAlerts} onChange={setSlackAlerts} label="Slack alerts" description="Send alerts to Slack channel" />
          <Toggle enabled={criticalOnly} onChange={setCriticalOnly} label="Critical only" description="Only notify for critical/high severity risks" />
          <button onClick={handleNotificationSave} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            Save Preferences
          </button>
        </div>
      </div>

      {/* Change Password */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Change Password</h2>
        <div className="space-y-3 max-w-sm">
          <input
            type="password"
            placeholder="Current password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
          />
          <input
            type="password"
            placeholder="New password (min 8 characters)"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
          />
          <input
            type="password"
            placeholder="Confirm new password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
          />
          {passwordError && <p className="text-xs text-red-500">{passwordError}</p>}
          <button
            onClick={handlePasswordChange}
            disabled={!currentPassword || !newPassword}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            Update Password
          </button>
        </div>
      </div>

      {/* Export */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Data Export</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">Download reports for board meetings and auditors</p>
        <div className="flex flex-wrap gap-2">
          <a href="/api/v1/export/risks?format=csv" target="_blank" className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700">
            Export Risks (CSV)
          </a>
          <a href="/api/v1/export/suppliers?format=csv" target="_blank" className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700">
            Export Suppliers (CSV)
          </a>
          <a href="/api/v1/export/report?format=json" target="_blank" className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700">
            Full Report (JSON)
          </a>
        </div>
      </div>
    </div>
  );
}
