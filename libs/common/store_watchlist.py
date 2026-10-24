"""Regulatory watchlists in both stores (mixed into MemoryStore and PostgresStore), and the
regulators' records a watchlist is checked against. public_signals is shared by every
organization; only the watchlist itself is tenant data."""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from libs.intel.sources import REGULATORY_SOURCES
from libs.intel.watchlist import like_patterns

WATCH_PUBLIC = ("id", "kind", "term", "note", "created_by", "created_at")


class DuplicateTerm(Exception):
    """The term is already on the organization's watchlist."""


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
    return str(value) if isinstance(value, uuid.UUID) else value


def _naive(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


class MemoryWatchlist:
    def _watch_rows(self) -> Dict[str, Dict[str, Any]]:
        if not hasattr(self, "watchlist_rows"):
            self.watchlist_rows: Dict[str, Dict[str, Any]] = {}
        return self.watchlist_rows

    async def list_watchlist(self, org: str) -> List[Dict[str, Any]]:
        rows = sorted((r for r in self._watch_rows().values() if r["organization_id"] == org),
                      key=lambda r: r["term"].lower())
        return [{k: _iso(r.get(k)) for k in WATCH_PUBLIC} for r in rows]

    async def add_watchlist_item(self, org: str, kind: str, term: str, note: str, created_by: Optional[str]) -> Dict[str, Any]:
        if any(r["organization_id"] == org and r["term"].lower() == term.lower() for r in self._watch_rows().values()):
            raise DuplicateTerm(term)
        row = {"id": str(uuid.uuid4()), "organization_id": org, "kind": kind, "term": term, "note": note,
               "created_by": created_by, "created_at": datetime.now(timezone.utc)}
        self._watch_rows()[row["id"]] = row
        return {k: _iso(row.get(k)) for k in WATCH_PUBLIC}

    async def delete_watchlist_item(self, org: str, item_id: str) -> Optional[Dict[str, Any]]:
        row = self._watch_rows().get(str(item_id))
        if not row or row["organization_id"] != org:
            return None
        del self._watch_rows()[row["id"]]
        return {k: _iso(row.get(k)) for k in WATCH_PUBLIC}

    async def regulatory_candidates(self, terms: List[str], since: Optional[str] = None,
                                    first_seen_after: Optional[str] = None, first_seen_until: Optional[str] = None,
                                    limit: int = 2000) -> List[Dict[str, Any]]:
        """Listed regulatory records that may name a term (a broad prefilter: the caller
        checks with libs.intel.watchlist.matching_terms). Newest activity first."""
        words = [p.strip("%") for p in like_patterns(terms)]
        if not words:
            return []
        lo, hi, start = _naive(first_seen_after), _naive(first_seen_until), since
        found = []
        for s in self.signals.values():
            if s.get("delisted_at") or s.get("source") not in REGULATORY_SOURCES:
                continue
            activity = str(s.get("updated_at") or s.get("published_at"))
            if start and activity < start:
                continue
            seen = _naive(s.get("first_seen_at"))
            if (lo and not (seen and seen > lo)) or (hi and not (seen and seen <= hi)):
                continue
            blob = f"{s.get('title')} {s.get('summary')} {s.get('raw')}".lower()
            if any(w in blob for w in words):
                found.append(s)
        found.sort(key=lambda s: str(s.get("updated_at") or s.get("published_at")), reverse=True)
        return found[:limit]


class PostgresWatchlist:
    async def list_watchlist(self, org: str) -> List[Dict[str, Any]]:
        rows = await self._all(org, "SELECT * FROM watchlist_items ORDER BY lower(term)")
        return [{k: _iso(r.get(k)) for k in WATCH_PUBLIC} for r in rows]

    async def add_watchlist_item(self, org: str, kind: str, term: str, note: str, created_by: Optional[str]) -> Dict[str, Any]:
        rows = await self._all(org, (
            "INSERT INTO watchlist_items (organization_id, kind, term, note, created_by) "
            "VALUES (CAST(:org AS uuid), :k, :t, :n, :by) ON CONFLICT DO NOTHING RETURNING *"),
            {"org": org, "k": kind, "t": term, "n": note, "by": created_by})
        if not rows:
            raise DuplicateTerm(term)
        return {k: _iso(rows[0].get(k)) for k in WATCH_PUBLIC}

    async def delete_watchlist_item(self, org: str, item_id: str) -> Optional[Dict[str, Any]]:
        try:
            uuid.UUID(str(item_id))
        except ValueError:
            return None
        rows = await self._all(org, "DELETE FROM watchlist_items WHERE id = CAST(:i AS uuid) RETURNING *", {"i": item_id})
        return {k: _iso(rows[0].get(k)) for k in WATCH_PUBLIC} if rows else None

    async def regulatory_candidates(self, terms: List[str], since: Optional[str] = None,
                                    first_seen_after: Optional[str] = None, first_seen_until: Optional[str] = None,
                                    limit: int = 2000) -> List[Dict[str, Any]]:
        patterns = like_patterns(terms)
        if not patterns:
            return []
        rows = await self._all(None, (
            "SELECT * FROM public_signals WHERE delisted_at IS NULL AND source = ANY(CAST(:sources AS text[])) "
            "AND (CAST(:since AS date) IS NULL OR COALESCE(updated_at, published_at) >= CAST(:since AS date)) "
            "AND (CAST(:lo AS timestamptz) IS NULL OR first_seen_at > CAST(:lo AS timestamptz)) "
            "AND (CAST(:hi AS timestamptz) IS NULL OR first_seen_at <= CAST(:hi AS timestamptz)) "
            "AND (title ILIKE ANY(CAST(:p AS text[])) OR summary ILIKE ANY(CAST(:p AS text[])) "
            "     OR CAST(raw AS text) ILIKE ANY(CAST(:p AS text[]))) "
            "ORDER BY COALESCE(updated_at, published_at) DESC, external_id LIMIT :limit"),
            {"sources": list(REGULATORY_SOURCES), "since": date.fromisoformat(since[:10]) if since else None, "p": patterns, "limit": limit,
             "lo": datetime.fromisoformat(first_seen_after) if first_seen_after else None,
             "hi": datetime.fromisoformat(first_seen_until) if first_seen_until else None})
        return [self._signal_row(r) for r in rows]
