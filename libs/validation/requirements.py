"""The requirements the validation pack traces to automated tests.

Each requirement names the regulation it supports, the tests that show it and the backend
each test must pass on: "postgres" for controls the database enforces (row-level security,
append-only tables, revoked privileges), "both" for behaviour of the API that must hold on
the in-memory store and on PostgreSQL. A requirement with no tests is the customer's own
procedure: it is listed so the matrix is complete, never counted as tested.

Test ids are pytest node ids; tests/validation/test_requirements.py checks every one exists.
"""

from typing import Any, Dict, List

SIG = "tests/security/test_signatures.py"
SSO = "tests/security/test_sso.py"
AUTH = "tests/security/test_auth_and_tenancy.py"
DB = "tests/db/test_database.py"
AI = "tests/security/test_ai_control.py"
MCP = "tests/security/test_mcp.py"
DD = "tests/security/test_due_diligence.py"
WAR = "tests/security/test_war_room.py"
PW = "tests/security/test_passwords.py"
MFA = "tests/security/test_mfa_enrollment.py"
KEYS = "tests/security/test_api_keys.py"
AUDIT = "tests/security/test_audit_log_screen.py"


def _r(rid: str, title: str, refs: List[str], tests: List[tuple], note: str = "") -> Dict[str, Any]:
    return {"id": rid, "title": title, "refs": refs,
            "tests": [{"node": node, "backend": backend} for node, backend in tests], "note": note}


