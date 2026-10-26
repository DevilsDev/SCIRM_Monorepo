/** Several columns (users.last_login_at, audit_logs.created_at) are stored as UTC without a
 *  zone ("2026-10-22T00:23:21"); a string like that would otherwise be read as local time.
 *  Values with a zone are left alone. */
export function utcDate(value: string): Date {
  return new Date(/(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`);
}
