/**
 * AuditOx Runtime bridge. The local AuditOx Runtime remains the owner of
 * projects, source assets, evidence and generated workpapers. Every bridge
 * invocation also enters the append-only workpaper trace ledger.
 */
import { readFile } from 'node:fs/promises'
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { JsonValue } from '@deepseek-ai/dsh-util-values'
import { listTraces, traceTool } from '@deepseek-ai/dsh-auditox-trace'

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
      `AuditOx Runtime is not reachable at ${BASE_URL}. Start it with:`
      + ' auditox/bootstrap-legacy-runtime.ps1 or the configured AuditOx Runtime.',
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

const traced = <T>(action: string, toolName: string, args: Record<string, unknown>, execute: () => Promise<T>) =>
  traceTool({ action, toolName, args, execute })

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
    output: objectOutput,
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
      return traced('project.create', 'auditox_create_project', args, async () =>
        (await request('/api/projects', { method: 'POST', body: JSON.stringify(args) })).value)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_list_assets',
    description: 'List source files already registered in an AuditOx project.',
    parameters: {
      project_id: { type: 'string', required: true, description: 'AuditOx project id.' },
    },
    output: objectOutput,
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
      return traced('asset.register', 'auditox_upload_asset', args, async () => {
        const bytes = await readFile(args.file_path)
        const filename = args.file_path.split(/[\\/]/).pop() ?? 'upload.bin'
        const query = new URLSearchParams({ logical_name: args.logical_name, filename })
        return (await request(
          `/api/projects/${encodeURIComponent(args.project_id)}/assets?${query.toString()}`,
          { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: new Uint8Array(bytes) },
        )).value
      })
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_list_tasks',
    description: 'List audit tasks in a project, including status and selected skill.',
    parameters: {
      project_id: { type: 'string', required: true, description: 'AuditOx project id.' },
    },
    output: objectOutput,
    async execute(args) {
      return (await request(`/api/projects/${encodeURIComponent(args.project_id)}/tasks`)).value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_run_task',
    description: 'Execute one audit task through its skill-defined deterministic procedure.',
    parameters: {
      task_id: { type: 'string', required: true, description: 'Audit task id.' },
    },
    output: objectOutput,
    async execute(args) {
      return traced('task.run', 'auditox_run_task', args, async () =>
        (await request(`/api/tasks/${encodeURIComponent(args.task_id)}/run`, { method: 'POST' })).value)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_list_artifacts',
    description: 'List generated artifacts and their SHA-256 identities for a task.',
    parameters: {
      task_id: { type: 'string', required: true, description: 'Audit task id.' },
    },
    output: objectOutput,
    async execute(args) {
      return (await request(`/api/tasks/${encodeURIComponent(args.task_id)}/artifacts`)).value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_list_approvals',
    description: 'List human-review approvals and material submitted for a task.',
    parameters: {
      task_id: { type: 'string', required: true, description: 'Audit task id.' },
    },
    output: objectOutput,
    async execute(args) {
      return (await request(`/api/tasks/${encodeURIComponent(args.task_id)}/approvals`)).value
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_decide_approval',
    description: 'Record a reviewer decision for a pending audit procedure approval.',
    parameters: {
      approval_id: { type: 'string', required: true, description: 'Approval id.' },
      approved: { type: 'boolean', required: true, description: 'Reviewer decision.' },
      actor: { type: 'string', required: true, description: 'Reviewer name or identity.' },
      comment: { type: 'string', description: 'Reviewer comment.' },
    },
    output: objectOutput,
    async execute(args) {
      return traced('approval.decide', 'auditox_decide_approval', args, async () =>
        (await request(`/api/approvals/${encodeURIComponent(args.approval_id)}/decide`, {
          method: 'POST',
          body: JSON.stringify({ approved: args.approved, actor: args.actor, comment: args.comment ?? '' }),
        })).value)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_export_workpaper',
    description: 'Generate the reviewable workpaper and record its artifact hash in the trace ledger.',
    parameters: {
      task_id: { type: 'string', required: true, description: 'Audit task id.' },
      prepared_by: { type: 'string', required: true, description: 'Preparer name.' },
      reviewer: { type: 'string', description: 'Reviewer name, if assigned.' },
    },
    output: objectOutput,
    async execute(args) {
      return traced('workpaper.export', 'auditox_export_workpaper', args, async () =>
        (await request(`/api/tasks/${encodeURIComponent(args.task_id)}/workpaper`, {
          method: 'POST',
          body: JSON.stringify({ prepared_by: args.prepared_by, reviewer: args.reviewer ?? '' }),
        })).value)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_workpaper_trace',
    description: 'Return the task, plan, artifacts, approvals and local trace ledger for one workpaper.',
    parameters: {
      task_id: { type: 'string', required: true, description: 'Audit task id.' },
    },
    output: objectOutput,
    async execute(args) {
      const [task, artifacts, approvals, traces] = await Promise.all([
        request(`/api/tasks/${encodeURIComponent(args.task_id)}`),
        request(`/api/tasks/${encodeURIComponent(args.task_id)}/artifacts`),
        request(`/api/tasks/${encodeURIComponent(args.task_id)}/approvals`),
        listTraces({ task_id: args.task_id, limit: 100 }),
      ])
      return {
        schema: 'auditox.workpaper-trace-bundle.v1',
        task: task.value,
        artifacts: artifacts.value,
        approvals: approvals.value,
        localTrace: traces,
      } as unknown as JsonValue
    },
  }))

  ctx.tools.register(defineTool({
    name: 'auditox_list_workpaper_traces',
    description: 'List tamper-evident local tool traces, optionally scoped to one project or task.',
    parameters: {
      project_id: { type: 'string', description: 'Optional project id.' },
      task_id: { type: 'string', description: 'Optional task id.' },
      limit: { type: 'number', description: 'Maximum records to return (1-500).' },
    },
    output: objectOutput,
    async execute(args) {
      return await listTraces(args) as unknown as JsonValue
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
      return traced('thread.guided.start', 'auditox_start_guided_thread', args, async () =>
        (await request('/api/threads', {
          method: 'POST',
          body: JSON.stringify({ project_id: args.project_id, mode: 'guided', title: args.title ?? '' }),
        })).value)
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
      return traced('thread.guided.advance', 'auditox_advance_guided_stage', args, async () =>
        (await request(`/api/threads/${encodeURIComponent(args.thread_id)}/guide/advance`, {
          method: 'POST',
          body: JSON.stringify({ stage_id: args.stage_id, instructions: args.instructions ?? '' }),
        })).value)
    },
  }))
}
