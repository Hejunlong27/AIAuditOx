import { describe, expect, it, vi } from 'vitest'

vi.mock('@deepseek-ai/dsh-auditox-trace', () => ({
  traceTool: async ({ execute }: { execute: () => Promise<unknown> }) => await execute(),
}))
import { handleAuditOxMcpMessage, type AuditOxMcpDependencies } from '../src/mcp.ts'

const deps: AuditOxMcpDependencies = {
  harnessStatus: vi.fn<() => Promise<unknown>>(async () => ({ name: 'auditox' })),
  listSkills: vi.fn<() => Promise<unknown>>(async () => ({ skills: [{ id: 'financial-statement-analysis' }] })),
  readSkill: vi.fn<(id: string) => Promise<unknown>>(async id => ({ id, content: '# Skill' })),
  runtimeRequest: vi.fn<(path: string, init?: RequestInit) => Promise<unknown>>(async () => ({ ok: true })),
}

describe('AuditOx MCP surface', () => {
  it('initializes with audit tools', async () => {
    const response = await handleAuditOxMcpMessage({
      jsonrpc: '2.0', id: 1, method: 'initialize', params: { protocolVersion: '2025-03-26' },
    }, deps)
    expect(response).toMatchObject({ id: 1, result: { capabilities: { tools: {} }, serverInfo: { name: 'auditox-harness' } } })
  })

  it('lists and calls an audit skill tool', async () => {
    const list = await handleAuditOxMcpMessage({ jsonrpc: '2.0', id: 2, method: 'tools/list' }, deps)
    const listed = list as { result: { tools: Array<{ name: string }> } }
    expect(listed.result.tools.some(tool => tool.name === 'auditox_skill_read')).toBe(true)
    const call = await handleAuditOxMcpMessage({
      jsonrpc: '2.0', id: 3, method: 'tools/call', params: { name: 'auditox_skill_read', arguments: { id: 'auditox-wp-standard' } },
    }, deps)
    expect(call).toMatchObject({ result: { content: [{ type: 'text' }] } })
    expect(deps.readSkill).toHaveBeenCalledWith('auditox-wp-standard')
  })
})
