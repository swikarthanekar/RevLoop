# Model Selection — Prompt 12

## Context

Prompt 12 compared the frozen Prompt 11 Logistic Regression recovery baseline against one restrained XGBoost challenger (`xgb-v1.0.0`). Selection used predeclared materiality thresholds and regression guardrails on held-out synthetic test data and synthetic policy simulation.

## Dataset

| Field | Value |
|---|---|
| Dataset version | `synthetic_recovery_v1` |
| Case count | 15,000 |
| Generator seed | `20260901` |
| Split seed | `20260904` |
| Training CSV SHA-256 | `f9c8e534b5907d03514b8c8494d004fed7d60d94c3591af90c40a0439fece170` |
| Summary SHA-256 | `4539f31ef7b97c2365f1cf4a6f4bd434452a9b2ca229c1bba9d9752deed49bc6` |

Split discipline: train 10,500 cases / 30,981 predictive rows; validation 2,250 / 6,641; test 2,250 / 6,661. STOP rows remain in the dataset but are excluded from model fitting and predictive metrics.

## Logistic Regression

Frozen Prompt 11 reference (`LR source commit = fd08bf7`).

**Validation metrics**

| Metric | Value |
|---|---|
| ROC-AUC | 0.7803 |
| PR-AUC | 0.5722 |
| Log loss | 0.4784 |
| Brier | 0.1568 |
| ECE | 0.0075 |

**Test metrics (SYNTHETIC MODEL EVALUATION)**

| Metric | Value |
|---|---|
| ROC-AUC | 0.7764 |
| PR-AUC | 0.5563 |
| Log loss | 0.4768 |
| Brier | 0.1564 |
| ECE | 0.0102 |

Canonical artifact SHA-256: `152ecbc8ab4e5bc5b583059a824ea562363f920e238b4b7aa283d9cb74447ef2`

Logistic Regression was **not** retrained during Prompt 12. Re-evaluation on the reproduced dataset matched Prompt 11 within deterministic tolerance.

## XGBoost candidate

**Configuration**

| Parameter | Value |
|---|---|
| objective | `binary:logistic` |
| eval_metric | `logloss` |
| tree_method | `hist` |
| max_depth | 4 |
| learning_rate | 0.05 |
| n_estimators | 800 |
| min_child_weight | 5 |
| subsample | 0.8 |
| colsample_bytree | 0.8 |
| reg_lambda | 1.0 |
| reg_alpha | 0.0 |
| random_state | 20260901 |
| n_jobs | 1 |
| early_stopping_rounds | 50 |

**Early stopping**

| Field | Value |
|---|---|
| Configured estimators | 800 |
| Best iteration | 159 |
| Best validation score (logloss) | 0.4787 |
| Patience | 50 |

**Validation metrics**

| Metric | Value |
|---|---|
| ROC-AUC | 0.7806 |
| PR-AUC | 0.5714 |
| Log loss | 0.4787 |
| Brier | 0.1568 |
| ECE | 0.0086 |

**Test metrics (SYNTHETIC MODEL EVALUATION)**

| Metric | Value |
|---|---|
| ROC-AUC | 0.7794 |
| PR-AUC | 0.5628 |
| Log loss | 0.4746 |
| Brier | 0.1553 |
| ECE | 0.0123 |
| Positive rate | 0.2626 |

Evaluated candidate binary: `/tmp/revloop-xgb-eval/xgboost_candidate.joblib` (SHA-256 `0b89eb56446e4b5678c7673a065076cfad6c75e98e67484458ad37e8a86a2e38`). Audit metadata/metrics are persisted under `apps/api/app/ml/artifacts/xgboost_candidate.*`.

## Calibration

| Field | Value |
|---|---|
| Uncalibrated validation Brier | 0.1568 |
| Uncalibrated validation log loss | 0.4787 |
| Uncalibrated validation ECE | 0.0086 |
| calibration_method | `none` |

**Reason:** Uncalibrated XGBoost validation calibration was not clearly worse than frozen Logistic Regression (Brier within margin, ECE below absolute threshold). No sigmoid calibrator was applied.

## Policy simulation

**SYNTHETIC POLICY SIMULATION** on the same held-out test cases (one-step offline simulation).

| Metric | Logistic Regression | XGBoost | Naive baseline |
|---|---:|---:|---:|
| Expected synthetic recovered (minor) | 1,028,844,436 | 1,032,058,965 | 689,535,604 |
| Realized synthetic recovered (minor) | 1,071,780,028 | 1,070,070,133 | 688,147,189 |
| Realized recovery rate | 0.2964 | 0.2982 | 0.1991 |
| Selected intervention count | 2,250 | 2,250 | 1,962 |
| Contact action count | 0 | 6 | 0 |
| STOP count | 0 | 0 | 288 |
| No-selection count | 0 | 0 | 0 |

Both models beat the naive retry/WAIT baseline on expected synthetic recovered amount. XGBoost showed a modest expected-value gain (+0.31%) but did not cross the predeclared material policy threshold (+1%).

## Materiality rule

XGBoost must achieve at least one material win **and** pass all guardrails.

**Material thresholds**

| Criterion | Required | Actual delta (XGB − LR or ratio) | Pass |
|---|---:|---:|---|
| PR-AUC | ≥ +0.015 absolute | +0.0065 | **fail** |
| Brier | ≤ LR − 0.003 absolute | LR − XGB = +0.0011 | **fail** |
| Log loss | ≤ LR − 0.008 absolute | LR − XGB = +0.0022 | **fail** |
| Expected synthetic recovered | ≥ LR × 1.01 | ratio 1.0031 | **fail** |

**Regression guardrails**

| Guardrail | Limit | Actual | Fail |
|---|---:|---:|---|
| PR-AUC regression | ≥ LR − 0.010 | +0.0065 | no |
| Brier regression | ≤ LR + 0.003 | −0.0011 | no |
| Log loss regression | ≤ LR + 0.005 | −0.0022 | no |
| Expected recovered regression | ≥ LR × 0.995 | ratio 1.0031 | no |

No material win was observed. All guardrails passed.

## Selection

**SELECTED RUNTIME MODEL: LOGISTIC REGRESSION**

## Reason

XGBoost improved several test metrics marginally (PR-AUC +0.0065, Brier −0.0011, log loss −0.0022, expected policy value +0.31%) but did not meet any predeclared materiality threshold. Under the conservative tie/marginal rule, Logistic Regression remains the runtime default to avoid added complexity without clear synthetic evidence of material gain.

## Limitations

All current model and policy comparisons use synthetic data. They are not merchant production-performance claims.
