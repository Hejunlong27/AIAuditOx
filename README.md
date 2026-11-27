# AuditOx AIAuditOx HARNESS

> Every audit procedure can become a Skill.

AuditOx is a local-first AI audit harness that separates audit procedure logic from deterministic execution tools, project data and review evidence. It works as an auditor desktop workspace and as a local audit capability layer for other agents.

## Architecture

| Layer | Responsibility |
| --- | --- |
| **Skill** | Defines what an audit procedure must do: objective, inputs, steps, judgments, evidence and workpaper structure. |
| **Tools** | Execute concrete work: parsing, database operations, deterministic calculations, OCR, image processing, document generation and model calls. |
| **Audit Runtime** | Owns projects, ledgers, tasks, plans, evidence, approvals, workpapers and revisions. |
| **Trace Ledger** | Appends a hash-chained JSONL record for agent and tool execution. |
| **MCP** | Exposes local audit capabilities to other agents and orchestration systems. |

## Included

- Guided and conversational audit workflows.
- Local model detection, Ollama lifecycle, custom OpenAI-compatible endpoints and GGUF import.
- Local SkillHub browsing, installation and `SKILL.md` inspection.
- Project, asset, task, approval, workpaper and artifact tools.
- Workpaper evidence sheets, revision sheets and SHA-256 artifact identity.
- A loopback MCP endpoint at `http://127.0.0.1:11436/mcp`.

## Start

```powershell
cd auditox
.\build.ps1
.\run.ps1
```

The previous runtime remains available on the GitHub branch `archive/legacy-runtime-92e03237` and is connected through the Runtime bridge rather than duplicated into the new product surface.

## Documentation

- [Chinese README](./README.zh.md)
- [Skill and tool architecture](./auditox/SKILL-TOOL-ARCHITECTURE.zh.md)
- [MCP endpoint](./auditox/MCP.zh.md)

## License

The original root [LICENSE](./LICENSE) is retained unchanged. Upstream open-source attribution remains limited to the license, third-party notices and acknowledgements.
