import { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import NotFoundPage from '../pages/NotFoundPage';
import { useFeatures } from '../services/features';

// A page that runs on built-in sample data. Hidden (Not Found) unless the deployment
// enables sample features; when shown, it says plainly that its numbers are samples.
export default function SampleRoute({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { loaded, samplePages } = useFeatures();
  if (!loaded) return null;
  if (!samplePages) return <NotFoundPage />;
  return (
    <>
      <div role="note" className="mb-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-xs text-amber-900">
        <strong>{t('sample.title', 'Sample data')}</strong>{' — '}
        {t('sample.body', 'This page runs on built-in sample data or an unvalidated formula. Its numbers are not an analysis of your suppliers. It is hidden outside development.')}
      </div>
      {children}
    </>
  );
}
