# Coffee rust weather rules (carried over)

These rules are the AgroClima v1 recipe from jaime-sql/agroclima (`39644d87`), MIT, © Jaime Garcia.
The Python scorer in `src/agroclima_agent/risk.py` implements this file.
A language model must not change the cutoffs, the level, or the technician handoff.

Data Engineer, 2026-10-10 (SV). Scope: El Salvador, 7-day Open-Meteo forecast. No app code here.

## 1. Rules table
| # | Factor | Threshold | Effect on daily risk | Source |
|---|---|---|---|---|
| R1 | Germination temperature | Optimum 21–25 °C (Waller 1982, as cited by Avelino); optimum 22 °C (de Jong 1987) vs 24 °C (Rozo 2012); on leaves min ~12.5 °C, max ~32.5 °C; <15 °C hampers germination | +1 if ≥ 3 wet hours in 21–25 °C (opt_wet_h ≥ 3, see §2); 0 if all wet hours <15 °C or >30 °C | Avelino et al. 2015, *Food Security* 7:303–321, doi:10.1007/s12571-015-0446-9; Toniutti et al. 2017, *Front. Plant Sci.* 8:2025, doi:10.3389/fpls.2017.02025; U. Hawaii Crop Knowledge Master, http://www.extento.hawaii.edu/Kbase/Crop/Type/h_vasta.htm |
| R2 | Free water / leaf wetness | Spores germinate ONLY in free water (rain/heavy dew); infection needs ~24–48 h continuous free moisture (germination itself 2–5 h); high RH alone not enough | Main driver: +2 if proxy wet hours ≥ 6 in day (see note), +1 if 3–5 | Hawaii CKM (above, citing Nutman 1963; Kushalappa & Eskes 1989); Purdue CAPS pest sheet, https://caps.ceris.purdue.edu/wp-content/uploads/2025/07/Hemileia-vastatrix.pdf |
| R3 | Relative humidity as wetness proxy | Hours with RH ≥ 90 % ≈ leaf-wetness hours (best simple RH model; 87–92 % correct, needs local calibration) | Used to compute R2 wet hours | Sentelhas et al. 2008, *Agric. For. Meteorol.* 148:392–400, doi:10.1016/j.agrformet.2007.09.011 |
| R4 | Rain events | Rain supplies free water and splash/wind dispersal; epidemics track rainy season | +1 if daily precipitation_sum ≥ 1 mm or precipitation_probability_max ≥ 60 % | Hawaii CKM; Purdue CAPS (above) |
| R5 | Latency vs temperature | Latency optimum when daily max 22–28 °C; reduced diurnal range (warmer nights, cooler days) shortened latency in 2008–13 epidemics; latency 10–14 days infection→new spores | +1 if temperature_2m_max in 22–28 °C (diurnal range is context only, not scored) | Avelino et al. 2015 (above); Purdue CAPS (above) |
| R6 | Rain-free spread windows | Disease spread "usually limited to the rainy season"; incidence very low in dry periods | Day with 0 warm wet hours → bajo regardless of temperature or daily rain (see §2a) | Hawaii CKM (above) |
| R7 | Altitude (El Salvador) | No numeric altitude threshold sourced. Open-Meteo `elevation` downscales temperature; R1/R5 capture altitude via temperature | — (sin fuente for altitude bands) | sin fuente |

Note: the "≥6 / 3–5 wet hours" scoring bins are OUR engineering choice (proxy for the 24–48 h needed over consecutive days), not a published threshold.

## 2. Daily score recipe (deterministic)
Per local day (timezone=America/El_Salvador):
- wet_h = count of hours with relative_humidity_2m ≥ 90 OR precipitation ≥ 0.1 mm
- warm_wet_h = wet_h hours where 15 ≤ temperature_2m ≤ 30 (R1 bounds); opt_wet_h = those in 21–25 °C
- score = (warm_wet_h ≥ 6 ? 2 : warm_wet_h ≥ 3 ? 1 : 0) + (opt_wet_h ≥ 3 ? 1 : 0) + (rain day R4 ? 1 : 0) + (R5 latency band ? 1 : 0)
- Consecutive-day bonus: +1 if today has warm_wet_h ≥ 6 AND the previous calendar date is in the forecast and also had warm_wet_h ≥ 6 (24–48 h continuous moisture, R2). No bonus if that date is missing; day 1 of the strip never gets it
- warm_wet_h = 0 → **bajo** (R6). score 0–1 bajo, 2–3 medio, ≥4 alto.
Spanish reason (pick the top factor):
- alto: «Hojas mojadas muchas horas y clima tibio: la roya se pega fácil.»
- medio: «Humedad o lluvia algunas horas: riesgo moderado.»
- bajo (seco): «Día seco: la roya casi no avanza.» / bajo (frío/caliente): «Temperatura poco favorable para la roya.» / bajo (lluvia ≥ 1 mm, 0 wet hours): «Llueve, pero sin horas húmedas favorables a la roya» / bajo (score 0–1 with warm_wet_h > 0): «Pocas horas húmedas favorables; riesgo bajo de roya»
- A bajo day always uses a bajo sentence, never the medio one

