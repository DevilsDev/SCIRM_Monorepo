# Due diligence (LkSG, CSDDD)

**Supply Chain → Due diligence** helps you carry out and document human rights and
environmental due diligence on your suppliers. It covers the German Supply Chain Due
Diligence Act (LkSG) and the EU Corporate Sustainability Due Diligence Directive (CSDDD).
SCIRM supports documenting these duties. Whether your company meets them depends on what you
do and decide; SCIRM does not establish compliance.

## The law, as of 25 October 2026

- **LkSG** is in force, unamended, for companies with at least 1,000 employees in Germany.
  A bill to drop the yearly report to BAFA (section 10(2) to (4)) had its first reading on
  16 January 2026 and is still in committee. BAFA switched off its reporting form in November
  2025 and only pursues serious violations. The duties themselves still apply: risk analysis,
  prevention and remedial measures, a complaints procedure and internal documentation kept
  for seven years (section 10(1)).
- **CSDDD** (Directive (EU) 2024/1760) was amended by the Omnibus I Directive (EU) 2026/470.
  It now applies only to companies with more than 5,000 employees and more than EUR 1.5 billion
  net worldwide turnover (or that EU turnover, for non-EU companies). It applies from
  **26 July 2029**, through each Member State's national law. Article 22 (the climate
  transition plan) was deleted. The Annex listing the rights and prohibitions was not changed.

## How it works

1. **Scope.** The page lists every active supplier with what SCIRM already holds: country and
   sites, 12-month spend per currency, war-room incidents and questionnaires. CSDDD Article 8
   asks for a scoping exercise "based solely on reasonably available information". SCIRM
   computes no risk index and has no country or sector scores. Suppliers that need attention
   come first.
2. **Risks.** For a supplier, record each risk in one of the areas of the law (LkSG
   section 2, CSDDD Annex): child labour, forced labour, occupational safety, wages, freedom
   of association, discrimination, pollution that harms people, land, security forces,
   mercury, persistent organic pollutants, hazardous waste, biodiversity and so on.
   - A person rates the likelihood and the severity, from 1 to 4, and must give a reason.
   - Each risk records where it came from: scoping, an in-depth assessment, the supplier's
     questionnaire, an incident, a public record, or a notification or complaint received.
   - Risks are listed most severe first, then by likelihood (CSDDD Article 9, LkSG section 3(2)).
3. **In-depth assessment.** Where risks are most likely and severe, you can ask the supplier
   with the built-in **Human rights and environment** questionnaire (see
   [supplier assessments](supplier-assessments.md)).
   - Sending it needs a reason, because a business partner is asked for information only
     where necessary (CSDDD Article 8(2a)). There is no "send to all suppliers".
   - Answers are the supplier's claims: they raise flags to follow up and are never scored.
4. **Measures.** Plan prevention, correction and remediation measures, each with an owner (a
   member), a due date and a status.
   - The last-resort steps are kinds of measure and are labelled as such: an enhanced
     prevention plan, no new or extended business, suspension, and ending the relationship
     (CSDDD Article 10(6), LkSG section 7(3)).
   - SCIRM never suggests or takes them on its own.
   - Record how each measure's effectiveness was checked.
5. **Review.** Record each review of a supplier's risk analysis with its conclusions. The
   interval is yours to set: 12 months by default (LkSG section 5(4)), at most 60 months
   (CSDDD Article 15). A war-room incident linked to the supplier, or a questionnaire it
   submitted after the last review, marks the review as *suggested*: a significant change
   may have happened.
6. **Documentation.** For each year, download the documentation as JSON: the risks
   identified, the measures, the effectiveness checks, the conclusions and the full history.
   The history is also available as CSV.

## What SCIRM keeps

Risks, measures and their history can never be deleted, and the history cannot be edited
(the database refuses it). A supplier with due diligence records cannot be deleted, only
deactivated. Every change is also in the [audit log](audit-log.md).

## How each duty is supported

| Duty | LkSG | CSDDD (as amended) | In SCIRM |
|---|---|---|---|
| Risk management and responsibility | § 4 | Articles 5, 7 | Owners on measures; the history shows who did what. Appointing a responsible person and adopting the policy statement are yours to do. |
| Risk analysis | § 5 | Article 8 (scoping exercise, then in-depth assessment) | Scoping view; risk register by area; the due-diligence questionnaire with a stated reason. |
| Prioritisation | § 3(2), § 5(2) | Article 9 | People rate severity and likelihood; risks are listed by severity, then likelihood. |
| Preventive measures | § 6 | Article 10 | Measures with kind, owner, due date and status. |
| Remedial action and last resort | § 7 | Articles 10(6), 11, 12 | Corrective and remediation measures; last-resort steps labelled, never automatic. |
| Complaints procedure | § 8, § 9(1) | Article 14 | Not provided: a notification you received can be recorded as a risk's source. SCIRM has no public complaints channel. |
| Indirect suppliers | § 9(3) | Article 8 (chain of activities) | Risks can be recorded from substantiated knowledge, for example a public record or the supplier's own reported suppliers. |
| Review and monitoring | § 5(4), § 6(5), § 7(4) | Article 15 (at least every 5 years and after a significant change) | Review interval, review records with conclusions, review suggested after incidents or new answers, effectiveness of measures. |
| Documentation | § 10(1) (seven years) | Article 16 (reporting) | Records that cannot be deleted; yearly documentation download. SCIRM does not produce the public LkSG report or the CSDDD statement. |

Not covered by SCIRM: your policy statement, the complaints procedure, stakeholder engagement
(CSDDD Article 13), training and the decisions themselves.

API: `GET /api/v1/due-diligence/overview`, `GET /api/v1/due-diligence/suppliers/{id}`,
`POST /api/v1/due-diligence/risks`, `PATCH /api/v1/due-diligence/risks/{id}`,
`POST /api/v1/due-diligence/measures`, `PATCH /api/v1/due-diligence/measures/{id}`,
`POST /api/v1/due-diligence/reviews`, `GET|PUT /api/v1/due-diligence/settings`,
`GET /api/v1/due-diligence/export?year=&format=json|csv`, `GET /api/v1/due-diligence/catalog`.
