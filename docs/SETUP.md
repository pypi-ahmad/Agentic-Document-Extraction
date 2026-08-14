# Setup

Requirements: Windows 11 or another supported Python/Node environment, Python 3.12, `uv`,
Node.js 20+, npm, and an OpenAI API key.

```powershell
git clone https://github.com/pypi-ahmad/Agentic-Document-Extraction.git
cd Agentic-Document-Extraction
uv sync --locked
cd frontend
npm ci
cd ..
$env:OPENAI_API_KEY = "your-key"
./scripts/dev.ps1 -OpenBrowser
```

For persistent Windows environment variables, set them in the user environment and open a
new terminal. `OPENAI_BASE_URL` defaults to `https://api.openai.com/v1`.

No GPU, Docker service, local model, or durable storage service is required.
