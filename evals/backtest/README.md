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

| | Result |
|---|---|
| Firms / firm-months | 712 / 16,792 |
| Base rate (Class I recall in next 90 days) | 1.1% |
| Flagged | 9.8% of firm-months |
| Precision (flag followed by a Class I recall) | 4.5% (4.2x the base rate) |
| Recall (Class I recalls flagged beforehand) | 41.4% |
| Recall on firms with no Class I recall in the prior 180 days | 33.8% |
| AUC | 0.695 (tuning period: 0.749) |
| Median warning | 41 days |
| Baseline "any recall in the last year" | flags 43%, precision 1.8%, recall 71% |

**What this means:** recall history alone flags 1 firm in 10 and catches about 4 in
10 serious recalls, roughly six weeks ahead. Most flags (about 95%) are not
followed by a Class I recall within 90 days. Treat a flag as "watch this
supplier", not as a prediction. Later signals, such as warning letters, import
alerts and the AI evidence work, have to beat these numbers to earn their place.

`results/baseline.json` holds the full result.
