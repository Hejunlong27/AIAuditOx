import { useEffect, useState, type ReactNode } from 'react'
import { apiJson, type SystemState } from './api.ts'
import css from './Workbench.module.css'

/** Compact local inference switch shown on the blank home and in Session headers. */
export function LocalModelToggle(): ReactNode {
  const [system, setSystem] = useState<SystemState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = async (): Promise<void> => {
    try {
      setSystem(await apiJson<SystemState>('/auditox/api/system'))
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  useEffect(() => {
    void refresh()
    const timer = setInterval(() => { void refresh() }, 5000)
    return () =>{  clearInterval(timer) }
  }, [])

  const toggle = async (): Promise<void> => {
    if (busy) return
    if (!system?.ollama.installed) {
      window.open('https://ollama.com/download', '_blank', 'noopener,noreferrer')
      return
    }
    setBusy(true)
    try {
      await apiJson(system.ollama.running ? '/auditox/api/models/stop' : '/auditox/api/models/start', { method: 'POST' })
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy(false)
    }
  }

  const state = !system?.ollama.installed ? '未安装' : system.ollama.running ? '运行中' : '已关闭'
  return (
    <button
      type="button"
      className={css.modelToggle}
      data-running={system?.ollama.running === true}
      onClick={() => { void toggle() }}
      title={error || (system?.ollama.installed ? '启动或关闭本地大模型服务' : '安装 Ollama 后启用本地模型')}
      disabled={busy}
    >
      <span className={css.modelDot} />
      <span>本地模型 {busy ? '切换中…' : state}</span>
      <span className={css.modelChevron}>{system?.ollama.running ? '关闭' : '启动'}</span>
    </button>
  )
}
