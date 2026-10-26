# Back-test: does SCIRM flag a firm before its next serious recall?

Every scoring or AI change is measured against this. It uses real FDA history and
only information that was public at each point in time.

```
python evals/backtest/backtest.py            # report on the committed snapshots
python evals/backtest/fetch_data.py          # refresh the snapshots from FDA
```

## Method

- **Data:**
  - `data/fda_enforcement.jsonl.gz`: openFDA drug recalls from 2018 on, about 10,000
    records.
  - `data/fda_warning_letters.jsonl.gz`: FDA warning letters, about 2,500. FDA's
    index starts in January 2021, and tobacco letters are excluded.
- **Question:** at the start of each month T, was a firm flagged before it had a
  **Class I recall** (the most serious class)? Each distinct recall event is judged
  once, at the last monthly cutoff at least 30 (or 60) days before FDA published it.
- **No hindsight:** the score at T uses only events *published* before T: a recall's
  FDA report date, or a warning letter's posting date. Initiation and letter-issue
  dates are ignored, because they come earlier. `tests/intel/test_intel_backtest.py`
  enforces this.
- **No tuning on the answers:** each variant's alert threshold is set on 2022 (top
  10% of firms) and frozen; numbers are reported from 2023 on. 2022 is the first
  year with a full year of warning-letter history.
- **Excluded sources:** shortages and import alerts. FDA publishes only their current
  lists, so entries removed in the past are missing, and which entries survived
  depends on what happened later. They are shown in the product but cannot be
  back-tested.
- **Firms with no FDA history** cannot be scored. Their events are counted and
  broken down by whether openFDA links the product to an FDA drug listing (NDC).

## Results (snapshot 2026-10-20), 30 days ahead

145 Class I drug recall events since 2023, each judged once:

| | Recalls only | Recalls + drug warning letters |
|---|---|---|
| At firms with FDA history (scorable) | 71 | 74 |
| ... flagged ahead | **29 (41%)** | 31 (42%) |
| ... "new problems" (no Class I in prior 180 days), flagged | 31% of 61 | 33% of 64 |
| At firms with no FDA history | 74 | 71 |
| ... products with no FDA drug listing (mostly supplements sold as drugs online) | 59 | 57 |
| ... listed drugs | 15 | 14 |
| Flagged, among all 145 | 20% | 21% |
| Flags per month, across all firms | 37 | 61 |
| Precision per firm-month (base rate) | 4.7% (1.1%) | 3.1% (0.5%) |
| AUC per firm-month | 0.70 | 0.73 |

At 60 days ahead the figures are 1 to 2 points lower.

**What this means:**
- **Among firms with FDA history,** recall history flags about **4 in 10 serious
  recalls at least a month ahead**, while flagging 1 firm in 10.
- **Half of all Class I drug recalls are at firms with no FDA history.** About four
  in five of those involve products with no FDA drug listing, mostly supplements
  sold as drugs online, which pharma buyers do not source from. The rest (about 15
  events since 2023) are the real coverage gap.
- **Warning letters barely help this outcome.** They add two flagged events in 145
  while adding two thirds more flags. The product shows them as records, which is
  useful for supplier qualification. Its "watch" flag uses recalls only, with exact
  name matches only (`libs/intel/scoring.WATCH_THRESHOLD`, pinned to this back-test
  by a test).
- **Precision is low.** About 95% of flags are not followed by a Class I recall
  within 90 days. A flag means "watch this supplier", not a prediction.
- **Next to beat:** 41% among firms with history, and the 15 listed-drug events at
  firms with none. FDA inspection outcomes need a free Data Dashboard API key.
  Import alerts need dated history, which SCIRM now builds: delisted entries are
  timestamped instead of deleted.
- The recall definition "listed products only" (an NDC in openFDA) was tried as a
  supply-chain scope and dropped as a headline: openFDA leaves NDCs unlinked on
  many real manufacturers' recalls (Novartis, Pfizer, Baxter), so it is kept only
  as a diagnostic in `results/baseline.json`.

`results/baseline.json` holds the full result.
