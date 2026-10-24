"""
SCIM 2.0 user provisioning with a SCIM token: what identity providers send (Entra and
Okta PATCH forms), uniqueness, deactivation ending sign-in, the last-admin guard, tenant
isolation and the token's narrow reach. Runs on both backends, like the security suite.
"""

import asyncio
import uuid

import pytest


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


SCIM = {"Content-Type": "application/scim+json"}


@pytest.fixture
def scim(client, sarah):
    created = client.post("/api/v1/org/api-keys", json={"name": "Entra provisioning", "scope": "scim"},
                          headers=bearer(sarah["access_token"]))
    assert created.status_code == 200, created.text
    assert created.json()["api_key"]["scopes"] == ["scim"]
    return {**bearer(created.json()["key"]), **SCIM}


def new_user(client, scim, **extra):
    email = f"scim-{uuid.uuid4().hex[:8]}@example.com"
    body = {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": email,
            "name": {"givenName": "Ada", "familyName": "Lovelace"}, "active": True, **extra}
    response = client.post("/scim/v2/Users", json=body, headers=scim)
    assert response.status_code == 201, response.text
    assert response.headers["content-type"].startswith("application/scim+json")
    return response.json()


class TestToken:
    def test_a_scim_token_reaches_only_scim_and_read_keys_cannot_reach_scim(self, client, sarah, scim):
        assert client.get("/scim/v2/ServiceProviderConfig", headers=scim).status_code == 200
        assert client.get("/api/v1/suppliers", headers=scim).status_code == 403
        read = client.post("/api/v1/org/api-keys", json={"name": "BI"}, headers=bearer(sarah["access_token"])).json()["key"]
        assert client.get("/scim/v2/Users", headers=bearer(read)).status_code == 403
        assert client.get("/scim/v2/Users", headers=bearer(sarah["access_token"])).status_code == 403  # a person's token

    def test_unknown_scopes_are_refused(self, client, sarah):
        assert client.post("/api/v1/org/api-keys", json={"name": "x", "scope": "admin"},
                           headers=bearer(sarah["access_token"])).status_code == 422


class TestUsers:
    def test_create_find_and_read(self, client, scim):
        user = new_user(client, scim, externalId="entra-object-1", roles=[{"value": "analyst"}])
        assert user["name"]["formatted"] == "Ada Lovelace" and user["active"] is True
        assert [r["value"] for r in user["roles"]] == ["analyst"] and user["externalId"] == "entra-object-1"
        by_name = client.get("/scim/v2/Users", params={"filter": f'userName eq "{user["userName"].upper()}"'},
                             headers=scim).json()
        assert by_name["totalResults"] == 1 and by_name["Resources"][0]["id"] == user["id"]
        by_ext = client.get("/scim/v2/Users", params={"filter": 'externalId eq "entra-object-1"'}, headers=scim).json()
        assert [u["id"] for u in by_ext["Resources"]] == [user["id"]]
        assert client.get(f"/scim/v2/Users/{user['id']}", headers=scim).json()["userName"] == user["userName"]

    def test_defaults_to_viewer_and_refuses_unknown_roles(self, client, scim):
        assert [r["value"] for r in new_user(client, scim)["roles"]] == ["viewer"]
        bad = client.post("/scim/v2/Users", json={"userName": f"r-{uuid.uuid4().hex[:6]}@example.com",
                                                  "roles": [{"value": "superuser"}]}, headers=scim)
        assert bad.status_code == 400 and bad.json()["scimType"] == "invalidValue"

    def test_emails_are_unique_in_and_across_organizations(self, client, lisa, scim):
        user = new_user(client, scim)
        for email in (user["userName"], user["userName"].upper()):
            again = client.post("/scim/v2/Users", json={"userName": email}, headers=scim)
            assert again.status_code == 409 and again.json()["scimType"] == "uniqueness"
        # An account in another organization (MedTech) cannot be created or taken over here.
        elsewhere = f"medtech-{uuid.uuid4().hex[:6]}@example.com"
        invite = client.post("/api/v1/org/invitations", json={"email": elsewhere, "roles": ["viewer"]},
                             headers=bearer(lisa["access_token"])).json()["invite_url"].split("#", 1)[1]
        client.post("/api/v1/invitations/accept", json={"token": invite, "name": "M", "password": "a-good-password"})
        taken = client.post("/scim/v2/Users", json={"userName": elsewhere}, headers=scim)
        assert taken.status_code == 409 and taken.json()["scimType"] == "uniqueness"
        moved = client.put(f"/scim/v2/Users/{user['id']}", json={"userName": elsewhere}, headers=scim)
        assert moved.status_code == 409

    def test_bad_filters_are_refused(self, client, scim):
        bad = client.get("/scim/v2/Users", params={"filter": 'displayName co "a"'}, headers=scim)
        assert bad.status_code == 400 and bad.json()["scimType"] == "invalidFilter"


