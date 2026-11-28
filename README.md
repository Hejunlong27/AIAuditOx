# AuditOx AIAuditOx HARNESS

> Every audit procedure can become a Skill.

AuditOx AIAuditOx HARNESS is a local-first AI audit harness for audit engagement teams. It combines audit procedure logic, deterministic execution tools, project data, evidence and review traceability in one workspace. It is both an auditor desktop workspace and a local audit capability layer for other agents.

## Why AuditOx

Traditional audit software often binds procedure logic, data processing and UI into one monolith. AuditOx separates the responsibilities:

- **Skill** defines what an audit procedure must do.
- **Tools** perform concrete execution.
- **Audit Runtime** owns projects, tasks, evidence and workpapers.
- **Trace Ledger** records a tamper-evident execution chain.
- **MCP** exposes the local audit capability to other agents.

This lets a new audit procedure start as a Skill and reuse existing deterministic tools instead of rebuilding the whole workflow.

## Architecture

```text
Financial statements / ledgers / invoices / contracts / source files
                                  │
                                  ▼
             Skill: objective, inputs, logic, evidence, workpaper contract
                                  │
                                  ▼
             Agent: select Skill, orchestrate stages, request human review
                                  │
                                  ▼
             Tools: parsing, database, calculation, OCR, image, documents, models
                                  │
                                  ▼
             Audit Runtime: projects, tasks, approvals, workpapers, revisions
                                  │
                                  ▼
             Trace Ledger: input digest, output digest, hash chain
                                  │
                                  ├── Human review and sign-off
                                  └── MCP for other agents and orchestration systems
```

## Included

### Audit workflows

- Guided audit: statements and ledger data → audit plan → materiality → procedures → walkthrough and controls → substantive workpapers → missing materials → review pack.
- Conversational audit for risks, questions, evidence gaps and review findings.
- Audit dossier with guided stages and work boundaries.

### Skill center

- Local SkillHub mirror browsing;
- search, category filtering and `SKILL.md` inspection;
- install and uninstall skills into the local Harness skill directory;
- skills remain a separate, versioned fact source.

### Local models

- CPU, memory, disk and GPU detection;
- Ollama installation and status detection;
- one-click local model start/stop;
- hardware-aware model recommendations;
- custom OpenAI-compatible endpoint, model name and optional API key;
- local model gateway for the agent;
- GGUF upload and local-path import.

### Audit tools

- project, source asset and task management;
- deterministic audit task execution;
- human approvals and review decisions;
- workpaper export;
- artifact, evidence and revision queries;
- workpaper trace queries.

### Traceability

A workpaper contains procedure details, evidence, revision records, preparer/reviewer and SHA-256. The Harness also writes an append-only JSONL trace ledger containing project/task/tool identity, input and output digests, status, previous hash and record hash.

The current ledger is tamper-evident, not an external notarization, trusted timestamp or WORM archive.

## MCP endpoint

Default endpoint:

```text
http://127.0.0.1:11436/mcp
```

Available tools include Harness status, skill listing/reading, Runtime health, project listing, workpaper trace, workpaper export and guided-stage execution.

See [auditox/MCP.zh.md](./auditox/MCP.zh.md).

## Quick start

### Requirements

- Windows 10/11, macOS or Linux;
- Node.js `^24.22.3` or `>=26.13.1`;
- pnpm `11.28.5`;
- a Python environment for the legacy AuditOx Runtime (default sibling `../agent-runtime`).

```powershell
cd auditox
.\build.ps1
.\run.ps1
```

Default services:

```text
UI:             http://127.0.0.1:3080
Audit Runtime:  http://127.0.0.1:8765
Model gateway:  http://127.0.0.1:11435/v1
MCP:            http://127.0.0.1:11436/mcp
```

### Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `AUDITOX_RUNTIME_URL` | Legacy Audit Runtime URL | `http://127.0.0.1:8765` |
| `AUDITOX_SKILL_LIBRARY` | Skill mirror directory | `../skill-library` |
| `AUDITOX_MCP_PORT` | MCP port | `11436` |
| `AUDITOX_MCP_TOKEN` | Optional MCP Bearer Token | empty |
| `AUDITOX_TRACE_FILE` | Trace ledger file path | `$DSH_HOME/auditox-traces/workpapers.jsonl` |
| `AUDITOX_MODEL_GATEWAY_PORT` | Local model gateway port | `11435` |

## Repository layout

```text
auditox/                          Product configuration and operating docs
packages/client/ui-brand-auditox/ Brand, website palette, home and audit dossier
packages/client/ui-auditox-workbench/ Local models and SkillHub UI
packages/extensions/tool-auditox-runtime/ Runtime bridge and workpaper trace tools
packages/extensions/auditox-local-services/ Local model, SkillHub and MCP service
packages/extensions/auditox-trace/ Shared append-only trace ledger
```

## Legacy runtime

The previous implementation is preserved on:

```text
archive/legacy-runtime-92e03237
```

It remains connected through the Runtime bridge rather than being duplicated into the new product layer.

## Development

```powershell
npx pnpm@11.28.5 run build
npx pnpm@11.28.5 run typecheck
npx pnpm@11.28.5 exec vitest run `
  packages/extensions/auditox-local-services/tests/mcp.spec.ts `
  packages/extensions/tool-auditox-runtime/tests/trace.spec.ts
```

## Security and data boundaries

- Customer data stays on the local machine by default.
- Deterministic tools own calculations, reconciliations, sampling and index numbers.
- Model output is a draft, never a substitute for source evidence, audit judgment or sign-off.
- MCP binds to loopback by default; use `AUDITOX_MCP_TOKEN` when appropriate.
- Cloud models and external MCP clients require explicit user configuration.
- Never commit customer data, secrets or sensitive workpapers to Git.

## Documentation

- [Chinese README](./README.zh.md)
- [Skill × Tool architecture](./auditox/SKILL-TOOL-ARCHITECTURE.zh.md)
- [Financial data package architecture](./auditox/DATA-PACKAGE-ARCHITECTURE.zh.md)
- [MCP endpoint](./auditox/MCP.zh.md)
- [Third-party notices](./THIRD_PARTY_NOTICES.md)
- [Upstream acknowledgements](./ACKNOWLEDGEMENTS.md)

## License

This repository uses the [AIAuditOx Non-Commercial License 1.0](./LICENSE):

- personal study, teaching/research and internal audit use are permitted;
- modification and redistribution with attribution and the same license are permitted;
- commercial use, resale, removal of attribution and false origin claims are prohibited;
- commercial licensing requires a separate agreement with the author.

This is a **source-available** license, not an OSI-approved open-source license. Upstream third-party components retain their own licenses; see [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
