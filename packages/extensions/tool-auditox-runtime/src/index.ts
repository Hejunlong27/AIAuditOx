/**
 * AuditOx Runtime bridge. The Python/FastAPI application remains the owner of
 * audit projects, source assets, evidence and generated workpapers; these tools
 * expose its local HTTP contract to the Harness model loop.
 */
import { readFile } from 'node:fs/promises'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'

export const name = 'tool-auditox-runtime'
export const inject = ['tools']

const BASE_URL = (process.env.AUDITOX_RUNTIME_URL ?? 'http://127.0.0.1:8765').replace(/\/$/, '')

interface JsonResult {
  status: number
  value: JsonValue
}

/** Render a stable text result for any AuditOx HTTP response. */
function renderJson(value: JsonValue): Array<{ type: 'text'; text: string }> {
  return [{ type: 'text', text: JSON.stringify(value, null, 2) }]
}

async function request(path: string, init?: RequestInit): Promise<JsonResult> {
  let response: Response
  try {
    const headers = new Headers(init?.headers)
    if (init?.body !== undefined && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    response = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  } catch (error) {
    throw new Error(
      `AuditOx Runtime is not reachable at ${BASE_URL}. Start it with: `
      + 'python -m api.main --port 8765',
      { cause: error },
    )
  }
  const text = await response.text()
  let value: JsonValue = text
  try {
    value = text.length === 0 ? null : JSON.parse(text) as JsonValue
  } catch {}
  if (!response.ok) {
    const detail = typeof value === 'object' && value !== null && 'detail' in value
      ? String((value as { detail: unknown }).detail)
      : text
    throw new Error(`AuditOx Runtime HTTP ${response.status}: ${detail}`)
  }
  return { status: response.status, value }
}

const objectOutput = {
  schema: { type: 'json' as const },
  render: (_args: unknown, value: JsonValue) => renderJson(value),
}

/** Register the AuditOx bridge tools. */
export function apply(ctx: Context): void {
  ctx.tools.register(defineTool({
    name: 'auditox_health',
    description: 'Check whether the local AuditOx Runtime and model configuration are available.',
    parameters: {},
    output: objectOutput,
    async execute() {
      return (await request('/api/health')).value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_list_projects',
    description: 'List local AuditOx audit projects visible to this machine.',
    parameters: {},
    output: {
      schema: { type: 'json' as const },
      render: (_args: unknown, value: JsonValue) => renderJson(value),
    },
    async execute() {
      return (await request('/api/projects')).value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_create_project',
    description: 'Create an AuditOx project for one audited entity and period.',
    parameters: {
      name: { type: 'string', required: true, description: 'Project name.' },
      client_label: { type: 'string', required: true, description: 'Audited entity full name.' },
      period: { type: 'string', required: true, description: 'Audit period, for example 2026 年度.' },
    },
    output: objectOutput,
    async execute(args) {
      const result = await request('/api/projects', {
        method: 'POST',
        body: JSON.stringify(args),
      })
      return result.value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_list_assets',
    description: 'List source files already registered in an AuditOx project.',
    parameters: {
      project_id: { type: 'string', required: true, description: 'AuditOx project id.' },
    },
    output: {
      schema: { type: 'json' as const },
      render: (_args: unknown, value: JsonValue) => renderJson(value),
    },
    async execute(args) {
      return (await request(`/api/projects/${encodeURIComponent(args.project_id)}/assets`)).value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_upload_asset',
    description: 'Register a local financial statement or ledger file in an AuditOx project.',
    parameters: {
      project_id: { type: 'string', required: true, description: 'AuditOx project id.' },
      logical_name: {
        type: 'string',
        required: true,
        description: 'Logical input key: financial_statement, trial_balance, general_ledger, supporting_docs or other.',
      },
      file_path: { type: 'string', required: true, description: 'Absolute local path readable by the Harness host.' },
    },
    output: objectOutput,
    async execute(args) {
      const bytes = await readFile(args.file_path)
      const filename = args.file_path.split(/[\\/]/).pop() ?? 'upload.bin'
      const query = new URLSearchParams({ logical_name: args.logical_name, filename })
      const result = await request(
        `/api/projects/${encodeURIComponent(args.project_id)}/assets?${query.toString()}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/octet-stream' },
          body: new Uint8Array(bytes),
        },
      )
      return result.value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_start_guided_thread',
    description: 'Create an AuditOx guided-audit conversation for a project.',
    parameters: {
      project_id: { type: 'string', required: true, description: 'AuditOx project id.' },
      title: { type: 'string', description: 'Optional work-line title.' },
    },
    output: objectOutput,
    async execute(args) {
      const result = await request('/api/threads', {
        method: 'POST',
        body: JSON.stringify({ project_id: args.project_id, mode: 'guided', title: args.title ?? '' }),
      })
      return result.value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_advance_guided_stage',
    description: 'Run the next or selected AuditOx guided-audit stage and return the generated review draft.',
    parameters: {
      thread_id: { type: 'string', required: true, description: 'AuditOx thread id.' },
      stage_id: {
        type: 'string',
        description: 'Optional stage id: financial_analysis, audit_plan, materiality, audit_procedures, walkthrough_controls, substantive_workpapers, missing_materials or review_pack.',
      },
      instructions: { type: 'string', description: 'Optional project-team instructions for this stage.' },
    },
    output: objectOutput,
    async execute(args) {
      const result = await request(`/api/threads/${encodeURIComponent(args.thread_id)}/guide/advance`, {
        method: 'POST',
        body: JSON.stringify({ stage_id: args.stage_id, instructions: args.instructions ?? '' }),
      })
      return result.value
    },
  }))
}
