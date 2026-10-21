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
  /** Null until an assessment has scored the supplier. */
  risk_score: number | null;
  risk_tier: string | null;
  contact_name?: string;
  contact_email?: string;
  is_active: boolean;
  /** Set on demo suppliers (fictional, or named after real companies). */
  demo_note?: string;
  /** Places the supplier operates, for site-level disaster exposure. */
  sites?: SupplierSite[];
  /** 12-month purchase-order spend per currency, from an SAP export (never converted). */
  spend_12m?: Record<string, string>;
  spend_period?: { from: string; to: string } | null;
  spend_main_currency?: string | null;
  /** Share of the file's spend in the main currency (0-1). */
  spend_share?: number | null;
  /** 1 = largest spend in the main currency. */
  spend_rank?: number | null;
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
  match_type: 'name_exact' | 'name_contains' | 'name_similar' | 'parent_company' | 'country_exposure' | 'site_proximity';
  confidence: number;
  kind: 'incident' | 'exposure';
  matched_on: string;
  signal: PublicSignal;
  /** site_proximity: the nearest site within the alert's radius of its reported point. */
  site?: { site: string; city: string | null; country: string; distance_km: number; radius_km: number; precision: string };
  /** When one event covers several records (an FDA recall per product strength or pack). */
  records?: Array<{ id: string; external_id: string; product: string; severity: string; url: string | null }>;
}

export interface SupplierSignals {
  supplier_id: string;
  supplier_name: string;
  incidents: SignalMatch[];
  exposures: SignalMatch[];
  /** Events naming the supplier; incident_records counts the records they cover. */
  incident_total: number;
  incident_records?: number;
  exposure_total: number;
  /** True when exposure was judged per located site rather than per country. */
  site_level?: boolean;
  /** Alerts in the supplier's countries that were not near any of its sites. */
  exposures_elsewhere?: number;
}

export interface SupplierSite {
  id: string;
  label: string;
  city: string | null;
  country: string;
  lat: number;
  lon: number;
  source: 'manual' | 'sap_lfa1' | string;
  /** exact (coordinates given), city, or city_ambiguous (several places share the name). */
  precision: 'exact' | 'city' | 'city_ambiguous' | string;
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

export interface ScanResult {
  report: {
    generated_at: string;
    summary: { scanned: number; with_records: number; watch: number; to_check: number; by_type: Record<string, number> };
    suppliers: Array<{ name: string; watch: boolean; records: unknown[] }>;
  };
  warnings: string[];
  /** Self-contained HTML report (no scripts). */
  html: string;
}

export interface SapImportAction {
  action: 'create' | 'update' | 'link' | 'deactivate' | 'skip' | 'needs_decision';
  number: string;
  name: string;
  supplier_id?: string;
  changed?: string[];
  reason?: string;
}

export interface SapImportResult {
  applied: boolean;
  written: number;
  rows: number;
  warnings: string[];
  summary: Partial<Record<SapImportAction['action'] | 'unchanged', number>>;
  duplicates: Array<{ number: string; name: string; country_code: string | null; existing_id: string;
    existing_name: string; existing_code: string }>;
  missing: Array<{ number: string; name: string; supplier_id: string }>;
  missing_deactivated: boolean;
  /** Set when missing suppliers were not deactivated because the file looked incomplete. */
  guard: string | null;
  actions: SapImportAction[];
}

export interface SapSpendResult {
  applied: boolean;
  written: number;
  warnings: string[];
  period: { from: string; to: string } | null;
  main_currency: string | null;
  currencies: Record<string, string>;
  lines: { read: number; deleted: number; before_period: number; counted: number };
  top: Array<{ rank: number; number: string; name: string; spend: Record<string, string>; share: number | null }>;
  unknown_suppliers: Array<{ number: string; spend: Record<string, string> }>;
  unknown_count: number;
  with_spend: number;
  suppliers: number;
}

/** The organization's SAP S/4HANA connection, as the API shows it (never the password). */
export interface SapConnection {
  id: string;
  system: 'sap';
  base_url: string;
  sap_client: string | null;
  username: string;
  has_password: boolean;
  last_test: (SapConnectionTest & { at: string }) | null;
  last_import: { kind: 'suppliers' | 'spend'; ok: boolean; error: string | null; applied?: boolean;
    written?: number; at: string } | null;
  updated_at: string;
}

export interface SapConnectionTest {
  ok: boolean;
  checks: Array<{ service: string; ok: boolean; detail: string }>;
}

export interface SapConnectionSettings {
  base_url: string;
  sap_client?: string;
  username: string;
  /** Leave out to keep the stored password. */
  password?: string;
}

export interface SapImportRequest {
  content: string;
  column_map?: Record<string, string>;
  /** Possible duplicates: { SAP number: "create" | "link:<supplier id>" } */
  decisions?: Record<string, string>;
  deactivate_missing?: boolean;
  apply?: boolean;
}

export type FeedbackTarget = 'signal_match' | 'answer' | 'citation';
export type FeedbackVerdict = 'useful' | 'not_useful' | 'wrong_supplier' | 'incorrect';

export interface FeedbackInput {
  target_type: FeedbackTarget;
  /** signal_match: the signal id. answer: the id the page gave the answer. citation: "<answer id>:<S#>". */
  target_id: string;
  verdict: FeedbackVerdict;
  supplier_id?: string;
  reason?: string;
  /** Only known fields are kept by the server (counts, method, source); never the question text. */
  context?: Record<string, string | number>;
}

export interface FeedbackSummary {
  since_days: number;
  raters: number;
  records: { rated: number; useful: number; not_useful: number; wrong_supplier: number;
    useful_rate: number | null; wrong_supplier_rate: number | null };
  answers: { rated: number; helpful: number; not_helpful: number; helpful_rate: number | null };
  citations: { reported_incorrect: number; in_rated_answers: number; reported_incorrect_in_rated_answers: number;
    estimated_correct_rate: number | null };
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

