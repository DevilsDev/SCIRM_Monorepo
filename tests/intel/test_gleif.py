"""The GLEIF client and shared-owner grouping (libs/intel/gleif.py), on recorded responses."""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import gleif_support  # noqa: E402
from gleif_support import BRAINE, GROUP, VERVIERS  # noqa: E402
from libs.intel import gleif  # noqa: E402


def client(state=None):
    return gleif.Client(base="https://api.gleif.org/api/v1", transport=gleif_support.transport(state))


def run(coro):
    return asyncio.run(coro)


class TestLookup:
    def test_a_reported_parent(self):
        o = run(client().ownership(VERVIERS))
        assert o["entity"]["legal_name"] == "LONZA VERVIERS" and o["entity"]["legal_address"]["country"] == "BE"
        assert o["direct_parent"]["kind"] == "parent" and o["direct_parent"]["lei"] == GROUP
        assert o["ultimate_parent"]["legal_name"] == "LONZA GROUP AG"
        assert o["entity"]["url"].endswith(VERVIERS) and o["golden_copy"]

    def test_an_exception_is_explained_in_gleifs_terms(self):
        o = run(client().ownership(GROUP))
        assert o["direct_parent"] == {"kind": "exception", "reason": "NON_CONSOLIDATING",
                                      "explanation": gleif.EXCEPTION_REASONS["NON_CONSOLIDATING"]}

    def test_nothing_reported_is_unknown_not_independent(self):
        o = run(client().ownership(BRAINE))
        assert o["direct_parent"]["kind"] == o["ultimate_parent"]["kind"] == "not_reported"
        assert "unknown" in o["direct_parent"]["explanation"]

    def test_unknown_or_malformed_lei(self):
        assert run(client().ownership("529900T8BM49AURSDO55")) is None
        assert run(client().ownership("not-an-lei")) is None

    def test_search_by_name_and_country_or_by_lei(self):
        found = run(client().search("Lonza", "be"))
        assert {c["legal_name"] for c in found} >= {"LONZA VERVIERS", "LONZA BRAINE SA"}
        assert len(found) <= gleif.MAX_CANDIDATES
        assert [c["lei"] for c in run(client().search(VERVIERS.lower()))] == [VERVIERS]
        assert run(client().search("x")) == []

    def test_an_outage_is_reported_not_hidden(self):
        with pytest.raises(gleif.GleifUnavailable):
            run(client({"down": True}).ownership(VERVIERS))

    @pytest.mark.parametrize("text,ok", [(VERVIERS, True), ("213800IK89OTMDYZTD0", False), ("213800IK89OTMDYZTDXX", False)])
    def test_lei_format(self, text, ok):
        assert gleif.is_lei(text) is ok


class TestSharedOwners:
    def link(self, supplier, lei, parent=None):
        top = {"kind": "parent", "lei": parent[0], "legal_name": parent[1], "legal_address": {"country": "CH"}} \
            if parent else {"kind": "exception", "reason": "NON_CONSOLIDATING"}
        return {"supplier_id": supplier, "supplier": supplier.title(), "lei": lei,
                "snapshot": {"entity": {"lei": lei, "legal_name": supplier.upper()}, "ultimate_parent": top}}

    def test_subsidiaries_and_the_owner_itself_group_together(self):
        groups = gleif.shared_owners([
            self.link("verviers", VERVIERS, (GROUP, "LONZA GROUP AG")),
            self.link("group", GROUP),
            self.link("other", "5299000000000000AB12"),
        ])
        assert len(groups) == 1 and groups[0]["owner_lei"] == GROUP
        assert sorted((s["supplier"], s["relation"]) for s in groups[0]["suppliers"]) == [
            ("Group", "is the owner"), ("Verviers", "owned")]

    def test_one_supplier_alone_is_not_a_group(self):
        assert gleif.shared_owners([self.link("verviers", VERVIERS, (GROUP, "LONZA GROUP AG"))]) == []
