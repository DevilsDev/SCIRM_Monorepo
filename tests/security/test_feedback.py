"""
Feedback on matched records and answers: the Phase 1 gate metrics. Runs on both
backends (STORE_BACKEND=memory and postgres), like the rest of the security suite.
"""

import uuid

import pytest

# Defined here, not imported from conftest (see test_onboarding.py).
from libs.common.store import summarize_feedback


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def rate(client, tokens, **body):
    return client.post("/api/v1/feedback", json=body, headers=bearer(tokens["access_token"]))


def supplier():
    return f"SUP-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def marcus(client, sarah):
    """A fresh analyst in org 1, invited by Sarah. (The demo analyst gets MFA enabled by
    another test, so it cannot sign in with a password alone.)"""
    invited = client.post("/api/v1/org/invitations", json={"email": f"rater-{uuid.uuid4().hex[:8]}@example.com",
                                                           "roles": ["analyst"]}, headers=bearer(sarah["access_token"]))
    assert invited.status_code == 200, invited.text
    token = invited.json()["invite_url"].split("#", 1)[1]
    response = client.post("/api/v1/invitations/accept", json={"token": token, "name": "Rater", "password": "a-good-password"})
    assert response.status_code == 200, response.text
    return response.json()


class TestRecording:
    def test_rating_a_match_and_changing_it(self, client, sarah):
        sid = supplier()
        first = rate(client, sarah, target_type="signal_match", target_id="sig-1", supplier_id=sid, verdict="useful")
        assert first.status_code == 200, first.text
        assert first.json()["target_id"] == f"{sid}:sig-1"
        assert rate(client, sarah, target_type="signal_match", target_id="sig-1", supplier_id=sid,
                    verdict="wrong_supplier").status_code == 200
        mine = client.get(f"/api/v1/suppliers/{sid}/feedback", headers=bearer(sarah["access_token"])).json()
        assert mine == {"ratings": {"sig-1": "wrong_supplier"}}  # one rating per person, the latest

    def test_ratings_are_per_person(self, client, sarah, marcus):
        sid = supplier()
        rate(client, sarah, target_type="signal_match", target_id="sig-2", supplier_id=sid, verdict="useful")
        rate(client, marcus, target_type="signal_match", target_id="sig-2", supplier_id=sid, verdict="not_useful")
        assert client.get(f"/api/v1/suppliers/{sid}/feedback",
                          headers=bearer(sarah["access_token"])).json()["ratings"] == {"sig-2": "useful"}
        assert client.get(f"/api/v1/suppliers/{sid}/feedback",
                          headers=bearer(marcus["access_token"])).json()["ratings"] == {"sig-2": "not_useful"}

    def test_the_same_record_rated_for_two_suppliers_is_two_ratings(self, client, sarah):
        a, b = supplier(), supplier()
        rate(client, sarah, target_type="signal_match", target_id="sig-3", supplier_id=a, verdict="useful")
        rate(client, sarah, target_type="signal_match", target_id="sig-3", supplier_id=b, verdict="wrong_supplier")
        assert client.get(f"/api/v1/suppliers/{a}/feedback",
                          headers=bearer(sarah["access_token"])).json()["ratings"] == {"sig-3": "useful"}

    def test_requires_sign_in(self, client):
        assert client.post("/api/v1/feedback", json={"target_type": "answer", "target_id": "a",
                                                     "verdict": "useful"}).status_code in (401, 403)


class TestValidation:
    @pytest.mark.parametrize("body", [
        {"target_type": "nonsense", "target_id": "x", "verdict": "useful"},
        {"target_type": "answer", "target_id": "x", "verdict": "wrong_supplier"},
        {"target_type": "citation", "target_id": "x", "verdict": "useful"},
        {"target_type": "signal_match", "target_id": "x", "verdict": "useful"},  # no supplier_id
        {"target_type": "answer", "target_id": "has spaces", "verdict": "useful"},
        {"target_type": "answer", "target_id": "x" * 201, "verdict": "useful"},
        {"target_type": "answer", "target_id": "x", "verdict": "useful", "reason": "r" * 501},
    ])
    def test_bad_input_is_refused(self, client, sarah, body):
        assert rate(client, sarah, **body).status_code in (400, 422)

    def test_only_known_context_fields_are_kept(self, client, sarah, apps):
        answer_id = uuid.uuid4().hex
        response = rate(client, sarah, target_type="answer", target_id=answer_id, verdict="useful",
                        context={"citations": 3, "method": "llm", "question": "secret question text",
                                 "status": "answered"})
        assert response.status_code == 200
        store = apps["gateway"].audit_store
        if hasattr(store, "feedback"):  # memory backend: inspect the stored row directly
            row = next(r for r in store.feedback.values() if r["target_id"] == answer_id)
            assert row["context"] == {"citations": 3, "method": "llm", "status": "answered"}


class TestSummary:
    def test_metrics(self, client, lisa):
        """Org 2: no other test writes feedback there, so the numbers are exact."""
        sid = supplier()
        for i, verdict in enumerate(["useful", "useful", "useful", "not_useful", "wrong_supplier"]):
            rate(client, lisa, target_type="signal_match", target_id=f"m{i}", supplier_id=sid, verdict=verdict)
        rate(client, lisa, target_type="answer", target_id="ans-1", verdict="useful", context={"citations": 4})
        rate(client, lisa, target_type="answer", target_id="ans-2", verdict="not_useful", context={"citations": 2})
        rate(client, lisa, target_type="citation", target_id="ans-2:S1", verdict="incorrect")
        rate(client, lisa, target_type="citation", target_id="unrated-answer:S1", verdict="incorrect")
        summary = client.get("/api/v1/feedback/summary", headers=bearer(lisa["access_token"])).json()
        assert summary["raters"] == 1
        assert summary["records"] == {"rated": 5, "useful": 3, "not_useful": 1, "wrong_supplier": 1,
                                      "useful_rate": 0.6, "wrong_supplier_rate": 0.2}
        assert summary["answers"] == {"rated": 2, "helpful": 1, "not_helpful": 1, "helpful_rate": 0.5}
        assert summary["citations"] == {"reported_incorrect": 2, "in_rated_answers": 6,
                                        "reported_incorrect_in_rated_answers": 1, "estimated_correct_rate": 0.833}

    def test_summaries_are_tenant_scoped(self, client, sarah, lisa):
        rate(client, sarah, target_type="answer", target_id=uuid.uuid4().hex, verdict="useful")
        org2 = client.get("/api/v1/feedback/summary", headers=bearer(lisa["access_token"])).json()
        assert org2["raters"] == 1  # Lisa only; Sarah's ratings in org 1 are not counted

    def test_ratings_are_not_visible_across_tenants(self, client, sarah, lisa):
        sid = supplier()
        rate(client, sarah, target_type="signal_match", target_id="sig-x", supplier_id=sid, verdict="useful")
        assert client.get(f"/api/v1/suppliers/{sid}/feedback",
                          headers=bearer(lisa["access_token"])).json()["ratings"] == {}

    def test_admins_and_auditors_only(self, client, marcus, auditor):
        assert client.get("/api/v1/feedback/summary", headers=bearer(marcus["access_token"])).status_code == 403
        assert client.get("/api/v1/feedback/summary", headers=bearer(auditor["access_token"])).status_code == 200

    def test_empty_summary_has_no_rates(self):
        summary = summarize_feedback([])
        assert summary["records"]["useful_rate"] is None and summary["citations"]["estimated_correct_rate"] is None