  // SAP supplier import (LFA1 extract). Preview unless apply is true.
  async importSapSuppliers(request: SapImportRequest): Promise<SapImportResult> {
    return (await apiClient.post('/api/v1/suppliers/import/sap', request, { timeout: 300000 })).data;
  },

  // SAP purchase-order spend (EKKO/EKPO or ME2N export). Preview unless apply is true.
  async importSapSpend(request: { content: string; column_map?: Record<string, string>; decimal?: '.' | ',';
    apply?: boolean }): Promise<SapSpendResult> {
    return (await apiClient.post('/api/v1/suppliers/import/sap-spend', request, { timeout: 300000 })).data;
  },

  // Direct SAP S/4HANA connection (OData). Settings are admin-only; the password is never returned.
  async getSapConnection(): Promise<SapConnection | null> {
    return (await apiClient.get('/api/v1/integrations/sap')).data.connection;
  },

  async saveSapConnection(settings: SapConnectionSettings): Promise<SapConnection> {
    return (await apiClient.put('/api/v1/integrations/sap', settings)).data.connection;
  },

  async deleteSapConnection(): Promise<void> {
    await apiClient.delete('/api/v1/integrations/sap');
  },

  async testSapConnection(): Promise<SapConnectionTest> {
    return (await apiClient.post('/api/v1/integrations/sap/test', {}, { timeout: 130000 })).data;
  },

  // Supplier master and spend read from the SAP connection: preview unless apply is true.
  async importSapSuppliersFromConnection(request: Omit<SapImportRequest, 'content' | 'column_map'>): Promise<SapImportResult> {
    return (await apiClient.post('/api/v1/suppliers/import/sap/connection', request, { timeout: 300000 })).data;
  },

  async importSapSpendFromConnection(request: { apply?: boolean }): Promise<SapSpendResult> {
    return (await apiClient.post('/api/v1/suppliers/import/sap-spend/connection', request, { timeout: 300000 })).data;
  },

  // Supplier scan: the list is processed in memory and not stored.
  async scanSuppliers(csv: string, preparedFor = ''): Promise<ScanResult> {
    return (await apiClient.post('/api/v1/scan', { csv, prepared_for: preparedFor }, { timeout: 120000 })).data;
  },

  // What this deployment shows (sample-data pages are off outside development).
  async getConfig(): Promise<{ features: { sample_pages: boolean } }> {
    return (await apiClient.get('/api/v1/config')).data;
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

  // Feedback: one rating per person per item; rating again replaces it.
  async sendFeedback(input: FeedbackInput): Promise<void> {
    await apiClient.post('/api/v1/feedback', input);
  },

  async getMySupplierFeedback(supplierId: string): Promise<{ ratings: Record<string, FeedbackVerdict> }> {
    return (await apiClient.get(`/api/v1/suppliers/${encodeURIComponent(supplierId)}/feedback`)).data;
  },

  async getFeedbackSummary(sinceDays = 90): Promise<FeedbackSummary> {
    return (await apiClient.get('/api/v1/feedback/summary', { params: { since_days: sinceDays } })).data;
  },

  // Supplier sites (site-level disaster exposure)
  async addSupplierSite(supplierId: string, site: { label: string; country: string; city?: string; lat?: number; lon?: number }): Promise<Supplier> {
    return (await apiClient.post(`/api/v1/suppliers/${encodeURIComponent(supplierId)}/sites`, site)).data;
  },

  async removeSupplierSite(supplierId: string, siteId: string): Promise<Supplier> {
    return (await apiClient.delete(`/api/v1/suppliers/${encodeURIComponent(supplierId)}/sites/${encodeURIComponent(siteId)}`)).data;
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
