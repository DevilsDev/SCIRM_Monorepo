import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { CheckCircleIcon } from '@heroicons/react/24/solid';

interface OnboardingWizardProps {
  onComplete: () => void;
}

const INDUSTRIES = ['pharmaceutical', 'healthcare', 'automotive', 'electronics', 'food_beverage', 'energy', 'manufacturing', 'general'];

export default function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1);
  const [industry, setIndustry] = useState('');
  const navigate = useNavigate();
  const { t } = useTranslation();

  const handleFinish = () => {
    localStorage.setItem('scirm_onboarded', 'true');
    localStorage.setItem('scirm_industry', industry);
    onComplete();
  };

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center">
      <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-lg w-full mx-4 overflow-hidden">
        {/* Progress */}
        <div className="px-6 pt-6 pb-4">
          <div className="flex items-center gap-3 mb-6">
            {[1, 2, 3].map((s) => (
              <div key={s} className="flex items-center gap-2 flex-1">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                  s < step ? 'bg-green-500 text-white' : s === step ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-500'
                }`}>
                  {s < step ? <CheckCircleIcon className="h-5 w-5" /> : s}
                </div>
                {s < 3 && <div className={`flex-1 h-0.5 ${s < step ? 'bg-green-500' : 'bg-gray-200 dark:bg-gray-700'}`} />}
              </div>
            ))}
          </div>

          {/* Step 1: Industry */}
          {step === 1 && (
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">{t('onboarding.welcome', 'Welcome to SCIRM')}</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">{t('onboarding.selectIndustry', 'Select your industry to get tailored risk insights')}</p>
              <div className="grid grid-cols-2 gap-2">
                {INDUSTRIES.map((ind) => (
                  <button
                    key={ind}
                    onClick={() => setIndustry(ind)}
                    className={`p-3 rounded-lg text-sm font-medium text-left capitalize border transition-colors ${
                      industry === ind ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' : 'border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                    }`}
                  >
                    {ind.replace('_', ' & ')}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Quick tour */}
          {step === 2 && (
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">{t('onboarding.quickTour', 'Quick Tour')}</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 mb-4">{t('onboarding.tourSubtitle', "Here's what you can do with SCIRM")}</p>
              <div className="space-y-3">
                {[
                  { title: t('onboarding.tourImport', 'Bring in your suppliers'), desc: t('onboarding.tourImportDesc', 'Import them from SAP, upload a list, or add them one by one') },
                  { title: t('onboarding.tourRecords', 'See their public records'), desc: t('onboarding.tourRecordsDesc', 'FDA recalls, warning letters, import alerts and shortages, matched to each supplier, with a Watch flag') },
                  { title: t('onboarding.tourAsk', 'Ask with citations'), desc: t('onboarding.tourAskDesc', 'Every sentence of an answer links to the record it comes from') },
                  { title: t('onboarding.tourRate', 'Tell us what is useful'), desc: t('onboarding.tourRateDesc', 'Rate records and answers; your ratings tune what SCIRM shows') },
                ].map((item, i) => (
                  <div key={i} className="flex gap-3 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <span className="text-blue-600 font-bold text-lg">{i + 1}</span>
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">{item.title}</p>
                      <p className="text-xs text-gray-500 dark:text-gray-400">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Step 3: Get started */}
          {step === 3 && (
            <div className="text-center">
              <div className="w-16 h-16 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
                <CheckCircleIcon className="h-10 w-10 text-green-500" />
              </div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-white">{t('onboarding.allSet', "You're All Set!")}</h2>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">{t('onboarding.allSetDesc', 'Start by running your first risk assessment or exploring the dashboard.')}</p>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-900 flex justify-between">
          {step > 1 ? (
            <button onClick={() => setStep(step - 1)} className="px-4 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
              {t('onboarding.back', 'Back')}
            </button>
          ) : (
            <button onClick={handleFinish} className="px-4 py-2 text-sm text-gray-400 hover:text-gray-600">{t('onboarding.skip', 'Skip')}</button>
          )}
          {step < 3 ? (
            <button
              onClick={() => setStep(step + 1)}
              disabled={step === 1 && !industry}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {t('onboarding.next', 'Next')}
            </button>
          ) : (
            <button onClick={handleFinish} className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700">
              {t('onboarding.goToDashboard', 'Go to Dashboard')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
