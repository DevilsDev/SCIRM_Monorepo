import axios from 'axios';
import { isAuthRequest, Session } from './session';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Tokens and 401 handling (see services/session.ts). The refresh call uses a bare
// axios request so it never passes back through these interceptors.
export const session = new Session(window.localStorage, async (refreshToken) => {
  const response = await axios.post(`${API_BASE_URL}/api/v1/auth/refresh`, { refresh_token: refreshToken },
    { timeout: 15000 });
  return response.data.access_token as string;
});

apiClient.interceptors.request.use(
  (config) => {
    const token = session.accessToken;
    if (token && !isAuthRequest(config.url)) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status === 401 && original && !isAuthRequest(original.url) && !original._retried) {
      const fresh = await session.handleUnauthorized();
      if (fresh) {
        original._retried = true;
        original.headers.Authorization = `Bearer ${fresh}`;
        return apiClient(original);
      }
    }
    return Promise.reject(error);
  }
);

export interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  token_type: string;
  mfa_required?: boolean;
  mfa_token?: string;
}

export interface Risk {
  id: string;
  title: string;
  description: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  probability: number;
  impact_score: number;
  affected_entities: string[];
  risk_category: string;
  detected_at: string;
  predicted_occurrence?: string;
  data_sources: string[];
}

export interface Recommendation {
  id: string;
  risk_id: string;
  title: string;
  description: string;
  action_type: string;
  priority: string;
  estimated_cost?: number;
  estimated_impact: number;
  timeline_days?: number;
  resources_required: string[];
  success_probability: number;
}

export interface Supplier {
  id: string;
  organization_id: string;
  supplier_code: string;
  name: string;
  supplier_type: string;
  country_code: string;
  region: string;
  risk_score: number;
  risk_tier: string;
  contact_name?: string;
  contact_email?: string;
  is_active: boolean;
  /** Set on demo suppliers named after real companies: their score is a placeholder. */
  demo_note?: string;
}

export interface Alert {
  id: string;
  alert_type: string;
  severity: string;
  title: string;
  description: string;
  status: string;
  created_at: string;
}

export interface RiskAssessmentRequest {
  entities: Array<{
    id: string;
    name: string;
    type: string;
    location?: string;
    metadata?: Record<string, any>;
  }>;
  assessment_type?: string;
  time_horizon_days?: number;
  priority_factors?: string[];
  context?: Record<string, any>;
}

export interface RiskAssessmentResponse {
  task_id: string;
  risks: Risk[];
  recommendations: Recommendation[];
  confidence_score: number;
  reasoning_trail: Array<{
    agent: string;
    step: string;
    reasoning: string;
    output: string;
    confidence: number;
    data_sources: string[];
  }>;
  metadata: Record<string, any>;
}

export interface PublicSignal {
  id: string;
  source: string;
  source_label: string;
  signal_type: string;
  title: string;
  content: string;
  url: string | null;
  severity: string;
  region: string;
  entity_names: string[];
  country_codes: string[];
  published_at: string;
  occurred_at: string | null;
  updated_at: string | null;
  ingested_at: string;
}

export interface SignalMatch {
  match_type: 'name_exact' | 'name_contains' | 'name_similar' | 'parent_company' | 'country_exposure';
  confidence: number;
  kind: 'incident' | 'exposure';
  matched_on: string;
  signal: PublicSignal;
}

export interface SupplierSignals {
  supplier_id: string;
  supplier_name: string;
  incidents: SignalMatch[];
  exposures: SignalMatch[];
  incident_total: number;
  exposure_total: number;
}

export interface SupplierSignalSummary {
  supplier_id: string;
  supplier_name: string;
  incidents: number;
  exposures: number;
  worst_incident_severity: string | null;
  latest_incident_published_at: string | null;
  /** Back-tested recall-history flag (evals/backtest): "watch this supplier", not a prediction. */
  watch: boolean;
  recall_score: number | null;
}

export interface EvidenceClaim {
  text: string;
  citations: string[];
  reasons?: string[];
}

