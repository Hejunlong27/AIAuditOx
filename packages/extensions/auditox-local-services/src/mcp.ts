/** Local Model Context Protocol surface for external audit agents. */
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { traceTool } from '@deepseek-ai/dsh-auditox-trace'

const DEFAULT_PORT = 11436
const MAX_REQUEST_BYTES = 2 * 1024 * 1024
const VERSION = '0.2.3-alpha.2'

type JsonRecord = Record<string, unknown>

export interface AuditOxMcpDependencies {
  harnessStatus: () => Promise<unknown>
  listSkills: () => Promise<unknown>
  readSkill: (id: string) => Promise<unknown>
  runtimeRequest: (path: string, init?: RequestInit) => Promise<unknown>
}

interface JsonRpcMessage {
  jsonrpc?: unknown
  id?: string | number | null
  method?: unknown
  params?: unknown
}

const TOOLS = [
  {
    name: 'auditox_harness_status',
    description: 'Return the local AuditOx Harness status, model gateway and skill warehouse status.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'auditox_skill_list',
    description: 'List AuditOx skills available from the local skill warehouse.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'auditox_skill_read',
    description: 'Read one AuditOx SKILL.md definition by skill id.',
    inputSchema: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'], additionalProperties: false },
  },
  {
    name: 'auditox_runtime_health',
    description: 'Check the integrated AuditOx Runtime and its local API.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'auditox_project_list',
    description: 'List AuditOx projects from the integrated local runtime.',
    inputSchema: { type: 'object', properties: {}, additionalProperties: false },
  },
  {
    name: 'auditox_workpaper_trace',
    description: 'Return task, plan, artifacts, approvals and trace records for a workpaper.',
    inputSchema: { type: 'object', properties: { task_id: { type: 'string' } }, required: ['task_id'], additionalProperties: false },
  },
  {
    name: 'auditox_export_workpaper',
    description: 'Generate a reviewable workpaper by task id.',
    inputSchema: {
      type: 'object',
      properties: { task_id: { type: 'string' }, prepared_by: { type: 'string' }, reviewer: { type: 'string' } },
      required: ['task_id', 'prepared_by'],
      additionalProperties: false,
    },
  },
  {
    name: 'auditox_guided_stage',
    description: 'Advance one guided audit thread stage through the integrated Runtime.',
    inputSchema: {
      type: 'object',
      properties: { thread_id: { type: 'string' }, stage_id: { type: 'string' }, instructions: { type: 'string' } },
      required: ['thread_id'],
      additionalProperties: false,
    },
  },
] as const

function record(value: unknown): JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value as JsonRecord : {}
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

async function executeTool(name: string, args: JsonRecord, deps: AuditOxMcpDependencies): Promise<unknown> {
  switch (name) {
    case 'auditox_harness_status':
      return await deps.harnessStatus()
    case 'auditox_skill_list':
      return await deps.listSkills()
    case 'auditox_skill_read':
      return await deps.readSkill(text(args.id))
    case 'auditox_runtime_health':
      return await deps.runtimeRequest('/api/health')
    case 'auditox_project_list':
      return await deps.runtimeRequest('/api/projects')
    case 'auditox_workpaper_trace': {
      const taskId = text(args.task_id)
      if (taskId === '') throw new Error('task_id is required')
      const encoded = encodeURIComponent(taskId)
      const [task, artifacts, approvals] = await Promise.all([
        deps.runtimeRequest(`/api/tasks/${encoded}`),
        deps.runtimeRequest(`/api/tasks/${encoded}/artifacts`),
        deps.runtimeRequest(`/api/tasks/${encoded}/approvals`),
      ])
      return { schema: 'auditox.workpaper-trace.v1', task, artifacts, approvals }
    }
    case 'auditox_export_workpaper': {
      const taskId = text(args.task_id)
      if (taskId === '') throw new Error('task_id is required')
      return await deps.runtimeRequest(`/api/tasks/${encodeURIComponent(taskId)}/workpaper`, {
        method: 'POST',
        body: JSON.stringify({ prepared_by: text(args.prepared_by), reviewer: text(args.reviewer) }),
      })
    }
    case 'auditox_guided_stage': {
      const threadId = text(args.thread_id)
      if (threadId === '') throw new Error('thread_id is required')
      return await deps.runtimeRequest(`/api/threads/${encodeURIComponent(threadId)}/guide/advance`, {
        method: 'POST',
        body: JSON.stringify({ stage_id: text(args.stage_id), instructions: text(args.instructions) }),
      })
    }
    default:
      throw new Error(`Unknown AuditOx MCP tool: ${name}`)
  }
}

