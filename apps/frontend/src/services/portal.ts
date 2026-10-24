import axios from 'axios';
import type { AssessmentQuestion } from './api';

// The supplier portal: a supplier answers a questionnaire through a personal link, with no
// account. Its own axios instance, without the app's interceptors, so a signed-in session
// in the same browser is never sent; the link's token goes in X-Portal-Token.
const portalClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

export interface PortalAssessment {
  id: string;
  organization_name: string | null;
  supplier_name: string | null;
  template_name: string;
  recipient_name: string;
  due_date: string | null;
  token_expires_at: string;
  questions: AssessmentQuestion[];
  answers: Record<string, unknown>;
}

const headers = (token: string) => ({ 'X-Portal-Token': token });

export const portal = {
  async load(token: string): Promise<PortalAssessment> {
    return (await portalClient.get('/api/v1/portal/assessment', { headers: headers(token) })).data.assessment;
  },

  async save(token: string, answers: Record<string, unknown>): Promise<void> {
    await portalClient.put('/api/v1/portal/assessment', { answers }, { headers: headers(token) });
  },

  async submit(token: string, answers: Record<string, unknown>, name: string, email: string): Promise<string> {
    return (await portalClient.post('/api/v1/portal/assessment/submit', { answers, name, email },
      { headers: headers(token) })).data.note;
  },
};

/** The token from the link's fragment (#...), which never reaches a server log. */
export function portalToken(hash: string): string {
  return hash.replace(/^#/, '').trim();
}
