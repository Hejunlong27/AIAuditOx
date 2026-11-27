import { useEffect, useState, type ReactNode } from 'react'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { apiJson, apiUpload, type SystemState } from './api.ts'
import css from './Workbench.module.css'

type ConfigResult = {
  ok: boolean
  config: SystemState['config']
  connection: SystemState['connection']
}

/** AuditOx local model setup, connection, import and runtime controls. */
export function LocalModelsPanel(_props: PropsRuntime<'main'>): ReactNode {
  const [system, setSystem] = useState<SystemState | null>(null)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [draftBaseUrl, setDraftBaseUrl] = useState('')
  const [draftApiKey, setDraftApiKey] = useState('')
  const [draftModel, setDraftModel] = useState('')
  const [testReply, setTestReply] = useState('')
  const [importName, setImportName] = useState('')
  const [importPath, setImportPath] = useState('')
  const [file, setFile] = useState<File | null>(null)

  const refresh = async (): Promise<void> => {
    try {
      const value = await apiJson<SystemState>('/auditox/api/system')
      setSystem(value)
      setDraftBaseUrl(value.config.baseUrl)
      setDraftModel(value.config.activeModel)
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  useEffect(() => { void refresh() }, [])

  const saveConfig = async (): Promise<void> => {
    if (busy) return
    setBusy('config')
    setMessage('')
    setError('')
    try {
      const result = await apiJson<ConfigResult>('/auditox/api/config', {
        method: 'POST',
        body: JSON.stringify({
          baseUrl: draftBaseUrl,
          activeModel: draftModel,
          ...draftApiKey === '' ? {} : { apiKey: draftApiKey },
        }),
      })
      setDraftApiKey('')
      setMessage(result.connection.reachable ? '模型服务连接成功' : '配置已保存，服务暂不可达')
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy('')
    }
  }

  const testCall = async (): Promise<void> => {
    if (busy) return
    setBusy('test')
    setMessage('')
    setError('')
    setTestReply('')
    try {
      const result = await apiJson<{ ok: boolean; text: string }>('/auditox/api/models/test-chat', { method: 'POST' })
      setTestReply(result.text || '模型已连接')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy('')
    }
  }

  const installOllama = async (): Promise<void> => {
    if (busy) return
    setBusy('install')
    setMessage('正在安装 Ollama，可能需要数分钟…')
    setError('')
    try {
      const result = await apiJson<{ ok: boolean; log: string }>('/auditox/api/ollama/install', { method: 'POST' })
      setMessage(result.ok ? 'Ollama 已安装并启动' : result.log)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy('')
    }
  }

  const toggleServer = async (): Promise<void> => {
    if (!system || busy) return
    if (system.connection.protocol === 'openai' && system.connection.reachable) return
    if (!system.ollama.installed) {
      await installOllama()
      return
    }
    setBusy('server')
    setMessage('')
    try {
      await apiJson(system.ollama.reachable ? '/auditox/api/models/stop' : '/auditox/api/models/start', { method: 'POST' })
      setMessage(system.ollama.reachable ? '模型服务已关闭' : '模型服务已启动')
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy('')
    }
  }

  const installCatalogModel = async (name: string): Promise<void> => {
    if (busy) return
    setBusy(name)
    setMessage(`正在下载 ${name}…`)
    setError('')
    try {
      const result = await apiJson<{ ok: boolean; log: string }>('/auditox/api/models/pull', {
        method: 'POST',
        body: JSON.stringify({ name }),
      })
      setMessage(result.ok ? `${name} 安装完成` : `${name} 安装失败`)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy('')
    }
  }

  const importFile = async (): Promise<void> => {
    if (!file || busy) return
    const name = importName.trim() || file.name.replace(/\.gguf$/iu, '').replaceAll(/[^A-Za-z0-9._-]/gu, '-')
    setBusy('import-upload')
    setMessage('正在导入 GGUF 模型…')
    setError('')
    try {
      await apiUpload('/auditox/api/models/import-upload', file, { 'x-auditox-model-name': name })
      setMessage(`${name} 已导入并设为当前模型`)
      setFile(null)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy('')
    }
  }

  const importFromPath = async (): Promise<void> => {
    if (!importPath.trim() || !importName.trim() || busy) return
    setBusy('import-path')
    setMessage('正在从本机路径导入模型…')
    setError('')
    try {
      await apiJson('/auditox/api/models/import-path', {
        method: 'POST',
        body: JSON.stringify({ path: importPath, modelName: importName }),
      })
      setMessage(`${importName} 已导入并设为当前模型`)
      await refresh()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally {
      setBusy('')
    }
  }

  if (!system) return <div className={css.pageState}>{error || '正在检测本地模型环境…'}</div>

  const hw = system.hardware
  const gpuText = hw.gpus.length
    ? hw.gpus.map(gpu => `${gpu.name}${gpu.memoryGb ? ` · ${gpu.memoryGb.toFixed(1)} GB` : ''}`).join(' / ')
    : '未检测到独立显卡'
  const connected = system.connection.reachable
  const statusText = connected
    ? `${system.connection.protocol === 'ollama' ? 'Ollama' : '模型服务'}已连接`
    : system.ollama.installed ? 'Ollama 已安装，服务未连接' : '未检测到 Ollama'
  const externalConnected = connected && system.connection.protocol === 'openai'
  const serverAction = busy === 'install'
    ? '安装中…'
    : externalConnected
      ? '服务已连接'
      : !system.ollama.installed
        ? '一键配置 Ollama'
        : system.ollama.reachable ? '关闭模型服务' : '启动模型服务'

  return (
    <div className={css.page}>
      <header className={css.pageHeader}>
        <div><h1>本地模型</h1></div>
        <div className={css.headerActions}>
          <button className={css.primaryButton} onClick={() => { void toggleServer() }} disabled={Boolean(busy) || externalConnected}>
            {serverAction}
          </button>
          <button className={css.secondaryButton} onClick={() => { void refresh() }} disabled={Boolean(busy)}>重新检测</button>
        </div>
      </header>

      <div className={connected ? css.serviceReady : css.serviceIdle}>
        <span className={css.serviceDot} />
        <span>{statusText}</span>
        <span className={css.serviceHint}>{system.config.baseUrl}</span>
      </div>

      {(message || error) && <div className={error ? css.errorBanner : css.infoBanner}>{error || message}</div>}

      <section className={css.setupGrid}>
        <article className={css.setupCard}>
          <h3>模型服务地址</h3>
          <label className={css.fieldLabel} htmlFor="auditox-model-base">OpenAI 兼容地址</label>
          <input id="auditox-model-base" className={css.textInput} value={draftBaseUrl}
            onChange={(event) => { setDraftBaseUrl(event.target.value) }} placeholder="http://127.0.0.1:11434/v1" />
          <label className={css.fieldLabel} htmlFor="auditox-model-key">API Key（可选）</label>
          <input id="auditox-model-key" className={css.textInput} type="password" value={draftApiKey}
            onChange={(event) => { setDraftApiKey(event.target.value) }}
            placeholder={system.config.apiKeyConfigured ? '已保存，留空不修改' : '本地服务通常不需要'} />
          <div className={css.cardActions}>
            <button className={css.primaryButton} onClick={() => { void saveConfig() }} disabled={Boolean(busy)}>保存并测试</button>
            {!system.ollama.installed && <a className={css.textLink} href="https://ollama.com/download" target="_blank" rel="noreferrer">手动安装</a>}
          </div>
        </article>

        <article className={css.setupCard}>
          <h3>当前模型</h3>
          <label className={css.fieldLabel} htmlFor="auditox-model-active">模型名称</label>
          <input id="auditox-model-active" className={css.textInput} list="auditox-model-options" value={draftModel}
            onChange={(event) => { setDraftModel(event.target.value) }} placeholder="qwen3.5:4b" />
          <datalist id="auditox-model-options">
            {system.installedModels.map(name => <option key={name} value={name} />)}
          </datalist>
          <div className={css.inlineNote}>Agent 选择“当前本地模型”时调用：{draftModel || system.config.activeModel}</div>
          <div className={css.cardActions}>
            <button className={css.secondaryButton} onClick={() => { void saveConfig() }} disabled={Boolean(busy)}>设为当前模型</button>
            <button className={css.primaryButton} onClick={() => { void testCall() }} disabled={Boolean(busy)}>
              {busy === 'test' ? '测试中…' : '测试调用'}
            </button>
          </div>
          {testReply && <div className={css.infoBanner}>模型回复：{testReply}</div>}
        </article>

        <article className={`${css.setupCard} ${css.importCard}`}>
          <h3>导入 GGUF 模型</h3>
          <label className={css.fieldLabel} htmlFor="auditox-import-name">模型名称</label>
          <input id="auditox-import-name" className={css.textInput} value={importName}
            onChange={(event) => { setImportName(event.target.value) }} placeholder="例如 qwen-audit:4b" />
          <label className={css.fieldLabel} htmlFor="auditox-import-file">选择本机 GGUF 文件</label>
          <input id="auditox-import-file" className={css.fileInput} type="file" accept=".gguf"
            onChange={(event) => {
              const selected = event.target.files?.[0] ?? null
              setFile(selected)
              if (selected && importName === '') setImportName(selected.name.replace(/\.gguf$/iu, ''))
            }} />
          <div className={css.cardActions}>
            <button className={css.primaryButton} onClick={() => { void importFile() }} disabled={!file || Boolean(busy)}>
              {busy === 'import-upload' ? '导入中…' : '上传并导入'}
            </button>
          </div>
          <div className={css.importDivider}>或使用本机文件路径</div>
          <input className={css.textInput} value={importPath} onChange={(event) => { setImportPath(event.target.value) }}
            placeholder="D:\models\qwen-audit.gguf" />
          <div className={css.cardActions}>
            <button className={css.secondaryButton} onClick={() => { void importFromPath() }}
              disabled={!importPath.trim() || !importName.trim() || Boolean(busy)}>
              {busy === 'import-path' ? '导入中…' : '从路径导入'}
            </button>
          </div>
        </article>
      </section>

      <section className={css.hardwareGrid}>
        <div><span>处理器</span><strong>{hw.cpu}</strong><small>{hw.cores} 核 · {hw.platform}/{hw.arch}</small></div>
        <div><span>内存</span><strong>{hw.memoryGb.toFixed(1)} GB</strong><small>当前可用 {hw.freeMemoryGb.toFixed(1)} GB</small></div>
        <div><span>显卡</span><strong>{gpuText}</strong><small>{system.environment.platform}</small></div>
        <div><span>磁盘</span><strong>{hw.diskFreeGb.toFixed(1)} GB 可用</strong><small>{system.importRoot}</small></div>
      </section>

      <div className={css.sectionTitle}><div><h2>推荐模型</h2></div></div>

      <section className={css.modelGrid}>
        {system.models.map(model => (
          <article key={model.id} className={`${css.modelCard} ${model.recommended ? css.modelRecommended : ''}`}>
            <div className={css.modelTop}>
              <span className={css.modelKind}>{model.kind === 'vision' ? '图像识别' : '语言推理'}</span>
              {model.recommended && <span className={css.badge}>推荐</span>}
              {model.installed && <span className={css.installedBadge}>已安装</span>}
            </div>
            <h3>{model.name}</h3>
            <p>{model.description}</p>
            <div className={css.modelFacts}>
              <span>{model.parameters} · {model.quantization}</span>
              <span>约 {model.sizeGb} GB</span>
              <span>建议 {model.recommendedRamGb} GB 内存</span>
            </div>
            <div className={model.compatible ? css.fitOk : css.fitWarn}>{model.reason}</div>
            <div className={css.modelActions}>
              <button className={css.primaryButton} disabled={!model.compatible || Boolean(busy)}
                onClick={() => { void installCatalogModel(model.id) }}>
                {busy === model.id ? '下载中…' : model.installed ? '重新下载' : '下载安装'}
              </button>
              <a href={model.mirrorSearchUrl} target="_blank" rel="noreferrer">国内镜像</a>
            </div>
          </article>
        ))}
      </section>
    </div>
  )
}
