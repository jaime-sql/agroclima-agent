from pathlib import Path


def test_deploy_workflow_publishes_the_dockerfile_to_cloud_run():
    text = Path(".github/workflows/deploy.yml").read_text(encoding="utf-8")
    trigger = text.split("jobs:", 1)[0]
    assert "workflow_dispatch:" in trigger
    assert "push:" not in trigger
    for snippet in (
        "databank-sv-123456",
        "gcloud projects undelete databank-sv-123456",
        "us-central1",
        "agroclima-agent",
        "google-github-actions/auth@",
        "credentials_json: ${{ secrets.GCP_SA_KEY_JSON }}",
        "NEBIUS_API_KEY",
        "TAVILY_API_KEY",
        "https://api.tokenfactory.nebius.com/v1",
        "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B",
        "nvidia/nemotron-3-super-120b-a12b",
        "nvidia/Nemotron-3.5-Super-VL",
        "AGROCLIMA_HOST",
        "0.0.0.0",
        "--allow-unauthenticated",
        "--source=.",
        "--command=python",
        "--args=-m,agroclima_agent",
        "/api/health",
        "/api/run",
        "nemotron",
    ):
        assert snippet in text, snippet
    assert "private_key" not in text
    assert "sk-" not in text
    assert "tvly-" not in text
    assert "TECHNICIAN_WHATSAPP:" not in text
