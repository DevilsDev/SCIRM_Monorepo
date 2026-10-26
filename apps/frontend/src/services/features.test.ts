import { afterEach, describe, expect, it, vi } from 'vitest';

// api.ts needs a browser (window.localStorage); only getConfig matters here.
vi.mock('./api', () => ({ api: { getConfig: vi.fn() } }));

import { api } from './api';
import { isSamplePath, loadFeatures, resetFeatures, SAMPLE_PATHS } from './features';

describe('sample pages', () => {
  afterEach(() => { vi.mocked(api.getConfig).mockReset(); resetFeatures(); });

  it('recognises sample pages and their sub-pages only', () => {
    expect(SAMPLE_PATHS).toEqual(['/components', '/predictions', '/simulator', '/procurement']);
    expect(isSamplePath('/simulator')).toBe(true);
    expect(isSamplePath('/components/abc')).toBe(true);
    expect(isSamplePath('/suppliers')).toBe(false);
    expect(isSamplePath('/predictionsX')).toBe(false);
  });

  it('follows the server when it answers', async () => {
    vi.mocked(api.getConfig).mockResolvedValue({ features: { sample_pages: true } });
    expect(await loadFeatures()).toEqual({ loaded: true, samplePages: true });
  });

  it('keeps sample pages hidden when the server cannot say', async () => {
    vi.mocked(api.getConfig).mockRejectedValue(new Error('offline'));
    expect(await loadFeatures()).toEqual({ loaded: true, samplePages: false });
  });

  it('asks the server once per session', async () => {
    const spy = vi.mocked(api.getConfig).mockResolvedValue({ features: { sample_pages: false } });
    await Promise.all([loadFeatures(), loadFeatures()]);
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
