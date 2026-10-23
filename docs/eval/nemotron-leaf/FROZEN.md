# FROZEN before test (written Fri Oct 23 2026 00:19 SV, UTC-6; test set not touched by this pipeline yet)
Selected prompt: v1 (val binary macro-F1 0.919; v2 0.892; v3 0.784; n=253 each, 0 abstentions).
frozen_config.json sha256: d0c2017aef15870923f5323298bcec04e8ffa35b7d7634d4c01f8c62959a5f87
run.py sha256: cc054ce4311680a4df895fe0e05088884c7e69925416b65275452d355b7dab9f
Test list sha256 to verify before the run: c9b88e6b21cd23953f6c8dac63f8244119ca2b2930c6c7018fa2f3c8c31c6895
Deviation logged: the val images (253) were missing locally (fetch.py only pulled train+test); fetched from the same lara2018 GitHub mirror before the val run.
Deviation logged: the model reasons by default (smoke call hit max_tokens with empty content); reasoning disabled via chat_template_kwargs, per PLAN's "reasoning off".
