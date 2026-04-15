import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useToast } from '../components/Toast';
import Toggle from '../components/Toggle';
import { Slider } from '../components/ui';

function AlertThresholds() {
  const { t } = useTranslation();
  const { addToast } = useToast();
  const [severityThreshold, setSeverityThreshold] = useState(() => Number(localStorage.getItem('scirm_sev_threshold') || '70'));
  const [probabilityThreshold, setProbabilityThreshold] = useState(() => Number(localStorage.getItem('scirm_prob_threshold') || '60'));

  const handleSave = () => {
    localStorage.setItem('scirm_sev_threshold', String(severityThreshold));
    localStorage.setItem('scirm_prob_threshold', String(probabilityThreshold));
    addToast('success', t('settings.thresholdsSaved', 'Alert thresholds saved'));
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.alertThresholds', 'Alert Thresholds')}</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('settings.thresholdsDesc', 'Set minimum thresholds for triggering alerts. Risks below these thresholds will not generate alerts.')}</p>
      <div className="space-y-5">
        <Slider label={t('settings.severityThreshold', 'Severity Score Threshold')} value={severityThreshold} onChange={setSeverityThreshold} min={0} max={100} suffix="%" />
        <Slider label={t('settings.probabilityThreshold', 'Probability Threshold')} value={probabilityThreshold} onChange={setProbabilityThreshold} min={0} max={100} suffix="%" />
        <button onClick={handleSave} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">{t('settings.savePreferences', 'Save Preferences')}</button>
      </div>
    </div>
  );
}

const RISK_DIMENSIONS = [
  { key: 'financial', label: 'Financial / Liquidity' },
  { key: 'geopolitical', label: 'Geopolitical / Regulatory' },
  { key: 'environmental', label: 'Natural / Environmental' },
  { key: 'operational', label: 'Operational / Quality' },
  { key: 'compliance', label: 'Reputational / Compliance' },
  { key: 'cyber', label: 'Cybersecurity' },
  { key: 'resilience', label: 'Supply Chain Resilience' },
];