class TestChanges:
    def test_entra_patch_deactivates_and_sign_in_stops(self, client, login, sarah, scim):
        email = f"scim-pw-{uuid.uuid4().hex[:6]}@example.com"
        invite = client.post("/api/v1/org/invitations", json={"email": email, "roles": ["analyst"]},
                             headers=bearer(sarah["access_token"])).json()["invite_url"].split("#", 1)[1]
        tokens = client.post("/api/v1/invitations/accept", json={"token": invite, "name": "P", "password": "a-good-password"}).json()
        uid = client.get("/scim/v2/Users", params={"filter": f'userName eq "{email}"'}, headers=scim).json()["Resources"][0]["id"]
        patch = {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                 "Operations": [{"op": "Replace", "path": "active", "value": "False"}]}
        assert client.patch(f"/scim/v2/Users/{uid}", json=patch, headers=scim).json()["active"] is False
        assert login(email, "a-good-password").status_code == 401
        assert client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401

    def test_okta_patch_without_a_path_and_name_parts(self, client, scim):
        user = new_user(client, scim)
        okta = {"Operations": [{"op": "replace", "value": {"active": False, "roles": [{"value": "auditor"}]}},
                               {"op": "replace", "path": "name.familyName", "value": "Byron"}]}
        changed = client.patch(f"/scim/v2/Users/{user['id']}", json=okta, headers=scim).json()
        assert changed["active"] is False and [r["value"] for r in changed["roles"]] == ["auditor"]
        assert changed["name"]["formatted"] == "Ada Byron"

    def test_put_replaces_name_and_email(self, client, scim):
        user = new_user(client, scim)
        email = f"renamed-{uuid.uuid4().hex[:6]}@example.com"
        replaced = client.put(f"/scim/v2/Users/{user['id']}", json={"userName": email, "displayName": "Ada K.",
                                                                     "active": True}, headers=scim).json()
        assert replaced["userName"] == email and replaced["name"]["formatted"] == "Ada K."

    def test_delete_deactivates(self, client, scim):
        user = new_user(client, scim)
        assert client.delete(f"/scim/v2/Users/{user['id']}", headers=scim).status_code == 204
        assert client.get(f"/scim/v2/Users/{user['id']}", headers=scim).json()["active"] is False

    def test_unsupported_ops_are_refused(self, client, scim):
        user = new_user(client, scim)
        bad = client.patch(f"/scim/v2/Users/{user['id']}", json={"Operations": [{"op": "remove", "path": "active"}]},
                           headers=scim)
        assert bad.status_code == 400

    def test_changes_are_audited_under_the_token(self, client, sarah, scim):
        user = new_user(client, scim)
        log = client.get("/api/v1/audit", params={"category": "access", "limit": 50},
                         headers=bearer(sarah["access_token"])).json()["entries"]
        mine = [e for e in log if e["action"] == "POST /scim/v2/Users"]
        assert mine and mine[0]["actor"].startswith("api-key:Entra provisioning")


class TestBoundaries:
    def test_another_organizations_users_are_invisible(self, client, lisa, scim):
        other = client.post("/api/v1/org/api-keys", json={"name": "other", "scope": "scim"},
                            headers=bearer(lisa["access_token"])).json()["key"]
        user = new_user(client, scim)
        h = {**bearer(other), **SCIM}
        assert client.get(f"/scim/v2/Users/{user['id']}", headers=h).status_code == 404
        assert client.patch(f"/scim/v2/Users/{user['id']}", json={"Operations": [
            {"op": "replace", "path": "active", "value": False}]}, headers=h).status_code == 404
        listed = client.get("/scim/v2/Users", params={"filter": f'userName eq "{user["userName"]}"'}, headers=h).json()
        assert listed["totalResults"] == 0

    def test_the_last_administrator_cannot_be_deprovisioned(self, client, apps):
        store = apps["gateway"].audit_store

        async def setup():
            org = await store.create_organization(f"SCIM org {uuid.uuid4().hex[:6]}")
            _, key = await store.create_api_key(org, "scim", "t", scope="scim")
            return key

        h = {**bearer(asyncio.run(setup())), **SCIM}
        admin = client.post("/scim/v2/Users", json={"userName": f"only-admin-{uuid.uuid4().hex[:6]}@example.com",
                                                    "roles": [{"value": "admin"}]}, headers=h).json()
        refused = client.delete(f"/scim/v2/Users/{admin['id']}", headers=h)
        assert refused.status_code == 409 and refused.json()["scimType"] == "mutability"
