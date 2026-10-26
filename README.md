# LightTry

**Explore new lighting for a photograph, without rebuilding the scene.**

LightTry is an interactive photo-relighting workbench built around NVIDIA Cosmos
and Nemotron, with GPU execution on Nebius. Describe a lighting idea, refine it
with visual controls, and compare the result with the original.

## What you can do

- Upload a photo and build reusable lighting schemes.
- Adjust environment lighting, intensity, direction, and local light zones.
- Ask the AI assistant for lighting suggestions; review parameters before applying them.
- Generate relit images with an explicitly configured GPU worker, then compare and download results.
- Use the interface in English or Chinese.

## Run locally

Use Python 3.11+ for the CPU web service. No frontend build is required.
The following PowerShell commands start a local-only workspace without cloud credentials:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-cpu.txt
$env:LIGHTTRY_ACCESS_KEY = .venv/Scripts/python -c "import secrets; print(secrets.token_urlsafe(32))"
Write-Host "Local access key: $env:LIGHTTRY_ACCESS_KEY"
.venv/Scripts/python -X utf8 -B start.py --service --listen-host 127.0.0.1 --public-origin http://127.0.0.1:8080 --data-root "$env:LOCALAPPDATA/LightTry"
```

Open **http://127.0.0.1:8080/login** and sign in with the key printed in your terminal.
Keep it private; do not share or commit it.
Local data is stored outside the source tree in `%LOCALAPPDATA%/LightTry`.
Upload your own photo; sample photos and model weights are not bundled.

## A quick walkthrough

1. Choose **English** in the language selector and upload a photo.
2. Create a scheme and adjust its environment or light zones.
3. If an AI provider is configured, request a suggestion and explicitly apply the proposed parameters.
4. If a GPU session is configured and ready, generate, compare, and download the relit image.

**The CPU-only launch supports the workspace, not model inference.** AI chat and
GPU generation require separate private configuration and authorization. They are
disabled by default; a running web page does not mean a GPU or model is ready.

## Architecture

`Browser -> Python CPU service -> authenticated GPU worker -> Cosmos inverse / forward inference`

- `start.py` is the single entry point; `project/web/` is the only frontend.
- `project/` contains the application, lighting editor, AI integration, and task handling.
- `cloud/`, `config/`, and `deploy/` provide cloud adapters and deployment templates.
- [Execution safety](docs/EXECUTION_FLOW.md) and [GPU transport](deploy/DIRECT_HTTPS.md) cover operator setup.

## Scope

`master` is the concise judging branch; `dev` retains development tools, tests,
and historical records. This branch does not bundle credentials, user photos,
model weights, experiment logs, or prebuilt container archives. Deployment and
model availability depend on the target environment; relighting quality must be
assessed from actual generated images, not service health or mock results.

Cosmos-derived code is covered by [its upstream license](third_party/Cosmos-LICENSE).
Model weights and external assets remain subject to their respective licenses.
