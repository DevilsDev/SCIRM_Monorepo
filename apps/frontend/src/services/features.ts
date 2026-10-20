import { useEffect, useState } from 'react';
import { api } from './api';

// Pages that run on built-in sample data or unvalidated formulas. The gateway refuses
// their endpoints unless SAMPLE_FEATURES is on (development and test by default).
export const SAMPLE_PATHS = ['/components', '/predictions', '/simulator', '/procurement'];

export function isSamplePath(path: string): boolean {
  return SAMPLE_PATHS.some((p) => path === p || path.startsWith(`${p}/`));
}

export interface Features {
  loaded: boolean;
  samplePages: boolean;
}

let cached: Promise<Features> | null = null;

/** Clears the cached answer (after sign-out, or in tests). */
export function resetFeatures(): void {
  cached = null;
}

export function loadFeatures(): Promise<Features> {
  if (!cached) {
    cached = api.getConfig()
      .then((c) => ({ loaded: true, samplePages: !!c.features?.sample_pages }))
      // If the server cannot say, keep sample pages hidden.
      .catch(() => ({ loaded: true, samplePages: false }));
  }
  return cached;
}

/** Deployment features, asked once per session. Sample pages stay hidden until known. */
export function useFeatures(): Features {
  const [features, setFeatures] = useState<Features>({ loaded: false, samplePages: false });
  useEffect(() => {
    let live = true;
    loadFeatures().then((f) => { if (live) setFeatures(f); });
    return () => { live = false; };
  }, []);
  return features;
}
