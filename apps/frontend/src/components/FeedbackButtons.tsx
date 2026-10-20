import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api, FeedbackInput, FeedbackVerdict } from '../services/api';

export interface FeedbackOption {
  verdict: FeedbackVerdict;
  label: string;
}

interface Props {
  /** Everything but the verdict, which comes from the button pressed. */
  target: Omit<FeedbackInput, 'verdict'>;
  options: FeedbackOption[];
  initial?: FeedbackVerdict | null;
  prompt?: string;
}

// A row of small rating buttons. The chosen one stays highlighted; pressing another
// replaces the rating (the server keeps one per person per item).
export default function FeedbackButtons({ target, options, initial = null, prompt }: Props) {
  const { t } = useTranslation();
  const [chosen, setChosen] = useState<FeedbackVerdict | null>(initial);
  const [failed, setFailed] = useState(false);
  const [sending, setSending] = useState(false);
  const [saved, setSaved] = useState(false);

  const choose = async (verdict: FeedbackVerdict) => {
    if (sending || verdict === chosen) return;
    const previous = chosen;
    setChosen(verdict);
    setFailed(false);
    setSaved(false);
    setSending(true);
    try {
      await api.sendFeedback({ ...target, verdict });
      setSaved(true);
    } catch {
      setChosen(previous);
      setFailed(true);
    } finally {
      setSending(false);
    }
  };

  return (
    <span className="inline-flex items-center gap-1 flex-wrap">
      {prompt && <span className="text-[10px] text-gray-400">{prompt}</span>}
      {options.map((o) => (
        <button
          key={o.verdict}
          type="button"
          aria-pressed={chosen === o.verdict}
          onClick={() => choose(o.verdict)}
          className={`text-[10px] px-1.5 py-0.5 rounded border ${chosen === o.verdict
            ? 'bg-blue-600 border-blue-600 text-white'
            : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-blue-500 hover:text-blue-600'}`}
        >
          {o.label}
        </button>
      ))}
      {saved && <span className="text-[10px] text-green-600">{t('feedback.thanks', 'Thanks')}</span>}
      {failed && <span className="text-[10px] text-red-500">{t('feedback.failed', 'Not saved, try again')}</span>}
    </span>
  );
}
