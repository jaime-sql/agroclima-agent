# Nemotron-3.5-Super-VL on BRACOL coffee leaves: sealed results
Run Fri Oct 23 2026, about 00:19–00:22 SV (UTC-6). Model `nvidia/Nemotron-3.5-Super-VL`, Token Factory OpenAI-compatible API, temperature 0, reasoning off, strict JSON schema, prompt v1. The prompt and settings were frozen before the test run: see FROZEN.md (frozen_config.json sha256 d0c2017a…5f87, run.py sha256 cc054ce4…b9f). The test-list sha256 was checked and matched c9b88e6b…6895. There was one sealed run: 252 calls, 0 retries, 0 errors, nothing changed afterwards.
Caveat: this test set was already viewed once before, when the app run was scored. Nobody tuned on it, but it isn't pristine.

## Validation (253 images; prompt selection used binary macro-F1)
| prompt | acc | macro-F1 | rust recall | abstain |
|---|---|---|---|---|
| v1 (selected) | 92.9% | 0.919 | 0.880 | 0 |
| v2 | 90.1% | 0.892 | 0.940 | 0 |
| v3 | 83.8% | 0.784 | 0.518 | 0 |
Smoke test, 3 val images: parsing OK, 414 input and 22 output tokens per image, $0.00014 per image, under the $0.01 stop threshold.

## Sealed test (252)
| system | binary acc (Wilson 95%) | binary macro-F1 (bootstrap 95%) | rust recall | rust precision | 3-class acc (Wilson) | 3-class macro-F1 (bootstrap) |
|---|---|---|---|---|---|---|
| Nemotron-3.5-Super-VL, prompt v1 (sealed) | 225/252 = 89.3% (84.9%–92.5%) | 0.867 (0.815–0.912) | 0.781 (57/73) | 0.838 | 224/252 = 88.9% (84.4%–92.2%) | 0.899 (0.862–0.932) |
| LogReg HSV histogram (baseline_preds.json) | 205/252 = 81.3% (76.1%–85.7%) | 0.787 (0.732–0.836) | 0.795 (58/73) | 0.644 | 189/252 = 75.0% (69.3%–79.9%) | 0.729 (0.667–0.787) |

Abstentions: 0/252 (0.0%); HTTP: all {200}; calls with retries: 0; unparsed: 0
McNemar exact (binary correctness, paired n=252): Nemotron right/LR wrong = 34, LR right/Nemotron wrong = 14, p = 0.005515

| conf bin | n | mean conf | observed acc |
|---|---|---|---|
| 0.6–0.8 | 106 | 0.693 | 0.811 |
| 0.8–1.0 | 146 | 0.852 | 0.952 |
ECE (5 equal-width bins, binary, answered only): 0.1075

Latency (client wall, Token Factory API): p50 1.09 s, p95 1.30 s, max 1.80 s (concurrency 8)
Cost per image (measured usage × $0.30/$0.90 per 1M): mean $0.000143, p95 $0.000144; sealed total $0.0361; image tokens/image: {'image': 278}

**Decision rule (task):** main diagnoser iff McNemar p<0.05 favouring Nemotron AND rust recall>=58%. p=0.005515, favours Nemotron, recall 78.1% → **MAIN DIAGNOSER**; confidence HIDDEN (ECE>0.05).
## Conflict with PLAN.md §6, reported rather than resolved
The PLAN.md pass bar is stricter: Wilson lower bound > 81.3% (84.9%, met), macro-F1 > 0.787 (0.867, met), **and rust recall ≥ 0.795 (0.781, NOT met, 57/73 vs the LR's 58/73)**. Under PLAN.md the verdict would be **second opinion**. Under the task's rule (recall ≥ 58%) it is **main diagnoser**. The team lead needs to pick which rule applies.

## Spend
Smoke and reasoning-toggle probes ≈ $0.002; val 3×253 = $0.1113; sealed test = $0.0361. Total ≈ $0.15 of the $5 budget.
Files: raw_nemotron_val_v{1,2,3}.jsonl, raw_nemotron_test.jsonl, frozen_config.json, FROZEN.md, run.py, valscore.py, score_nebius.py, scores_nebius.md.

## Trust panel sentence (approved by Captain 2026-10-23)
"Probado con 252 fotos públicas de hojas de café de Brasil (no de El Salvador), fotografiadas sobre fondo blanco, no en el campo: acertó roya o no roya en 89% (IC 95%: 85–93%), frente a 81% de un modelo simple de color. Detecta 78% de las hojas con roya: se le escapa cerca de 1 de cada 5. Orientativo — no es un diagnóstico."
Confidence stays hidden (ECE 0.11 > 0.05).
Fallback sentence (colour-histogram model answered):
"Probado con 252 fotos públicas de hojas de café de Brasil (no de El Salvador), fotografiadas sobre fondo blanco, no en el campo: acertó roya o no roya en 81% (IC 95%: 76–86%). Detecta 79% de las hojas con roya: se le escapa cerca de 1 de cada 5. Orientativo — no es un diagnóstico."
