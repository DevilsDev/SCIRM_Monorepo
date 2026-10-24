# Supplier assessments

Send a questionnaire to a contact at a supplier. They answer through the **supplier
portal**, a personal link that needs no account. Their answers, a score, and the list of
their own critical suppliers come back to SCIRM.

Everything a supplier enters is **supplier-provided**: their own statements, shown as such,
never treated as a verified finding. It is not used by Ask or by the public-record matching.

## Sending a questionnaire

**Supply Chain → Supplier assessments → Send a questionnaire** (administrators and
analysts; viewers and auditors can read everything).

- Pick the supplier, the questionnaire, the contact's email, an optional due date, and how
  long the link works (7 to 90 days, 30 by default).
- With email configured (`SMTP_HOST`, see [scheduled reports](scheduled-reports.md)) the link
  is emailed to the contact. Either way it is **shown once**, to copy and send yourself.
- **New link** replaces the link (the old one stops working at once); **Cancel** withdraws
  the questionnaire. Both only while it is waiting for answers.

## Questionnaires

Two built-in templates (labelled as such) cover common needs:

- **Supply continuity**: business continuity plan, single sites and single sources, safety
  stock, recent disruptions, and their critical suppliers.
- **Quality and compliance**: GMP status, the last inspection and its outcome, open
  corrective actions, recalls, change notification, data integrity.

Under **Questionnaires** you can build your own (up to 60 questions). Question types: yes/no,
text, number, date, one of several options, and a list of their suppliers. A sent
questionnaire keeps its own copy of the questions, so changing or retiring a questionnaire
never changes what a supplier already received.

## The portal

The supplier opens `/portal#<token>`:

- They can **save a draft** and come back with the same link until they submit.
- **Submit** checks that every required question is answered, records their name and email,
  and locks the answers. The link then stops working.
- A link that has expired, been replaced, been cancelled or already been used gets one and
  the same answer: ask for a new link. It never reveals which of these happened.

## Score and flags

The score (0 to 100) is computed by code, from yes/no questions that state which answer is
preferred and how much it matters (weight 1 to 5): the weighted share of those questions
answered the preferred way, out of those answered. Each answer the other way is listed as a
flag, most important first. Questions without a preferred answer are not scored.

## Their suppliers

Answers to a "list of their suppliers" question (company, country, city, what they supply)
are kept per supplier as **supplier-reported sub-tier links**, apart from public-record
matches: `GET /api/v1/suppliers/{supplier_id}/subtier`.

## Review

A submitted questionnaire is **Answered: to review** until someone marks it reviewed, with an
optional note.

## Security

- The link's token is random, shown once, and stored only as its SHA-256. It sits in the
  URL fragment, so it is not sent in server logs or `Referer` headers.
- The portal reads only the `X-Portal-Token` header. It ignores `Authorization`, so a
  signed-in session in the same browser changes nothing, and the token reaches no other part
  of the API.
- Before anyone signs in, a single database function (`scirm_assessment_by_token`) turns a
  live token into its assessment and organization; every other step runs inside that
  organization under row-level security. An assessment can never point at another
  organization's supplier.
- Audit log: `assessment.sent`, `assessment.resent`, `assessment.cancelled`,
  `assessment.reviewed`, `assessment.template_created`, and `assessment.submitted` with the
  supplier contact as the actor (`supplier:<email>`). Drafts and portal reads are not
  logged.

## Not included yet

File uploads (certificates, reports) and reminders before the due date.