function ScoringWeights() {
  const { t } = useTranslation();
  const { addToast } = useToast();
  const [weights, setWeights] = useState<Record<string, number>>(() => {
    const saved = localStorage.getItem('scirm_scoring_weights');
    if (saved) return JSON.parse(saved);
    const defaults: Record<string, number> = {};
    RISK_DIMENSIONS.forEach((d) => { defaults[d.key] = Math.round(100 / RISK_DIMENSIONS.length); });
    return defaults;
  });

  const total = Object.values(weights).reduce((a, b) => a + b, 0);

  const updateWeight = (key: string, value: number) => {
    setWeights((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    localStorage.setItem('scirm_scoring_weights', JSON.stringify(weights));
    addToast('success', t('settings.weightsSaved', 'Scoring weights saved'));
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.scoringWeights', 'Risk Scoring Weights')}</h2>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('settings.weightsDesc', 'Customize how each risk dimension contributes to the overall risk score')}</p>
      <div className="space-y-4">
        {RISK_DIMENSIONS.map((dim) => (
          <Slider key={dim.key} label={dim.label} value={weights[dim.key] || 0} onChange={(v) => updateWeight(dim.key, v)} min={0} max={100} suffix="%" />
        ))}
        <div className="flex items-center justify-between pt-3 border-t border-gray-200 dark:border-gray-700">
          <span className={`text-sm font-medium ${total === 100 ? 'text-green-600' : 'text-yellow-600'}`}>
            {t('settings.totalWeight', 'Total')}: {total}%
            {total !== 100 && ` (${t('settings.shouldBe100', 'should be 100%')})`}
          </span>
          <button onClick={handleSave} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">{t('settings.savePreferences', 'Save Preferences')}</button>
        </div>
      </div>
    </div>
  );
}

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
  const { t, i18n } = useTranslation();

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
    addToast('success', t('settings.languageUpdated', 'Language updated'), t('settings.languageSetTo', 'Language set to {{language}}', { language: LANGUAGES.find((l) => l.code === code)?.label }));
  };

  const handleNotificationSave = () => {
    localStorage.setItem('scirm_email_alerts', String(emailAlerts));
    localStorage.setItem('scirm_slack_alerts', String(slackAlerts));
    localStorage.setItem('scirm_critical_only', String(criticalOnly));
    addToast('success', t('settings.preferencesSaved', 'Notification preferences saved'));
  };

  const handlePasswordChange = () => {
    setPasswordError('');
    if (newPassword.length < 8) {
      setPasswordError(t('auth.passwordTooShort', 'Password must be at least 8 characters'));
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError(t('auth.passwordMismatch', 'Passwords do not match'));
      return;
    }
    // In production, call API to change password
    addToast('success', t('settings.changePassword', 'Change Password'), t('settings.passwordUpdated', 'Your password has been changed successfully.'));
    setCurrentPassword('');
    setNewPassword('');
    setConfirmPassword('');
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{t('settings.title', 'Settings')}</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{t('settings.subtitle', 'Manage your account, preferences, and notifications')}</p>
      </div>

      {/* Profile */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.profile', 'Profile')}</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('settings.name', 'Name')}</label>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{user?.name || 'N/A'}</p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('settings.email', 'Email')}</label>
            <p className="text-sm font-medium text-gray-900 dark:text-white">{user?.email || 'N/A'}</p>
          </div>
          <div>
            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('settings.roles', 'Roles')}</label>
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
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.appearance', 'Appearance')}</h2>
        <Toggle
          enabled={theme === 'dark'}
          onChange={toggleTheme}
          label={t('settings.darkMode', 'Dark Mode')}
          description={t('settings.darkModeDesc', 'Switch between light and dark theme')}
        />
      </div>

      {/* Language */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.language', 'Language')}</h2>
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
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.notifications', 'Notifications')}</h2>
        <div className="space-y-4">
          <Toggle enabled={emailAlerts} onChange={setEmailAlerts} label={t('settings.emailAlerts', 'Email alerts')} description={t('settings.emailAlertsDesc', 'Receive risk alerts via email')} />
          <Toggle enabled={slackAlerts} onChange={setSlackAlerts} label={t('settings.slackAlerts', 'Slack alerts')} description={t('settings.slackAlertsDesc', 'Send alerts to Slack channel')} />
          <Toggle enabled={criticalOnly} onChange={setCriticalOnly} label={t('settings.criticalOnly', 'Critical only')} description={t('settings.criticalOnlyDesc', 'Only notify for critical/high severity risks')} />
          <button onClick={handleNotificationSave} className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
            {t('settings.savePreferences', 'Save Preferences')}
          </button>
        </div>
      </div>

      {/* Change Password */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.changePassword', 'Change Password')}</h2>
        <div className="space-y-3 max-w-sm">
          <input
            type="password"
            placeholder={t('settings.currentPassword', 'Current password')}
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
          />
          <input
            type="password"
            placeholder={t('settings.newPassword', 'New password (min 8 characters)')}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 outline-none"
          />
          <input
            type="password"
            placeholder={t('settings.confirmNewPassword', 'Confirm new password')}
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
            {t('settings.updatePassword', 'Update Password')}
          </button>
        </div>
      </div>

      {/* Alert Thresholds */}
      <AlertThresholds />

      {/* Risk Scoring Weights */}
      <ScoringWeights />

      {/* Export */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t('settings.dataExport', 'Data Export')}</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">{t('settings.dataExportDesc', 'Download reports for board meetings and auditors')}</p>
        <div className="flex flex-wrap gap-2">
          <a href="/api/v1/export/risks?format=csv" target="_blank" className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700">
            {t('settings.exportRisks', 'Export Risks (CSV)')}
          </a>
          <a href="/api/v1/export/suppliers?format=csv" target="_blank" className="px-4 py-2 bg-green-600 text-white rounded-lg text-sm font-medium hover:bg-green-700">
            {t('settings.exportSuppliers', 'Export Suppliers (CSV)')}
          </a>
          <a href="/api/v1/export/report?format=json" target="_blank" className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700">
            {t('settings.fullReport', 'Full Report (JSON)')}
          </a>
        </div>
      </div>
    </div>
  );
}