export interface EvidenceCitation {
  id: string;
  source: string;
  source_label: string;
  type: string;
  title: string;
  published_at: string;
  url: string | null;
  severity: string;
  match_type: string;
  match_kind: string;
  matched_on: string;
}

export interface EvidenceAnswer {
  question: string;
  supplier: string;
  /** answered | no_records | insufficient_evidence */
  status: string;
  note: string;
  claims: EvidenceClaim[];
  removed: EvidenceClaim[];
  citations: EvidenceCitation[];
  /** extractive (from the records' own fields) | llm | extractive_after_llm_rejected | none */
  method: string;
}

export type Role = 'admin' | 'analyst' | 'viewer' | 'auditor';
export const ROLES: Role[] = ['admin', 'analyst', 'viewer', 'auditor'];

export interface TeamMember {
  id: string;
  email: string;
  name: string;
  roles: Role[];
  is_active: boolean;
  mfa_enabled: boolean;
  created_at: string | null;
  last_login_at: string | null;
  /** Built-in development account: listed, not editable. */
  demo?: boolean;
}

export interface Invitation {
  id: string;
  email: string;
  roles: Role[];
  status: 'pending' | 'accepted' | 'revoked' | 'expired';
  created_at: string;
  expires_at: string;
}

export interface InvitationPreview {
  organization_name: string;
  email: string;
  roles: Role[];
  expires_at: string;
}

export interface PublicSourceStatus {
  label: string;
  status: 'ok' | 'error' | 'rate_limited' | 'never_run';
  error?: string | null;
  last_run_at?: string;
  last_success_at?: string | null;
}