## 2a. Edge cases (decided Oct 11)
- Bajo days always use a bajo sentence (never «…riesgo moderado.»). Score 0–1 with warm wet hours > 0 → «Pocas horas húmedas favorables; riesgo bajo de roya».
- Previous-day bonus: only if BOTH today and the previous calendar date (present in the forecast) have warm_wet_h ≥ 6; otherwise no bonus. Day 1 never gets it.
- Optimum temperature: ≥ 3 wet hours in 21–25 °C (recipe wins over the old "overlap" wording).
- R5: the diurnal-range (max−min) condition is dropped; only temperature_2m_max 22–28 °C scores.
- Daily precipitation_sum ≥ 1 mm with 0 wet hours → bajo, «Llueve, pero sin horas húmedas favorables a la roya».
- A day with missing hourly data (fewer than 24 hours) or a null in a required field (hourly temperature_2m, relative_humidity_2m, precipitation; daily temperature_2m_max, precipitation_sum, precipitation_probability_max) → «sin datos», no level. Hourly precipitation_probability is not required (spray window only).
- Any fetch failure, empty reply, missing timezone, or reply whose timezone ≠ America/El_Salvador → «pronóstico no disponible» for the whole strip, no levels.

## 3. Open-Meteo fields (verified at https://open-meteo.com/en/docs, 2026-10-10)
Endpoint `/v1/forecast`, `forecast_days=7` (default), `timezone=America/El_Salvador`, lat/lon of municipality (`elevation` optional, default 90 m DEM downscaling).
| Variable | Type | Unit | Rule |
|---|---|---|---|
| `temperature_2m` | hourly, instant | °C | R1 (warm/opt wet hours) |
| `relative_humidity_2m` | hourly, instant | % | R3 wetness proxy (≥90) |
| `dew_point_2m` | hourly, instant | °C | optional alt proxy: T − Td ≤ 2 °C (dew-point depression model in Sentelhas 2008; threshold not adopted, sin fuente) |
| `precipitation` | hourly, preceding-hour sum | mm | R2/R4 wet hours; spray window |
| `precipitation_probability` | hourly, preceding hour | % (>0.1 mm) | spray window |
| `temperature_2m_max`, `temperature_2m_min` | daily | °C | R5 (max only; min is display/context) |
| `precipitation_sum`, `precipitation_hours`, `precipitation_probability_max` | daily | mm / h / % | R4, UI text |

## 4. Dry spray window (research/extension, NOT label text)
- Systemic triazoles (tetraconazole, cyproconazole) kept rust control with simulated rain 30, 60, 120 min after spraying → need ≥ 2 h rain-free. Source: SciELO, *Arq. Inst. Biol.* "Avaliação da eficácia de fungicidas sistêmicos ... sob chuva simulada", https://www.scielo.br/j/aib/a/MYWBhSkVxnM3hKMJcfxPRgw/
- Copper (hydroxide; oxychloride + 0.75 % mineral oil) retained efficacy with rain at 120 and 480 min. Source: *J. Agric. Sci.* (CCSE) 11(6):329, "Drying Time of Systemic and Protectant Fungicides on Coffee Leaves Exposed to Artificial Rain", https://ccsenet.org/journal/index.php/jas/article/download/0/0/39268/40090
- App rule (conservative, our choice): next window = first daytime block with ≥ 4 consecutive hours precipitation < 0.1 mm AND precipitation_probability < 40 %, leaves not wet (RH < 90). The 4 h / 40 % values are sin fuente (safety margin over the 2 h finding). Always "siga la etiqueta del producto".

## 5. Plan values
| What | Dose | When | Source |
|---|---|---|---|
| Preventive control at start of rainy season, low incidence; cover leaf underside; alternate modes of action | — | Inicio de lluvias | ANACAFE (Guatemala) 2022, https://www.anacafe.org/uploads/file/4d9dbb854bf940159d4489c200dc44da/Prevencion-Roya-Cafeto-2022.pdf |
| Copper (cobre, hidróxido 50 WP) | 2.8 kg/mz | every 30 d, only if incidence < 5 % | ANACAFE/CEDICAFE trial, https://www.anacafe.org/bcms-media/Files/Download?id=654c4741-7618-41f7-92af-a9ba011d3632 |
| Triazol (epoxiconazol 12.5 SC) | 405 cc/mz | every 60 d | same + CEDICAFE bulletin, https://www.anacafe.org/uploads/file/89e5afde997541678dc415b7d44fb2d9/Boletin-CEDICAFE-RII-08.pdf |
| Triazol (ciproconazol 10 SL) / triazol+estrobilurina (ciproconazol+azoxistrobina) | 350 cc/mz | every 60 d | https://www.anacafe.org/bcms-media/Files/Download?id=cb69ac69-b0b8-48c1-ae06-a9ba011fab88 |
Caveat: these are Guatemalan (ANACAFE) research trial doses with brand products, not El Salvador guidance or labels. Recommend the app show class + "dosis según etiqueta / su agrónomo" and cite ANACAFE only as reference. 1 mz ≈ 0.7 ha.

## 6. Contacts
| Org | Phone | Web | Status |
|---|---|---|---|
| CENTA | (503) 2397-2200, oir@centa.gob.sv; Km 33½ Carretera a Santa Ana, Ciudad Arce | https://www.centa.gob.sv | VERIFIED on https://www.centa.gob.sv/directorio-2/ (2026-10-10) |

## 7. Caveats
1. RH ≥ 90 % proxy is uncalibrated for El Salvador coffee canopies (Sentelhas: local calibration needed); model RH at 2 m ≠ shaded leaf surface.
2. Weather favourability ≠ disease: inoculum, variety resistance (Catimor/Sarchimor), shade, nutrition and farm management (Avelino 2015) matter as much; the strip is "riesgo del clima", not a diagnosis.
3. Score bins and spray-window margins are engineering choices on top of cited biology; validate against ISC, CENTA and ANACAFE (Guatemala) before claiming accuracy.
