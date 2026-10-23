# What changed from AgroClima

Baseline: [jaime-sql/agroclima](https://github.com/jaime-sql/agroclima) at `39644d87a3cbe4419389bef8af4f6cd1da53b73c` (MIT). AgroClima Agent is a new service for the Nebius Global AI Hackathon (Best Apps and Agents, plus the Tavily bonus). It keeps the weather rules and the handoff bands, and replaces the hosting stack and the model path.

## Kept on purpose

- Coffee-rust scoring for El Salvador (`America/El_Salvador`, 7-day Open-Meteo, the same wet-hour, temperature, rain, latency, and consecutive-day recipe). See `docs/rust-risk-rules.md`.
- The Spanish reason lines and the footer that the cutoffs are our estimate and are not validated by ISC, CENTA, or MAG.
- Fungicide **class names only**, with “dosis según etiqueta / su agrónomo”. Trial rates from the rules note are not shown.
- Photo bands from the original flow: retake wins; sano needs confidence ≥ 0.85; ≥ 0.80 is seguro; 0.60–0.79 is probable; below 0.60 has no plan.
- The 20 sourced coffee municipalities in `src/agroclima_agent/data/locations.json` (town centres or the three original slope points, not farms).
- The public CENTA switchboard and site, used only as the handoff line.

## New in this repo

| Area | AgroClima | AgroClima Agent |
| --- | --- | --- |
| Runtime | Next.js on a Cloudflare Worker | Python app. One command: `./run` |
| Models | OpenAI `gpt-4.1-mini` for the leaf; Blaxel then OpenAI for questions | Nebius Token Factory, OpenAI-compatible. Nemotron Nano summarizes. Nemotron Super (or Ultra via env) words the plan. NVIDIA vision reads the leaf |
| Vision check | Single model call | `nvidia/Nemotron-3.5-Super-VL` is the leaf path. On error or timeout the colour model answers, and the audit log records the path. Per-leaf confidence is not shown. `agroclima-eval` still scores the colour histogram on synthetic leaves |
| Official alerts | Not searched | Shared Tavily cache: basic search only, at most once per department per 24 hours, not on a page load and not in the nightly job. Caps default to 40/day and 300 total. Stale rows are labelled sin actualizar |
| Risk map | Computed when a place is opened | Nightly Nebius Serverless AI job writes a per-department map. The job does not call a model |
| Who decides the level and the handoff | Rules for the level; the ask model could still talk about the plan | Rules decide the level, the plan fields, and whether a technician is needed. The model only narrates that decision, and a dose in the narration is dropped |
| Safety log | Ask-path headers and log lines | JSONL audit per step: hashed inputs, model id, latency, tokens when the API returns them. PII is redacted before the call |
| Keys | Worker secrets, empty diagnosis until `OPENAI_API_KEY` | `NEBIUS_API_KEY` and `TAVILY_API_KEY`. With either missing, that part runs in labelled mock mode so CI needs no secrets |
| UI | Spanish mobile flow, map, speech | English page with four steps: Clima → Alertas oficiales → Diagnóstico → Plan. Farmer text stays Spanish |
| Location | Phone GPS rounded to 3 decimals, or a picked municipality | Department picker only. Precise coordinates are redacted if they show up in free text |

## Explicitly not carried over

Cloudflare Workers, OpenNext, R2 audio cache, ElevenLabs speech, the Blaxel ask agent, the leaflet map, and the direct OpenAI vision default. Those belonged to the previous hosting setup. Speech and the map can return later; they are not required for the hackathon path.

## Hackathon fit

- Inference goes to `https://api.tokenfactory.nebius.com/v1` with NVIDIA open model ids (`nvidia/…`).
- Tavily is the official-alert step and is cited in the UI.
- Deadline context: Friday 30 October 2026, 11:00 America/El_Salvador.
