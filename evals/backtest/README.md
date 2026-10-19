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
- **Two scopes:**
  - **All Class I drug recalls.**
  - **Recalls of FDA-listed drug products** (with an NDC). This is what pharma buyers
    source. This scope was added after a diagnosis showed that most recalls at firms
    with no history were tainted supplements sold online (e.g. "Volt Candy Wholesale
    Club"), not pharma suppliers. Both scopes are reported.

## Results (snapshot 2026-10-20), 30 days ahead

| Class I recall events since 2023 | Recalls only | Recalls + drug warning letters |
|---|---|---|
| **Listed drug products** (64 events): at firms with any history | 49 | 50 |
| ... flagged, among all 64 | **33%** (21) | 34% (22) |
| ... "new problems" (no Class I in prior 180 days), flagged | 36% of 44 | 38% of 45 |
| **All Class I drug recalls** (145 events): at firms with any history | 71 | 74 |
| ... flagged, among all 145 | 20% (29) | 21% (31) |
| Flags per month, across all firms | 37 | 61 |
| Precision per firm-month (base rate) | 4.7% (1.1%) | 3.1% (0.5%) |
| AUC per firm-month | 0.70 | 0.73 |

At 60 days ahead the numbers are 2 to 3 points lower.

**What this means:**
- **For pharma suppliers,** recall history flags about **1 in 3 serious recalls of
  listed drugs at least a month ahead**, while flagging 1 firm in 10. Coverage is
  decent: 77% of these recalls happen at firms with earlier FDA history.
- **Warning letters barely help this outcome.** They add one flagged event in 64
  while adding two thirds more flags, so the product shows them as records but its
  "watch" flag uses recalls only (`libs/intel/scoring.WATCH_THRESHOLD`, pinned to
  this back-test by a test). They remain valuable for supplier qualification.
- **Precision is low.** About 95% of flags are not followed by a Class I recall
  within 90 days. A flag means "watch this supplier", not a prediction.
- **Next to beat:** the "listed products, flagged among all" figure, 33%. FDA
  inspection outcomes need a free Data Dashboard API key. Import alerts need
  dated history; a start would be snapshotting the Red List weekly from now on.

`results/baseline.json` holds the full result.
