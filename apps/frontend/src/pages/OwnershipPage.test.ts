import { describe, expect, it, vi } from 'vitest';

// The page imports the API client, which needs a browser; only the helpers are tested.
vi.mock('../services/api', () => ({ api: {} }));
vi.mock('../contexts/AuthContext', () => ({ useAuth: () => ({}) }));
import { coverage } from './OwnershipPage';
import { parentText, statusWarning } from '../components/SupplierOwnership';
import type { LeiEntity } from '../services/api';

const entity: LeiEntity = {
  lei: '549300EFW4H2TCZ71055', legal_name: 'LONZA GROUP AG',
  legal_address: { city: 'Basel', country: 'CH', region: null }, headquarters: { city: null, country: null, region: null },
  legal_form: null, entity_status: 'ACTIVE', registration_status: 'ISSUED', last_update: null, next_renewal: null,
  corroboration: null, url: 'https://search.gleif.org/#/record/549300EFW4H2TCZ71055',
};

describe('ownership page', () => {
  it('names a parent with its place, and explains an exception or a gap', () => {
    expect(parentText({ kind: 'parent', ...entity })).toBe('LONZA GROUP AG (Basel, CH)');
    expect(parentText({ kind: 'exception', reason: 'NATURAL_PERSONS', explanation: 'Controlled by people.' })).toBe('Controlled by people.');
    expect(parentText({ kind: 'not_reported', explanation: 'Unknown here.' })).toBe('Unknown here.');
  });

  it('warns about lapsed registrations and inactive entities only', () => {
    expect(statusWarning(entity)).toBe('');
    expect(statusWarning({ ...entity, registration_status: 'LAPSED' })).toContain('lapsed');
    expect(statusWarning({ ...entity, entity_status: 'INACTIVE' })).toContain('inactive');
  });

  it('counts coverage over active suppliers', () => {
    const link = (active: boolean) => ({ is_active: active } as any);
    expect(coverage({ links: [link(true), link(false)], unlinked: [{} as any, {} as any] })).toEqual({ linked: 1, active: 3 });
  });
});
