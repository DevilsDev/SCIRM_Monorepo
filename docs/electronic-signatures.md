# Electronic signatures

SCIRM lets people sign records electronically: a **supplier assessment** they reviewed or
approved, a **war-room incident** (for example its closure), and an **action an AI agent
proposed** once it was decided. The signatures are built to support the controls of
**21 CFR Part 11** (FDA's rule on electronic records and signatures). SCIRM supports these
controls; whether your use of it complies with Part 11 is established by your own
validation and procedures.

## Signing

On the record, **Sign**: choose the meaning (*Reviewed*, *Approved* or *Responsible*), add an
optional comment, and re-authenticate:

- **Accounts with a SCIRM password** enter the password, and the two-step code if two-step
  sign-in is on, **every time** they sign.
- **Accounts that sign in with single sign-on** go to the identity provider, which is asked
  for a fresh login (`prompt=login`, `max_age=0`). SCIRM records the signature only if the ID
  token says the person logged in just now (`auth_time`), it is the same person who started
  signing, and the record has not changed in the meantime.

Five wrong passwords or codes in 15 minutes stop signing for that person for 15 minutes.
Every signature, and every failed attempt, is in the [audit log](audit-log.md).

## How each section is addressed

| 21 CFR Part 11 | In SCIRM |
|---|---|
| **11.50** Signature manifestations: the signer's printed name, the date and time, and the meaning, in any human-readable form | Each signature stores and shows the name, email, date and time (UTC, shown in your time zone) and meaning on the record's page. |
| **11.70** Signature/record linking: signatures cannot be excised, copied or transferred | A signature stores the SHA-256 of the record's exact content when it was signed, with the record's type and id. It is shown as *record changed after signing* if the record changes later. Signatures can be added and read but never changed or deleted (the database refuses it), and deleting or editing a record never removes them. |
| **11.100(a)** Unique to one individual, never reused or reassigned | A signature is tied to the person's account id, which is never reassigned; emails are unique across SCIRM. |
| **11.100(b)** Verify the individual's identity before assigning a signature | Your organization's procedure (for example at invitation or SCIM provisioning). |
| **11.100(c)** Certify to FDA that electronic signatures are legally binding | Your organization's letter to FDA. |
| **11.200(a)(1)** At least two components (an identification code and a password); all of them for signings outside one continuous session | The account (the signed-in person's identity) and the password, re-entered for **every** signing (stricter than the continuous-session allowance), plus the two-step code when set; or a fresh login at your identity provider, with its own factors. |
| **11.200(a)(2)-(3)** Used only by the genuine owner; misuse needs two or more people to collaborate | Passwords are stored only as hashes and administrators cannot see or set them (a reset link goes only to the person's own email); two-step codes come from the person's own device. An administrator can reset someone's two-step sign-in (it is audited), but still does not have their password. |

Not covered by SCIRM itself: your validation (for example the computer software assurance
approach), procedures and training, and the other system controls of section 11.10 that
depend on how you operate SCIRM.

API: `GET /api/v1/signatures?record_type=&record_id=`, `GET /api/v1/signatures/method`,
`POST /api/v1/signatures` (password), `POST /api/v1/signatures/sso/prepare` (identity provider).
