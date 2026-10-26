"""Electronic signatures in both stores (mixed into MemoryStore and PostgresStore): added and
read only, never changed or removed (see migration 031)."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SIGNATURE_PUBLIC = ("id", "signer_id", "signer_name", "signer_email", "meaning", "reason", "record_type", "record_id",
                    "record_summary", "record_hash", "method", "signed_at")


def _row(r: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k in SIGNATURE_PUBLIC:
        v = r.get(k)
        if isinstance(v, datetime):
            v = (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone.utc).isoformat()
        elif isinstance(v, uuid.UUID):
            v = str(v)
        out[k] = v
    return out


class MemorySignatures:
    def _signatures(self) -> List[Dict[str, Any]]:
        if not hasattr(self, "signature_rows"):
            self.signature_rows: List[Dict[str, Any]] = []
        return self.signature_rows

    async def add_signature(self, org: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        row = {"id": str(uuid.uuid4()), "organization_id": org, "reason": None,
               "signed_at": datetime.now(timezone.utc), **fields}
        self._signatures().append(row)
        return _row(row)

    async def list_signatures(self, org: str, record_type: Optional[str] = None, record_id: Optional[str] = None,
                              limit: int = 500) -> List[Dict[str, Any]]:
        rows = [r for r in self._signatures() if r["organization_id"] == org
                and (record_type is None or r["record_type"] == record_type)
                and (record_id is None or r["record_id"] == record_id)]
        if record_id is None:
            rows = list(reversed(rows))
        return [_row(r) for r in rows[:limit]]


class PostgresSignatures:
    async def add_signature(self, org: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        rows = await self._all(org, (
            "INSERT INTO e_signatures (organization_id, signer_id, signer_name, signer_email, meaning, reason, "
            "record_type, record_id, record_summary, record_hash, method) VALUES (CAST(:org AS uuid), "
            "CAST(:signer AS uuid), :name, :email, :meaning, :reason, :rtype, :rid, :summary, :hash, :method) RETURNING *"),
            {"org": org, "signer": fields["signer_id"], "name": fields["signer_name"], "email": fields["signer_email"],
             "meaning": fields["meaning"], "reason": fields.get("reason"), "rtype": fields["record_type"],
             "rid": fields["record_id"], "summary": fields["record_summary"][:500], "hash": fields["record_hash"],
             "method": fields["method"]})
        return _row(rows[0])

    async def list_signatures(self, org: str, record_type: Optional[str] = None, record_id: Optional[str] = None,
                              limit: int = 500) -> List[Dict[str, Any]]:
        order = "seq" if record_id is not None else "seq DESC"
        rows = await self._all(org, (
            "SELECT * FROM e_signatures WHERE (CAST(:t AS text) IS NULL OR record_type = :t) "
            f"AND (CAST(:i AS text) IS NULL OR record_id = :i) ORDER BY {order} LIMIT :limit"),
            {"t": record_type, "i": record_id, "limit": limit})
        return [_row(r) for r in rows]
