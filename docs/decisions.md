# Decisions

## 2026-10-23 — Nemotron-3.5-Super-VL is the main leaf diagnoser

nvidia/Nemotron-3.5-Super-VL on Token Factory is the main leaf diagnoser. It was tested in one sealed run on 252 public BRACOL test leaves (Brazil). Rust vs not-rust accuracy was 89.3% (95% Wilson CI 84.9-92.5%), against 81.3% for the colour-histogram LR baseline. Macro-F1 was 0.867 vs 0.787. McNemar p=0.0055 (34 vs 14 discordant leaves). Rust recall was 78.1% (57/73), against 79.5% (58/73) for the LR. ECE was 0.11, so confidence is hidden in the UI. Cost was $0.00014 per image and p95 latency 1.3 s.

Rule applied: the approved bar was McNemar p<0.05 favouring Nemotron and rust recall >=58%, and both were met. The conflict: PLAN.md §6 also required rust recall >= the LR's. Nemotron misses that by one leaf. The Captain ruled the approved rule binding because a one-leaf difference isn't meaningful.

Caveat: this test set had already been scored once, during the earlier app run, so it isn't pristine. The prompt was chosen on validation only and frozen with sha hashes before the test run. Hashes and the sealed numbers are in [eval/nemotron-leaf/FROZEN.md](eval/nemotron-leaf/FROZEN.md) and [eval/nemotron-leaf/results.md](eval/nemotron-leaf/results.md).

UI: the «Orientativo — no es un diagnóstico» tag and an always-visible «Consultar a un técnico» button. The trust-panel sentence is in [results.md](eval/nemotron-leaf/results.md).