REQUIREMENTS: List[Dict[str, Any]] = [
    # 21 CFR Part 11: electronic signatures (docs/electronic-signatures.md)
    _r("P11-SIG-01", "A signature shows the signer's printed name, the date and time, and its meaning, and is tied to "
                     "the signer's account.", ["21 CFR 11.50", "21 CFR 11.100(a)"],
       [(f"{SIG}::TestPasswordSigning::test_a_signature_shows_who_when_and_what_it_means_and_is_bound_to_the_content", "both"),
        (f"{SIG}::test_signatures_hold_the_signers_identity_not_a_session", "both")]),
    _r("P11-SIG-02", "A signature is bound to the exact content of the record it signs; a later change shows, and a "
                     "record that changes while signing is not signed.", ["21 CFR 11.70"],
       [(f"{SIG}::TestPasswordSigning::test_a_signature_shows_who_when_and_what_it_means_and_is_bound_to_the_content", "both"),
        (f"{SSO}::TestSigning::test_a_record_that_changes_while_signing_is_not_signed", "both")]),
    _r("P11-SIG-03", "Signatures cannot be changed, deleted or moved: the database refuses it, nothing cascades to "
                     "them, and their signer cannot be removed.", ["21 CFR 11.70"],
       [(f"{DB}::test_signatures_are_tenant_scoped_and_can_never_be_changed_or_removed", "postgres")]),
    _r("P11-SIG-04", "Every signing re-authenticates: the password and, when set, the two-step code; or a fresh login "
                     "at the identity provider. Repeated failures lock signing.", ["21 CFR 11.200(a)(1)", "21 CFR 11.300(d)"],
       [(f"{SIG}::TestPasswordSigning::test_every_signing_needs_the_password_and_failures_lock_out", "both"),
        (f"{SIG}::TestPasswordSigning::test_two_step_users_also_give_the_code", "both"),
        (f"{SSO}::TestSigning::test_a_fresh_login_signs", "both"),
        (f"{SSO}::TestSigning::test_a_stale_login_does_not_sign", "both")]),
    _r("P11-SIG-05", "Only the genuine owner can sign: someone else logged in at the identity provider cannot, "
                     "passwords are stored only as hashes, and only people in the organization can sign its records.",
       ["21 CFR 11.200(a)(2)", "21 CFR 11.200(a)(3)"],
       [(f"{SSO}::TestSigning::test_someone_else_at_the_identity_provider_does_not_sign", "both"),
        (f"{AUTH}::TestSignup::test_password_is_stored_hashed_and_verifies", "both"),
        (f"{SIG}::TestPasswordSigning::test_only_finished_records_and_only_people_in_the_organization", "both")]),
    _r("P11-SIG-06", "Identity is verified before an electronic signature is assigned.", ["21 CFR 11.100(b)"], [],
       "Customer procedure, not tested by SCIRM: for example at invitation or SCIM provisioning."),
    _r("P11-SIG-07", "The organization certifies to FDA that its electronic signatures are legally binding.",
       ["21 CFR 11.100(c)"], [], "Customer procedure, not tested by SCIRM."),

    # 21 CFR Part 11: system controls
    _r("P11-AUD-01", "Changes and refused attempts are written to a time-stamped audit trail with the actor and the "
                     "outcome; sign-ins and API key refusals too.", ["21 CFR 11.10(e)", "21 CFR 11.300(d)"],
       [(f"{AUTH}::TestAudit::test_writes_are_audited_with_actor_and_outcome", "both"),
        (f"{AUTH}::TestAudit::test_rejected_writes_are_audited_too", "both"),
        (f"{AUTH}::TestAudit::test_sign_ins_are_audited_with_the_account_email", "both"),
        (f"{KEYS}::TestPublicApi::test_use_is_recorded_and_refusals_are_audited_by_prefix", "both")]),
    _r("P11-AUD-02", "The audit trail cannot be changed or deleted, not even by the database owner.", ["21 CFR 11.10(e)"],
       [(f"{DB}::TestAuditLog::test_app_role_cannot_update_or_delete_audit_rows", "postgres"),
        (f"{DB}::TestAuditLog::test_even_the_owner_cannot_rewrite_history", "postgres"),
        (f"{DB}::TestAuditLog::test_audit_rows_are_tenant_scoped", "postgres")]),
    _r("P11-AUD-03", "The audit trail can be read and exported by administrators and auditors only, for their own "
                     "organization.", ["21 CFR 11.10(b)", "21 CFR 11.10(e)"],
       [(f"{AUTH}::TestAudit::test_only_admins_and_auditors_read_the_audit_log", "both"),
        (f"{AUTH}::TestAudit::test_audit_log_is_tenant_scoped", "both"),
        (f"{AUDIT}::TestExport::test_only_admins_and_auditors", "both"),
        (f"{AUDIT}::TestExport::test_csv_with_escaped_formulas_and_its_own_audit_entry", "both")]),
    _r("P11-ACC-01", "Access is limited to authorized people: read-only roles cannot change data, and administrator "
                     "settings need an administrator.", ["21 CFR 11.10(d)", "21 CFR 11.10(g)"],
       [(f"{AUTH}::TestRoles::test_read_only_role_can_read", "both"),
        (f"{AUTH}::TestRoles::test_read_only_role_cannot_create_supplier", "both"),
        (f"{AUTH}::TestRoles::test_read_only_role_cannot_create_risk", "both"),
        (f"{WAR}::TestWorking::test_read_only_roles_can_read_but_not_change", "both"),
        (f"{DD}::TestReviewCycle::test_only_administrators_set_the_interval", "both")]),
    _r("P11-ACC-02", "Passwords and sessions: reset links work once and expire, a password change signs out other "
                     "sessions, and token types cannot be swapped.", ["21 CFR 11.300(a)", "21 CFR 11.300(b)"],
       [(f"{PW}::TestReset::test_a_reset_link_works_once_and_signs_out_other_sessions", "both"),
        (f"{PW}::TestReset::test_an_expired_link_is_refused", "both"),
        (f"{PW}::TestChange::test_change_password_really_changes_it_and_signs_out_other_sessions", "both"),
        (f"{AUTH}::TestTokenTypes::test_refresh_token_rejected_as_bearer", "both"),
        (f"{AUTH}::TestMFA::test_mfa_pending_token_rejected_as_bearer", "both")]),
    _r("P11-ACC-03", "Two-step sign-in challenges only after the person confirms it, and an administrator's reset of "
                     "someone's two-step sign-in stays in their organization.", ["21 CFR 11.300(b)"],
       [(f"{MFA}::TestEnrollment::test_confirmed_enrollment_challenges_sign_in", "both"),
        (f"{MFA}::TestEnrollment::test_a_pending_seed_does_not_challenge_sign_in", "both"),
        (f"{MFA}::TestAdminReset::test_admin_resets_a_teammate", "both"),
        (f"{MFA}::TestAdminReset::test_another_organizations_admin_cannot", "both")]),
    _r("P11-REC-01", "Records that must be kept cannot be removed by the application: incident timelines, the AI run "
                     "log and due diligence records are append-only or undeletable.", ["21 CFR 11.10(c)", "LkSG § 10(1)"],
       [(f"{DB}::test_war_room_tables_are_tenant_scoped_and_the_timeline_is_append_only", "postgres"),
        (f"{DB}::test_ai_tables_are_tenant_scoped_and_the_run_log_is_append_only", "postgres"),
        (f"{DB}::test_due_diligence_records_are_tenant_scoped_kept_and_block_supplier_deletion", "postgres")]),
    _r("P11-VAL-01", "The system is validated for its intended use.", ["21 CFR 11.10(a)"], [],
       "Customer procedure, not tested by SCIRM. This pack is evidence to support it."),
    _r("P11-PRC-01", "People who develop, maintain or use the system are trained; written policies hold them "
                     "accountable; system documentation is controlled.", ["21 CFR 11.10(i)", "21 CFR 11.10(j)",
                                                                          "21 CFR 11.10(k)"], [],
       "Customer procedure, not tested by SCIRM."),

    # Tenancy
    _r("TEN-01", "Each organization sees and changes only its own data through the API.", ["Tenant isolation"],
       [(f"{AUTH}::TestTenantIsolation::test_each_org_sees_only_its_suppliers", "both"),
        (f"{AUTH}::TestTenantIsolation::test_cross_tenant_supplier_read_blocked", "both"),
        (f"{AUTH}::TestTenantIsolation::test_cross_tenant_supplier_update_blocked", "both"),
        (f"{AUTH}::TestTenantIsolation::test_org_id_query_parameter_cannot_select_another_tenant", "both"),
        (f"{WAR}::TestWorking::test_incidents_stay_in_their_organization", "both"),
        (f"{DD}::TestRiskRegister::test_another_organization_sees_and_touches_nothing", "both")]),
    _r("TEN-02", "The database enforces tenant isolation with row-level security for the application role.",
       ["Tenant isolation"],
       [(f"{DB}::test_app_role_is_restricted", "postgres"),
        (f"{DB}::TestRowLevelSecurity::test_other_org_sees_nothing", "postgres"),
        (f"{DB}::TestRowLevelSecurity::test_no_org_set_sees_nothing", "postgres"),
        (f"{DB}::TestRowLevelSecurity::test_cannot_write_another_orgs_row", "postgres"),
        (f"{DB}::TestRowLevelSecurity::test_cross_tenant_update_and_delete_affect_nothing", "postgres"),
        (f"{DB}::TestRowLevelSecurity::test_child_rows_cannot_hang_off_another_orgs_parent", "postgres")]),
    _r("TEN-03", "Database migrations can be rolled back and re-applied.", ["Change control"],
       [(f"{DB}::test_migrations_downgrade_and_reapply", "postgres")]),

    # AI agents
    _r("AI-01", "Actions that reach outside the organization always need a person's approval; no policy can allow "
                "them directly.", ["AI action policy"],
       [(f"{AI}::TestPolicy::test_actions_that_leave_the_organization_always_need_a_person", "both")]),
    _r("AI-02", "A proposed action runs once, through the same checks as a person's request, and only as the policy "
                "allows.", ["AI action policy"],
       [(f"{AI}::TestProposals::test_queued_then_approved_once_through_the_normal_checks", "both"),
        (f"{AI}::TestProposals::test_never_refuses_and_allowed_runs_directly", "both"),
        (f"{AI}::TestProposals::test_proposals_stay_in_their_organization", "both")]),
    _r("AI-03", "Every AI question and agent call is logged, and the log is append-only.", ["AI run log"],
       [(f"{AI}::TestRunLog::test_every_ask_is_logged_for_admins_and_auditors", "both"),
        (f"{MCP}::TestTools::test_every_call_is_logged_and_keys_are_rate_limited", "both"),
        (f"{DB}::test_ai_tables_are_tenant_scoped_and_the_run_log_is_append_only", "postgres")]),
    _r("AI-04", "An MCP key reaches only the MCP server, only its organization's data, and changes only as proposals.",
       ["AI action policy", "API keys"],
       [(f"{MCP}::TestAccess::test_only_mcp_keys_reach_the_mcp_server_and_nothing_else", "both"),
        (f"{MCP}::TestAccess::test_reads_see_only_the_keys_organization", "both"),
        (f"{MCP}::TestTools::test_changes_are_proposals_under_the_policy", "both")]),
    _r("API-01", "A read API key reads only the allowed routes of its organization and can never write.", ["API keys"],
       [(f"{KEYS}::TestPublicApi::test_reads_allowed_routes_in_its_own_organization", "both"),
        (f"{KEYS}::TestPublicApi::test_everything_else_is_refused", "both"),
        (f"{KEYS}::TestPublicApi::test_the_key_cannot_write_through_an_allowed_path_with_another_method", "both"),
        (f"{KEYS}::TestPublicApi::test_unknown_and_revoked_keys_get_401", "both")]),

    # Due diligence (docs/due-diligence.md)
    _r("DD-01", "Due diligence information is asked from a supplier only with a stated reason, by a person or an "
                "AI agent.", ["CSDDD Art. 8(2a)"],
       [(f"{DD}::test_asking_a_supplier_for_due_diligence_information_needs_a_reason", "both"),
        (f"{AI}::TestProposals::test_a_due_diligence_questionnaire_without_a_reason_never_reaches_the_queue", "both")]),
    _r("DD-02", "Risks are rated by people with a reason and prioritised by severity, then likelihood; supplier "
                "answers raise flags and are never scored.", ["LkSG §§ 3(2), 5", "CSDDD Art. 8, 9"],
       [(f"{DD}::TestRiskRegister::test_people_rate_risks_with_a_reason_and_the_register_is_prioritised", "both"),
        (f"{DD}::test_the_due_diligence_questionnaire_raises_flags_and_never_a_score", "both"),
        (f"{DD}::test_the_catalogue_follows_the_law_and_the_migration", "both")]),
    _r("DD-03", "Measures have owners in the organization and their effectiveness is reviewed; the risk analysis is "
                "reviewed on a set interval and after a significant change.", ["LkSG §§ 5(4), 6(5), 7(4)",
                                                                                 "CSDDD Art. 10, 15"],
       [(f"{DD}::TestRiskRegister::test_measures_have_members_as_owners_and_their_effectiveness_is_reviewed", "both"),
        (f"{DD}::TestReviewCycle::test_review_states", "both"),
        (f"{DD}::TestReviewCycle::test_a_review_is_recorded_and_a_later_incident_suggests_another", "both")]),
    _r("DD-04", "The year's due diligence documentation can be exported, and the export is audited.", ["LkSG § 10(1)"],
       [(f"{DD}::test_the_yearly_documentation", "both")]),
]
