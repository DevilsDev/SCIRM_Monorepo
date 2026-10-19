# Back-test: does SCIRM flag a firm before its next serious recall?

Every scoring or AI change is measured against this. It uses real FDA history and
only information that was public at each point in time.

```
python evals/backtest/backtest.py            # report on the committed snapshot
python evals/backtest/fetch_data.py          # refresh the snapshot from openFDA
```

## Method

- **Data:** the openFDA drug recall (enforcement) history from 2018 onward, saved in
  `data/fda_enforcement.jsonl.gz` (about 10,000 records).
- **Question:** at the start of each month T, would a firm be flagged before it has a
  **Class I recall** (the most serious class) published in the next 90 days?
- **No hindsight:** the score at T uses only recalls *published* before T. Recall
  initiation dates are ignored, because FDA publishes recalls weeks after they
  start. `tests/intel/test_intel_backtest.py` enforces this.
- **No tuning on the answers:** the alert threshold is set on 2021–2022 (top 10%
  of firms) and frozen. The reported numbers come from 2023 onward.
- **Scope:** firms with at least one recall in the prior 3 years. Firms with none
  are not in FDA's data and cannot be scored. Shortages are excluded, because
  openFDA keeps only the current shortage list, so past shortages are missing.

## Baseline (snapshot 2026-10-20, rule `libs/intel/scoring.py`)

**Headline: distinct Class I recall events from 2023 on**, each judged once at the
last monthly cutoff at least 30 days (or 60) before FDA published it.

| | 30 days ahead | 60 days ahead |
|---|---|---|
| Class I recall events | 145 | 141 |
| at firms with any recall history (scorable) | 71 | 66 |
| flagged, among scorable | **29 (41%)** | 26 (39%) |
| flagged, among all events | **20%** | 18% |
| "new problems" (no Class I in prior 180 days), flagged | 31% of 61 | 30% of 57 |

**Per firm-month (secondary):** 712 firms and 16,792 firm-months, with a 1.1% base
rate of a Class I recall in the next 90 days. The rule flags 9.8% of them at 4.5%
precision (4.2x the base rate), with AUC 0.70 (0.75 in the tuning period). The
naive baseline "any recall in the last year" flags 43% at 1.8% precision.

**What this means:**
- **Coverage is the main limit.** Half of all serious recalls happen at firms with
  no FDA recall history, so a recall-history signal cannot see them. Flagging
  those needs other sources (warning letters, import alerts, inspections, news).
- **Among firms it can see,** it flags about 4 in 10 serious recalls at least a
  month before FDA publishes them, while flagging 1 firm in 10.
- **Precision is low.** About 95% of flags are not followed by a Class I recall
  within 90 days. A flag means "watch this supplier", not a prediction.
- Later signals and the AI evidence work have to beat these numbers, above all
  "flagged, among all events", to earn their place.

`results/baseline.json` holds the full result.
