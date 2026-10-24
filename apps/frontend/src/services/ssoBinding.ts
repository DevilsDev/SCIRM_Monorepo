// Ties a single sign-on to the tab that started it. The login page keeps a random value in
// sessionStorage and sends only its SHA-256 to the gateway; the one-time code at the end is
// exchanged together with the value, so a sign-in started or captured elsewhere cannot be
// completed in someone else's browser (login CSRF).

const KEY = 'scirm_sso_binding';

function toHex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes)).map((b) => b.toString(16).padStart(2, '0')).join('');
}

/** A fresh value for this tab; returns the hash to send to /sso/start. */
export async function newSsoBinding(storage: Storage = sessionStorage): Promise<string> {
  const raw = new Uint8Array(32);
  crypto.getRandomValues(raw);
  const value = toHex(raw.buffer);
  storage.setItem(KEY, value);
  return toHex(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)));
}

/** The value for the exchange, removed so it is used once. */
export function takeSsoBinding(storage: Storage = sessionStorage): string {
  const value = storage.getItem(KEY) || '';
  storage.removeItem(KEY);
  return value;
}
