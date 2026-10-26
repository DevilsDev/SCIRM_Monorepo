# Regulatory watch

Follow what the FDA and the European Medicines Agency (EMA) publish about the substances
and products you buy. Add them to your organization's **watchlist**; every regulatory
record that names one shows up on **Intelligence → Regulatory watch**, as a
`watchlist.matched` [webhook](webhooks.md), and in the [digest](scheduled-reports.md).

## Sources

| Source | What | How it is read |
|---|---|---|
| FDA drug recalls, shortages, warning letters, import alerts | as on the intelligence feed | see the feed |
| **EMA medicine shortages** | EMA's list of shortages of centrally authorised medicines: ongoing, resolved and discontinued, with active substance, forms, alternatives and expected resolution | the whole list at every run; an entry EMA drops is delisted |
| **EMA safety communications (DHPCs)** | direct healthcare professional communications: safety signals, quality defects, shortages, new measures | entries updated within the ingestion lookback |
| **EMA referrals** | EU referral procedures, with their status (started, under evaluation, opinion, final decision) and whether they are safety referrals | entries updated within the ingestion lookback |

The EMA records come from the JSON data files EMA publishes on its website and refreshes
daily (reuse is allowed with acknowledgement of the source). Only human medicines are
read. A file that changes format is reported as a source error on the sources page, never
treated as "no records".

**Severity** comes from the record itself: an ongoing EMA shortage with no alternatives is
*high*, other ongoing or discontinued ones *medium*, resolved ones *low*; safety signals and
quality defects in DHPCs are *high*; open safety referrals *high*, other open referrals
*medium*, concluded ones *low*.

## The watchlist

Administrators and analysts add terms (substances or products, up to 200, each 3 to 100
characters, with an optional note); everyone can read it.

A term matches as **whole words**, ignoring case and punctuation, in a record's title,
summary and the substance or product fields of its source:
- "metformin" matches "Metformin Hydrochloride Tablets" and "METFORMIN-HCl", but not
  "metformina";
- "immunoglobulin" does not match "immunoglobulins": use the form the regulators use (the
  INN for substances).

EMA records name medicines and active substances, not manufacturers, which is why they are
followed through the watchlist rather than matched to supplier names. FDA records still
match suppliers by name as before; on this screen they also appear when they name a
watched term.

These are public records matched by wording, not findings about your suppliers: check the
source record. EMA records are not used to compute supplier scores or the back-tested Watch
flag.

## API

- `GET /api/v1/watchlist`, `POST /api/v1/watchlist` (`kind`: `substance` or `product`,
  `term`, `note`), `DELETE /api/v1/watchlist/{id}`
- `GET /api/v1/regulatory-watch?days=180&source=ema_dhpc`: records with activity in the
  period that name a watched term, newest first (up to 500). `truncated: true` means older
  matches were left out (more than 500 matches, or more than 5,000 candidate records):
  choose a shorter period or one source; the screen says so too

Adding and removing terms is recorded in the [audit log](audit-log.md)
(`watchlist.added`, `watchlist.removed`).
