import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

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

export const api = {
  // Authentication
  async login(email: string, password: string): Promise<{ access_token: string; token_type: string }> {
    const response = await apiClient.post('/api/v1/auth/login', { email, password });
    return response.data;
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

  // Alerts
  async getAlerts(params: { status?: string; severity?: string; limit?: number } = {}) {
    const response = await apiClient.get('/api/v1/alerts', { params });
    return response.data;
  },

  // Risk History
  async getRiskHistory(limit: number = 100) {
    const response = await apiClient.get('/api/v1/risks/history', { params: { limit } });
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
