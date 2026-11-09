This repository contains two independent Windows x64 desktop tools and a local training website.
Read README_RU.md and docs/PROJECT_STATE_RU.md before changing behavior.
Never commit API keys, pairing codes, config.local.json, environment secrets, reports or user screenshots.
No live OpenAI validation has been performed without an authorized funded key. Mocked API tests are not live proof.
Use the official OpenAI Responses API, HTTPS certificate validation, structured output and model-specific parameters.
Keep Gemini and exact graph solvers. Do not claim general OES compatibility, guaranteed correctness or undetectability.
Proctor Lab intentionally flags ScreenHelper and screen capture processes. No process-hiding/rootkit capability is implemented.
Run the relevant offline tests; do not send desktop screenshots or make paid calls without the user's authorization.
The release folder is generated and ignored; publish its binaries as release assets, not source commits.
Build-Release.ps1 rebuilds from source. Never copy private installed configurations into portable archives.
Screen Helper 8.4 also supports a shared cloud gateway. Its provider key is intentionally absent and SERVICE_ENABLED=false until the owner sets a key through approved Sites runtime secret tools. Never embed provider keys or platform service-access tokens into the desktop ZIP.
cloud-gateway/ is a sanitized source mirror. Read docs/CLOUD_OWNER_RU.md, open the owning Sites checkout through its source workflow before deployment, and keep its existing Site ID/audience. Run scripts/sync_cloud_contract.py --check to prevent schema drift. Do not reset quota counters or raise shared limits without owner authorization.