async function callTool(name: string, args: JsonRecord, deps: AuditOxMcpDependencies): Promise<unknown> {
  return await traceTool({
    action: `mcp.${name}`,
    toolName: name,
    args,
    execute: async () => await executeTool(name, args, deps),
  })
}

function result(value: unknown) {
  return { content: [{ type: 'text', text: JSON.stringify(value, null, 2) }], structuredContent: record(value) }
}

/** Process one JSON-RPC request. Notifications return undefined. */
export async function handleAuditOxMcpMessage(message: JsonRpcMessage, deps: AuditOxMcpDependencies): Promise<object | undefined> {
  if (message.jsonrpc !== '2.0' || typeof message.method !== 'string') {
    return { jsonrpc: '2.0', id: message.id ?? null, error: { code: -32600, message: 'Invalid Request' } }
  }
  if (message.id === undefined) return undefined
  const id = message.id
  try {
    switch (message.method) {
      case 'initialize': {
        const requested = record(message.params).protocolVersion
        return {
          jsonrpc: '2.0',
          id,
          result: {
            protocolVersion: typeof requested === 'string' ? requested : '2025-03-26',
            capabilities: { tools: { listChanged: false } },
            serverInfo: { name: 'auditox-harness', version: VERSION },
            instructions: '审小牛AIAuditOx HARNESS exposes local audit skills, project runtime and traceable workpaper tools. All data remains local unless an external agent explicitly sends it elsewhere.',
          },
        }
      }
      case 'ping':
        return { jsonrpc: '2.0', id, result: {} }
      case 'tools/list':
        return { jsonrpc: '2.0', id, result: { tools: TOOLS } }
      case 'tools/call': {
        const params = record(message.params)
        const name = text(params.name)
        if (name === '') throw new Error('tools/call requires name')
        return { jsonrpc: '2.0', id, result: result(await callTool(name, record(params.arguments), deps)) }
      }
      default:
        return { jsonrpc: '2.0', id, error: { code: -32601, message: `Method not found: ${message.method}` } }
    }
  } catch (error) {
    return { jsonrpc: '2.0', id, error: { code: -32000, message: error instanceof Error ? error.message : String(error) } }
  }
}

async function body(req: IncomingMessage): Promise<JsonRpcMessage> {
  const chunks: Uint8Array[] = []
  let size = 0
  for await (const chunk of req) {
    const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    size += bytes.length
    if (size > MAX_REQUEST_BYTES) throw new Error('MCP request body is too large')
    chunks.push(new Uint8Array(bytes))
  }
  const parsed = JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error('MCP request must be a JSON object')
  return parsed
}

function reply(res: ServerResponse, status: number, value: unknown): void {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(value === undefined ? '' : JSON.stringify(value))
}

function authorized(req: IncomingMessage): boolean {
  const token = process.env.AUDITOX_MCP_TOKEN?.trim() ?? ''
  return token === '' || req.headers.authorization === `Bearer ${token}`
}

/** Start the loopback MCP endpoint at http://127.0.0.1:11436/mcp. */
export function startAuditOxMcpServer(
  deps: AuditOxMcpDependencies,
  port = Number(process.env.AUDITOX_MCP_PORT ?? DEFAULT_PORT),
): () => void {
  const server = createServer((req, res) => {
    void (async () => {
      if (req.method === 'GET' && req.url === '/health') {
        reply(res, 200, { ok: true, name: 'auditox-harness', version: VERSION, mcp: '/mcp' })
        return
      }
      if (req.url !== '/mcp') { reply(res, 404, { error: 'not found' }); return }
      if (req.method !== 'POST') { reply(res, 405, { error: 'POST required' }); return }
      if (!authorized(req)) { reply(res, 401, { error: 'unauthorized' }); return }
      const message = await body(req)
      const response = await handleAuditOxMcpMessage(message, deps)
      reply(res, 200, response)
    })().catch((error: unknown) => {
      reply(res, 400, {
        jsonrpc: '2.0',
        id: null,
        error: { code: -32700, message: error instanceof Error ? error.message : String(error) },
      })
    })
  })
  server.on('error', () => {})
  server.listen(port, '127.0.0.1')
  return () => { server.close() }
}