export const api = {
  // Authentication
  /** Either tokens, or (with MFA on) mfa_required plus a short-lived mfa_token for verifyMfa. */
  async login(email: string, password: string): Promise<LoginResponse> {
    const response = await apiClient.post('/api/v1/auth/login', { email, password });
    return response.data;
  },

  async verifyMfa(mfaToken: string, totpCode: string): Promise<LoginResponse> {
    const response = await apiClient.post('/api/v1/auth/mfa/verify', { mfa_token: mfaToken, totp_code: totpCode });
    return response.data;
  },

  // Team (Settings > Team)
  async listMembers(): Promise<{ members: TeamMember[] }> {
    return (await apiClient.get('/api/v1/org/members')).data;
  },

  async updateMember(id: string, changes: { roles?: Role[]; is_active?: boolean }): Promise<TeamMember> {
    return (await apiClient.patch(`/api/v1/org/members/${encodeURIComponent(id)}`, changes)).data;
  },

  async listInvitations(): Promise<{ invitations: Invitation[] }> {
    return (await apiClient.get('/api/v1/org/invitations')).data;
  },

  async createInvitation(email: string, roles: Role[]): Promise<{ invitation: Invitation; invite_url: string; note: string }> {
    return (await apiClient.post('/api/v1/org/invitations', { email, roles })).data;
  },

  async revokeInvitation(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/org/invitations/${encodeURIComponent(id)}`);
  },

  // Invitations (public). The token goes in the body, never the URL path.
  async lookupInvitation(token: string): Promise<InvitationPreview> {
    return (await apiClient.post('/api/v1/invitations/lookup', { token })).data;
  },

  async acceptInvitation(token: string, name: string, password: string): Promise<LoginResponse> {
    return (await apiClient.post('/api/v1/invitations/accept', { token, name, password })).data;
  },

  // Registration
  async signup(email: string, password: string, name: string): Promise<{ access_token: string; token_type: string; user: any }> {
    const response = await apiClient.post('/api/v1/auth/signup', { email, password, name });
    return response.data;
  },

  // Health check
  async getHealth() {
    const response = await apiClient.get('/health');
    return response.data;
  },

  // Risk management
  async getRisks(params: { limit?: number; offset?: number; severity?: string } = {}) {
    const response = await apiClient.get('/api/v1/risks', { params });
    return response.data;
  },

  async getRisk(riskId: string) {
    const response = await apiClient.get(`/api/v1/risks/${riskId}`);
    return response.data;
  },

  async createRisk(risk: Partial<Risk> & { status?: string; owner?: string }) {
    const response = await apiClient.post('/api/v1/risks', risk);
    return response.data;
  },

  async updateRisk(riskId: string, updates: Partial<Risk> & { status?: string; owner?: string }) {
    const response = await apiClient.put(`/api/v1/risks/${riskId}`, updates);
    return response.data;
  },

  async assessRisk(request: RiskAssessmentRequest): Promise<RiskAssessmentResponse> {
    const response = await apiClient.post('/api/v1/risk-assessment', request);
    return response.data;
  },

  async getRecommendations(riskId: string) {
    const response = await apiClient.get(`/api/v1/recommendations/${riskId}`);
    return response.data;
  },

  // Metrics and analytics
  async getMetrics() {
    const response = await apiClient.get('/api/v1/metrics');
    return response.data;
  },

  async getAnalytics(params: { 
    start_date?: string; 
    end_date?: string; 
    category?: string 
  } = {}) {
    const response = await apiClient.get('/api/v1/analytics', { params });
    return response.data;
  },

  // Task management
  async getTask(taskId: string) {
    const response = await apiClient.get(`/api/v1/tasks/${taskId}`);
    return response.data;
  },

  async getTasks(params: { limit?: number; status?: string } = {}) {
    const response = await apiClient.get('/api/v1/tasks', { params });
    return response.data;
  },

  // Suppliers
  async getSuppliers(params: { org_id?: string; risk_tier?: string; limit?: number } = {}) {
    const response = await apiClient.get('/api/v1/suppliers', { params });
    return response.data;
  },

  async getSupplier(supplierId: string) {
    const response = await apiClient.get(`/api/v1/suppliers/${supplierId}`);
    return response.data;
  },

  async createSupplier(supplier: Partial<Supplier>) {
    const response = await apiClient.post('/api/v1/suppliers', supplier);
    return response.data;
  },

  async updateSupplier(supplierId: string, updates: Partial<Supplier>) {
    const response = await apiClient.put(`/api/v1/suppliers/${supplierId}`, updates);
    return response.data;
  },

  async deleteSupplier(supplierId: string) {
    const response = await apiClient.delete(`/api/v1/suppliers/${supplierId}`);
    return response.data;
  },

  // Alerts
  async getAlerts(params: { status?: string; severity?: string; limit?: number } = {}) {
    const response = await apiClient.get('/api/v1/alerts', { params });
    return response.data;
  },

  async acknowledgeAlert(alertId: string) {
    const response = await apiClient.post(`/api/v1/alerts/${alertId}/acknowledge`);
    return response.data;
  },

  // Risk History
  async getRiskHistory(limit: number = 100) {
    const response = await apiClient.get('/api/v1/risks/history', { params: { limit } });
    return response.data;
  },

  // Components & Products
  async getComponents(category?: string) {
    const params: any = {};
    if (category) params.category = category;
    const response = await apiClient.get('/api/v1/components', { params });
    return response.data;
  },

  async getProducts() {
    const response = await apiClient.get('/api/v1/products');
    return response.data;
  },

  async getProductBom(productId: string) {
    const response = await apiClient.get(`/api/v1/products/${productId}/bom`);
    return response.data;
  },

  // Digital Twin Simulator
  async runSimulation(params: { disrupted_suppliers: string[]; severity: string; duration_days: number; num_simulations?: number }) {
    const response = await apiClient.post('/api/v1/simulator/run', { scenario_type: 'supplier_disruption', ...params });
    return response.data;
  },

  // Procurement
  async evaluateProcurement(suppliers: Array<Record<string, any>>, riskThreshold: number = 65) {
    const response = await apiClient.post('/api/v1/procurement/evaluate', { suppliers, risk_threshold: riskThreshold });
    return response.data;
  },

  async getProcurementActions(status?: string) {
    const params: any = {};
    if (status) params.status = status;
    const response = await apiClient.get('/api/v1/procurement/actions', { params });
    return response.data;
  },

  // Chat
  async chat(message: string, context: Record<string, any> = {}) {
    const response = await apiClient.post('/api/v1/chat', { message, context });
    return response.data;
  },

  // Intelligence Feed
  async triggerIngestion() {
    const response = await apiClient.post('/api/v1/intelligence/ingest');
    return response.data;
  },

  async getIntelligenceFeed(source?: string, limit: number = 50) {
    const params: any = { limit };
    if (source) params.source = source;
    const response = await apiClient.get('/api/v1/intelligence/feed', { params });
    return response.data;
  },

  async getIntelligenceSources(): Promise<{ sources: Record<string, PublicSourceStatus>; available: string[]; total_documents: number }> {
    const response = await apiClient.get('/api/v1/intelligence/sources');
    return response.data;
  },

  // Public signals matched to suppliers
  async getSupplierSignals(supplierId: string): Promise<SupplierSignals> {
    const response = await apiClient.get(`/api/v1/suppliers/${encodeURIComponent(supplierId)}/signals`);
    return response.data;
  },

  async askAboutSupplier(supplierId: string, question: string): Promise<EvidenceAnswer> {
    const response = await apiClient.post(`/api/v1/suppliers/${encodeURIComponent(supplierId)}/ask`, { question });
    return response.data;
  },

  async getSignalsOverview(sinceDays: number = 365): Promise<{ suppliers: SupplierSignalSummary[] }> {
    const response = await apiClient.get('/api/v1/signals/suppliers', { params: { since_days: sinceDays } });
    return response.data;
  },

  // Sub-Tier Discovery
  async discoverSubtiers(supplierName: string, supplierId: string = '', supplierContext: Record<string, any> = {}) {
    const response = await apiClient.post('/api/v1/suppliers/discover-subtiers', { supplier_name: supplierName, supplier_id: supplierId, supplier_context: supplierContext });
    return response.data;
  },

  // Risk Events
  async createEvent(event: Record<string, any>) {
    const response = await apiClient.post('/api/v1/events', event);
    return response.data;
  },

  async getEvents(limit: number = 50) {
    const response = await apiClient.get('/api/v1/events', { params: { limit } });
    return response.data;
  },

  async getEventImpacts(eventId: string) {
    const response = await apiClient.get(`/api/v1/events/${eventId}/impacts`);
    return response.data;
  },

  // Risk Scoring (7 dimensions)
  async scoreSupplierRisk(supplierName: string, supplierContext: Record<string, any> = {}) {
    const response = await apiClient.post('/api/v1/risk-score', { supplier_name: supplierName, supplier_context: supplierContext });
    return response.data;
  },

  async getRiskDimensions() {
    const response = await apiClient.get('/api/v1/risk-dimensions');
    return response.data;
  },

  // Predictions
  async getPredictions() {
    const response = await apiClient.get('/api/v1/predictions');
    return response.data;
  },

  // Supply Chain Map
  async getSupplyChainMap(orgId?: string) {
    const response = await apiClient.get('/api/v1/supply-chain/map', { params: orgId ? { org_id: orgId } : {} });
    return response.data;
  },

  // Scenario Simulation
  async simulateScenario(scenario: { type: string; affected_suppliers: string[]; severity: string; duration_days: number; description?: string }) {
    const response = await apiClient.post('/api/v1/scenarios/simulate', scenario);
    return response.data;
  },

  // Organizations
  async getOrganizations() {
    const response = await apiClient.get('/api/v1/organizations');
    return response.data;
  },

  async getOrganization(orgId: string) {
    const response = await apiClient.get(`/api/v1/organizations/${orgId}`);
    return response.data;
  },

  // Real-time updates via WebSocket
  createWebSocket(onMessage: (data: any) => void, onError?: (error: Event) => void) {
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
    const ws = new WebSocket(wsUrl);

    // The gateway requires the access token as the first message (never in the URL).
    ws.onopen = () => {
      ws.send(JSON.stringify({ token: session.accessToken || '' }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };
    
    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      if (onError) onError(error);
    };
    
    return ws;
  },
};

export default api;
