/** Append-only, tamper-evident AuditOx tool trace ledger. */
import { createHash, randomUUID } from 'node:crypto'
import { appendFile, mkdir, readFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

const DSH_HOME = process.env.DSH_HOME ?? path.join(os.homedir(), '.dsh')
const TRACE_FILE = process.env.AUDITOX_TRACE_FILE ?? path.join(DSH_HOME, 'auditox-traces', 'workpapers.jsonl')
const MAX_LIST = 500
let queue: Promise<void> = Promise.resolve()

export interface AuditTraceRecord {
  schema: 'auditox.trace.v1'
  traceId: string
  occurredAt: string
  action: string
  actor: 'agent'
  status: 'success' | 'error'
  projectId?: string | undefined
  taskId?: string | undefined
  skillId?: string | undefined
  toolName: string
  inputHash: string
  outputHash?: string | undefined
  error?: string | undefined
  previousHash: string
  recordHash: string
}

function stable(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value)
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`
  const record = value as Record<string, unknown>
  return `{${Object.keys(record).filter(key => record[key] !== undefined).sort().map(key => `${JSON.stringify(key)}:${stable(record[key])}`).join(',')}}`
}

function digest(value: unknown): string {
  return createHash('sha256').update(stable(value)).digest('hex')
}

function summary(args: Record<string, unknown>): Record<string, unknown> {
  const result: Record<string, unknown> = {}
  for (const key of ['project_id', 'task_id', 'thread_id', 'approval_id', 'skill_id', 'stage_id', 'logical_name', 'prepared_by', 'reviewer']) {
    if (args[key] !== undefined) result[key] = args[key]
  }
  if (typeof args.file_path === 'string') result.file_name = path.basename(args.file_path)
  return result
}

async function readRecords(): Promise<AuditTraceRecord[]> {
  try {
    const text = await readFile(TRACE_FILE, 'utf8')
    return text.split(/\r?\n/u).filter(Boolean).map(line => JSON.parse(line) as AuditTraceRecord)
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return []
    throw error
  }
}

async function append(input: {
  action: string
  toolName: string
  args: Record<string, unknown>
  status: 'success' | 'error'
  result?: unknown
  error?: unknown
}): Promise<void> {
  await mkdir(path.dirname(TRACE_FILE), { recursive: true, mode: 0o700 })
  const records = await readRecords()
  const previousHash = records.at(-1)?.recordHash ?? 'GENESIS'
  const partial = {
    schema: 'auditox.trace.v1' as const,
    traceId: `TRACE-${randomUUID()}`,
    occurredAt: new Date().toISOString(),
    action: input.action,
    actor: 'agent' as const,
    status: input.status,
    projectId: typeof input.args.project_id === 'string' ? input.args.project_id : undefined,
    taskId: typeof input.args.task_id === 'string' ? input.args.task_id : undefined,
    skillId: typeof input.args.skill_id === 'string' ? input.args.skill_id : undefined,
    toolName: input.toolName,
    inputHash: digest({ args: summary(input.args), action: input.action }),
    ...(input.status === 'success' ? { outputHash: digest(input.result) } : {}),
    ...(input.status === 'error' ? { error: input.error instanceof Error ? input.error.message : String(input.error) } : {}),
    previousHash,
  }
  const record: AuditTraceRecord = { ...partial, recordHash: digest(partial) }
  await appendFile(TRACE_FILE, `${JSON.stringify(record)}\n`, { encoding: 'utf8', mode: 0o600 })
}

/** Record one tool execution in the append-only ledger. */
export function traceTool<T>(options: {
  action: string
  toolName: string
  args: Record<string, unknown>
  execute: () => Promise<T>
}): Promise<T> {
  const run = async (): Promise<T> => {
    try {
      const result = await options.execute()
      await append({ action: options.action, toolName: options.toolName, args: options.args, status: 'success', result })
      return result
    } catch (error) {
      await append({ action: options.action, toolName: options.toolName, args: options.args, status: 'error', error })
      throw error
    }
  }
  const current = queue.then(run, run)
  queue = current.then(() => undefined, () => undefined)
  return current
}

/** Return recent trace records after verifying their hash chain. */
export async function listTraces(filter: { project_id?: string; task_id?: string; limit?: number } = {}) {
  const records = await readRecords()
  let head = 'GENESIS'
  let chainValid = true
  for (const record of records) {
    const { recordHash, ...partial } = record
    if (record.previousHash !== head || digest(partial) !== recordHash) chainValid = false
    head = recordHash
  }
  const limit = Math.max(1, Math.min(MAX_LIST, filter.limit ?? 100))
  const filtered = records.filter(record =>
    (filter.project_id === undefined || record.projectId === filter.project_id)
    && (filter.task_id === undefined || record.taskId === filter.task_id))
  return {
    schema: 'auditox.trace-list.v1',
    file: TRACE_FILE,
    chainValid,
    total: filtered.length,
    records: filtered.slice(-limit),
  }
}
