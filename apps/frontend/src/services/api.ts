import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

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
    const wsUrl = process.env.REACT_APP_WEBSOCKET_URL || 'ws://localhost:8000/ws';
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
