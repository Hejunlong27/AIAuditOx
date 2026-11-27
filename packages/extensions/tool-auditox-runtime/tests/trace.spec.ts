import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'

let dir: string | undefined

afterEach(async () => {
  vi.unstubAllEnvs()
  if (dir !== undefined) await rm(dir, { recursive: true, force: true })
  dir = undefined
})

describe('workpaper trace ledger', () => {
  it('writes a valid hash chain and filters by task', async () => {
    dir = await mkdtemp(path.join(tmpdir(), 'auditox-trace-'))
    vi.stubEnv('DSH_HOME', dir)
    vi.resetModules()
    const { listTraces, traceTool } = await import('../../auditox-trace/src/index.ts')
    await traceTool({
      action: 'workpaper.export', toolName: 'auditox_export_workpaper', args: { task_id: 'T1', prepared_by: 'A' },
      execute: async () => ({ path: 'wp.xlsx', sha256: 'abc' }),
    })
    await traceTool({
      action: 'task.run', toolName: 'auditox_run_task', args: { task_id: 'T2' }, execute: async () => ({ ok: true }),
    })
    const all = await listTraces()
    expect(all.chainValid).toBe(true)
    expect(all.total).toBe(2)
    const task = await listTraces({ task_id: 'T1' })
    expect(task.records).toHaveLength(1)
    expect(task.records[0]).toMatchObject({ toolName: 'auditox_export_workpaper', taskId: 'T1' })
  })
})
