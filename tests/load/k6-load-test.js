/**
 * SCIRM Platform Load Test — k6
 * Simulates 100K concurrent users across all API endpoints.
 *
 * Run: k6 run tests/load/k6-load-test.js
 * With output: k6 run --out json=results.json tests/load/k6-load-test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const assessmentDuration = new Trend('assessment_duration');

// Test configuration — ramp up to 100K virtual users
export const options = {
  stages: [
    { duration: '1m', target: 100 },      // Warm up
    { duration: '3m', target: 1000 },      // Ramp to 1K
    { duration: '5m', target: 10000 },     // Ramp to 10K
    { duration: '5m', target: 50000 },     // Ramp to 50K
    { duration: '5m', target: 100000 },    // Peak: 100K concurrent
    { duration: '3m', target: 100000 },    // Sustain 100K
    { duration: '2m', target: 0 },         // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<2000'],  // 95th < 500ms, 99th < 2s
    errors: ['rate<0.01'],                             // Error rate < 1%
    http_req_failed: ['rate<0.01'],                    // HTTP failures < 1%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
let authToken = '';

// Login once per VU
export function setup() {
  const loginRes = http.post(
    `${BASE_URL}/api/v1/auth/login`,
    JSON.stringify({ email: 'sarah.chen@pharmacorp.com', password: 'scirm-dev-2026' }),
    { headers: { 'Content-Type': 'application/json' } }
  );
  return { token: JSON.parse(loginRes.body).access_token };
}

export default function (data) {
  const headers = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${data.token}`,
  };

  group('Health Check', () => {
    const res = http.get(`${BASE_URL}/health`);
    check(res, { 'health 200': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group('List Risks', () => {
    const res = http.get(`${BASE_URL}/api/v1/risks?limit=20`, { headers });
    check(res, { 'risks 200': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group('List Suppliers', () => {
    const res = http.get(`${BASE_URL}/api/v1/suppliers`, { headers });
    check(res, { 'suppliers 200': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group('Get Predictions', () => {
    const res = http.get(`${BASE_URL}/api/v1/predictions`, { headers });
    check(res, { 'predictions 200': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group('Get Alerts', () => {
    const res = http.get(`${BASE_URL}/api/v1/alerts`, { headers });
    check(res, { 'alerts 200': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  group('Supply Chain Map', () => {
    const res = http.get(`${BASE_URL}/api/v1/supply-chain/map`, { headers });
    check(res, { 'map 200': (r) => r.status === 200 });
    errorRate.add(res.status !== 200);
  });

  // Run assessment less frequently (1 in 20 iterations) — it's heavier
  if (__ITER % 20 === 0) {
    group('Risk Assessment', () => {
      const payload = JSON.stringify({
        entities: [
          { id: `vu-${__VU}-${__ITER}`, name: 'Test Supplier', type: 'supplier', location: 'US' },
        ],
        context: { organization_id: 'a0000000-0000-0000-0000-000000000001' },
      });

      const start = Date.now();
      const res = http.post(`${BASE_URL}/api/v1/risk-assessment`, payload, { headers, timeout: '30s' });
      assessmentDuration.add(Date.now() - start);

      check(res, { 'assessment 200': (r) => r.status === 200 });
      errorRate.add(res.status !== 200);
    });
  }

  // Scenario simulation (1 in 50 iterations)
  if (__ITER % 50 === 0) {
    group('Scenario Simulation', () => {
      const payload = JSON.stringify({
        type: 'supplier_disruption',
        affected_suppliers: ['c0000000-0000-0000-0000-000000000003'],
        severity: 'high',
        duration_days: 30,
      });
      const res = http.post(`${BASE_URL}/api/v1/scenarios/simulate`, payload, { headers });
      check(res, { 'simulation 200': (r) => r.status === 200 });
      errorRate.add(res.status !== 200);
    });
  }

  sleep(Math.random() * 2 + 0.5); // 0.5-2.5s think time
}
