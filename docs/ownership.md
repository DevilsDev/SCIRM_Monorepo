# Supplier ownership (GLEIF)

SCIRM shows who owns your suppliers, using the
[Global LEI Index](https://search.gleif.org/) published by the Global Legal Entity
Identifier Foundation (GLEIF). Its main use is to reveal hidden concentration: two
"different" suppliers in the same corporate group are one dependency.

Open **Supply Chain → Ownership** for all suppliers, or **Suppliers**, then a supplier,
then **Ownership** to link one.

## What GLEIF reports

A Legal Entity Identifier (LEI) is a 20-character code for one legal entity. Its record
holds the entity's legal name, addresses and status. Where reported, it also names the
entity's parents:

- **Direct parent:** the closest entity that consolidates it in its financial statements.
- **Ultimate parent:** the highest entity that does so.

These are *accounting consolidation* parents, not beneficial owners. When an entity reports
no parent, it gives one of GLEIF's reasons instead. SCIRM shows each reason in plain
words:

| GLEIF reason | Shown as |
|---|---|
| NATURAL_PERSONS | Controlled by one or more people without an intermediate consolidating entity |
| NON_CONSOLIDATING | Controlled by entities that do not prepare consolidated statements |
| NO_KNOWN_PERSON | No known person controls it (for example, dispersed shareholding) |
| NON_PUBLIC | A parent exists, but its details are not public |
| NO_LEI | A parent exists, but it has no LEI and did not consent to get one |

An entity that reports neither a parent nor a reason is shown as **not reported**, which
is **unknown**, not independent.

## Linking a supplier to its LEI

SCIRM never links a supplier to an LEI by itself.

1. In the supplier panel, under **Ownership**, search GLEIF by legal name, optionally
   limited to a country. You can also paste an LEI.
2. Check the candidates' names, places and registration status. Open a record at GLEIF if
   you need more detail.
3. Choose **This is the supplier** on the right one. If none fits, leave the supplier
   unlinked.

Only admins and analysts can search and link. **The name and country you search for are
sent to GLEIF** (api.gleif.org); nothing else about the supplier is.

When you link a supplier, SCIRM reads its record and both parent levels from GLEIF and
keeps that answer with the link. The link records who confirmed it and when, and appears
in the audit log with the LEI. **Refresh from GLEIF** reads the record again. **Remove
link** deletes the link; the audit log keeps both the link and its removal.

A warning appears when:

- the LEI's registration is not *issued* (for example *lapsed*, which means the entity
  stopped renewing it, so its data may be out of date)
- GLEIF lists the entity itself as no longer active

## Shared owners

The Ownership page groups linked suppliers under the same top entity. That entity is the
ultimate parent reported to GLEIF. If a supplier reports no ultimate parent, it counts as
its own top entity, so a supplier that owns another supplier is grouped with it.

What a group does and does not tell you:

- **A group is reported data.** Suppliers in it are in the same corporate group.
- **No group is not proof of independence.** Suppliers whose parents are withheld or not
  reported, and suppliers without an LEI, can still share an owner that GLEIF does not
  show.

The page also lists active suppliers without a confirmed LEI. Their ownership is unknown.
LEI coverage is high for banks, listed companies and larger EU firms. It is much thinner
for smaller suppliers and in many countries outside the EU and US.

## When GLEIF is unavailable

Searching, linking and refreshing need GLEIF. If it cannot be reached, SCIRM says so and
changes nothing. Links you already made, and the shared-owner view, keep working from the
stored answers.

## Data and licence

LEI data, including the parent relationships, is published by GLEIF under
[CC0 1.0](https://www.gleif.org/en/meta/lei-data-terms-of-use). SCIRM names GLEIF as the
source and links each record. GLEIF does not endorse SCIRM.

**Deployment:** the coordinator calls `https://api.gleif.org/api/v1` (change it with
`GLEIF_API_URL`), so it needs outbound HTTPS to api.gleif.org. Tests use recorded responses
(`tests/fixtures/gleif`) and never call GLEIF.
