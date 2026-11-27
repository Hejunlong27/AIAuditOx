# @deepseek-ai/dsh-tool-auditox-runtime

Model-facing tools for the local AuditOx Python Runtime.

The tools manage projects, source assets and guided-audit stages over the Runtime HTTP API. Set `AUDITOX_RUNTIME_URL` to override the default `http://127.0.0.1:8765`.

The bridge does not perform audit calculations itself and does not start the Python process.

## Known limitations

The Runtime must already be running, and tool output quality depends on the installed AuditOx Runtime version.