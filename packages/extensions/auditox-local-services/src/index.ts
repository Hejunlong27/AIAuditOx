/**
 * Local AuditOx capability service.
 *
 * Hardware/model configuration, the OpenAI-compatible local-model gateway,
 * Ollama environment setup, GGUF import and the local SkillHub mirror.
 */
import { execFile, spawn, type ChildProcess } from 'node:child_process'
import { constants as fsConstants } from 'node:fs'
import {
  access, cp, mkdir, open, readFile, readdir, rename, rm, stat, statfs, writeFile,
} from 'node:fs/promises'
import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import os from 'node:os'
import path from 'node:path'
import { promisify } from 'node:util'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'
import { startAuditOxMcpServer } from './mcp.ts'

const execFileAsync = promisify(execFile)
const SKILL_SOURCE = path.resolve(process.env.AUDITOX_SKILL_LIBRARY ?? path.join(process.cwd(), '..', 'skill-library'))
const DSH_HOME = process.env.DSH_HOME ?? path.join(os.homedir(), '.dsh')
const SKILL_INSTALL_ROOT = path.join(DSH_HOME, 'skills')
const MODEL_CONFIG_PATH = path.join(DSH_HOME, 'auditox-model-config.json')
const MODEL_IMPORT_ROOT = path.join(DSH_HOME, 'auditox-models', 'imports')
const MODEL_GATEWAY_PORT = Number(process.env.AUDITOX_MODEL_GATEWAY_PORT ?? 11435)
const MODEL_GATEWAY_URL = `http://127.0.0.1:${MODEL_GATEWAY_PORT}/v1`
const RUNTIME_SERVICE_URL = (process.env.AUDITOX_RUNTIME_URL ?? 'http://127.0.0.1:8765').replace(/\/$/u, '')
const MAX_PULL_LOG = 48_000
const MAX_JSON_BODY = 64 * 1024
const MAX_GATEWAY_BODY = 64 * 1024 * 1024
const MAX_MODEL_UPLOAD = 64 * 1024 * 1024 * 1024
let ollamaProcess: ChildProcess | undefined

interface ModelSpec {
  id: string
  name: string
  kind: 'llm' | 'vision'
  parameters: string
  quantization: string
  sizeGb: number
  minRamGb: number
  recommendedRamGb: number
  minVramGb: number
  description: string
  mirrorSearchUrl: string
}

const MODEL_CATALOG: readonly ModelSpec[] = [
  {
    id: 'qwen3.5:2b', name: 'Qwen3.5 2B', kind: 'llm', parameters: '2B', quantization: 'Q4',
    sizeGb: 1.8, minRamGb: 6, recommendedRamGb: 8, minVramGb: 2,
    description: '低配置笔记本的轻量语言模型。',
    mirrorSearchUrl: 'https://modelscope.cn/models?name=Qwen3.5-2B',
  },
  {
    id: 'qwen3.5:4b', name: 'Qwen3.5 4B', kind: 'llm', parameters: '4B', quantization: 'Q4',
    sizeGb: 3.2, minRamGb: 8, recommendedRamGb: 12, minVramGb: 4,
    description: '默认语言模型，适合中文问答、计划与底稿初稿。',
    mirrorSearchUrl: 'https://modelscope.cn/models?name=Qwen3.5-4B',
  },
  {
    id: 'qwen3.5:9b', name: 'Qwen3.5 9B', kind: 'llm', parameters: '9B', quantization: 'Q4',
    sizeGb: 6.1, minRamGb: 16, recommendedRamGb: 24, minVramGb: 6,
    description: '适合较长上下文和复杂推理。',
    mirrorSearchUrl: 'https://modelscope.cn/models?name=Qwen3.5-9B',
  },
  {
    id: 'qwen2.5vl:3b', name: 'Qwen2.5-VL 3B', kind: 'vision', parameters: '3B', quantization: 'Q4',
    sizeGb: 3.4, minRamGb: 12, recommendedRamGb: 16, minVramGb: 6,
    description: '合同、发票、票据和扫描件识别。',
    mirrorSearchUrl: 'https://modelscope.cn/models?name=Qwen2.5-VL-3B',
  },
  {
    id: 'qwen2.5vl:7b', name: 'Qwen2.5-VL 7B', kind: 'vision', parameters: '7B', quantization: 'Q4',
    sizeGb: 6.2, minRamGb: 24, recommendedRamGb: 32, minVramGb: 8,
    description: '复杂票据、表格和多页扫描件理解。',
    mirrorSearchUrl: 'https://modelscope.cn/models?name=Qwen2.5-VL-7B',
  },
  {
    id: 'minicpm-v:8b', name: 'MiniCPM-V 8B', kind: 'vision', parameters: '8B', quantization: 'Q4',
    sizeGb: 5.8, minRamGb: 24, recommendedRamGb: 32, minVramGb: 8,
    description: '轻量视觉语言模型。',
    mirrorSearchUrl: 'https://modelscope.cn/models?name=MiniCPM-V',
  },
]

interface HardwareInfo {
  cpu: string
  cores: number
  memoryGb: number
  freeMemoryGb: number
  diskFreeGb: number
  platform: string
  arch: string
  gpus: Array<{ name: string; memoryGb: number | null; source: string }>
}

interface SkillEntry {
  id: string
  name: string
  displayName: string
  description: string
  version: string
  category: string
  installed: boolean
  sourcePath: string
  installPath: string
  fileCount: number
}

interface ModelConfig {
  baseUrl: string
  activeModel: string
  apiKey: string
  importedModels: string[]
}

interface ModelProbe {
  reachable: boolean
  protocol: 'ollama' | 'openai' | 'unknown'
  models: string[]
  error?: string
}

const DEFAULT_MODEL_CONFIG: ModelConfig = {
  baseUrl: 'http://127.0.0.1:11434/v1',
  activeModel: process.env.AUDITOX_ACTIVE_MODEL ?? 'qwen3.5:4b',
  apiKey: '',
  importedModels: [],
}

let configCache: Promise<ModelConfig> | undefined

function textField(value: Record<string, unknown>, key: string): string {
  const field = value[key]
  return typeof field === 'string' ? field.trim() : ''
}

function headerText(req: IncomingMessage, name: string): string {
  const value = req.headers[name]
  return Array.isArray(value) ? value[0] ?? '' : value ?? ''
}

function normalizeHttpUrl(value: string): string {
  const input = /^https?:\/\//u.test(value) ? value : `http://${value}`
  const url = new URL(input)
  if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new Error('地址必须使用 HTTP 或 HTTPS')
  return url.toString().replace(/\/$/u, '')
}

function normalizeOpenAIBase(value: string): string {
  const url = new URL(normalizeHttpUrl(value))
  if (url.pathname === '/' || url.pathname === '') url.pathname = '/v1'
  return url.toString().replace(/\/$/u, '')
}

function ollamaRoot(baseUrl: string): string {
  const url = new URL(normalizeOpenAIBase(baseUrl))
  url.pathname = url.pathname.replace(/\/v1\/?$/u, '') || '/'
  return url.toString().replace(/\/$/u, '')
}

function isLoopbackHost(hostname: string): boolean {
  return hostname === '127.0.0.1' || hostname === 'localhost' || hostname === '::1'
}

function normalizeModelConfig(value: Partial<ModelConfig>): ModelConfig {
  const baseUrl = normalizeOpenAIBase(value.baseUrl?.trim() || DEFAULT_MODEL_CONFIG.baseUrl)
  const activeModel = value.activeModel?.trim() || DEFAULT_MODEL_CONFIG.activeModel
  const importedModels = [...new Set((value.importedModels ?? []).filter(name => typeof name === 'string' && name.length > 0))]
  return { baseUrl, activeModel, apiKey: value.apiKey ?? '', importedModels }
}

async function loadModelConfig(): Promise<ModelConfig> {
  configCache ??= (async () => {
    try {
      const parsed = JSON.parse(await readFile(MODEL_CONFIG_PATH, 'utf8')) as Partial<ModelConfig>
      return normalizeModelConfig(parsed)
    } catch {
      return normalizeModelConfig({})
    }
  })()
  return configCache
}

async function saveModelConfig(value: ModelConfig): Promise<ModelConfig> {
  const config = normalizeModelConfig(value)
  await mkdir(DSH_HOME, { recursive: true })
  const temp = `${MODEL_CONFIG_PATH}.${process.pid}.tmp`
  await writeFile(temp, `${JSON.stringify(config, null, 2)}\n`, 'utf8')
  await rename(temp, MODEL_CONFIG_PATH)
  configCache = Promise.resolve(config)
  return config
}

function modelConfigView(config: ModelConfig) {
  return {
    baseUrl: config.baseUrl,
    activeModel: config.activeModel,
    importedModels: config.importedModels,
    apiKeyConfigured: config.apiKey.length > 0,
    gatewayUrl: MODEL_GATEWAY_URL,
  }
}

function modelName(value: string): string {
  const name = value.trim()
  if (!/^[A-Za-z0-9][A-Za-z0-9._/-]{0,120}(?::[A-Za-z0-9._-]{1,40})?$/u.test(name)) {
    throw new Error('模型名称不合法')
  }
  return name
}

function json(res: ServerResponse, status: number, value: unknown): void {
  res.statusCode = status
  res.setHeader('Content-Type', 'application/json; charset=utf-8')
  res.setHeader('Cache-Control', 'no-store')
  res.end(JSON.stringify(value))
}

async function body(req: IncomingMessage, limit = MAX_JSON_BODY): Promise<Record<string, unknown>> {
  const chunks: Uint8Array[] = []
  let size = 0
  for await (const chunk of req) {
    const value = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
    size += value.length
    if (size > limit) throw new Error('请求内容过大')
    chunks.push(new Uint8Array(value))
  }
  if (size === 0) return {}
  const parsed = JSON.parse(Buffer.concat(chunks).toString('utf8')) as unknown
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) throw new Error('请求必须是 JSON 对象')
  return parsed as Record<string, unknown>
}

function frontmatter(text: string): Record<string, string> {
  const match = /^---\r?\n([\s\S]*?)\r?\n---/u.exec(text)
  if (!match) return {}
  const result: Record<string, string> = {}
  for (const line of (match[1] ?? '').split(/\r?\n/u)) {
    const field = /^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$/u.exec(line)
    if (!field) continue
    const [, key, value] = field
    if (key === undefined || value === undefined) continue
    result[key] = value.trim().replace(/^['"]|['"]$/gu, '')
  }
  return result
}

function skillCategory(id: string): string {
  if (id.startsWith('z-')) return '资产类'
  if (id.startsWith('f-')) return '负债类'
  if (id.startsWith('s-')) return '损益类'
  if (id === 'universal-annual-audit') return '总控'
  return '辅助工具'
}

async function countFiles(root: string): Promise<number> {
  let total = 0
  for (const item of await readdir(root, { withFileTypes: true })) {
    if (item.isDirectory()) total += await countFiles(path.join(root, item.name))
    else if (item.isFile()) total += 1
  }
  return total
}

async function command(file: string, args: string[], timeout = 15_000, env?: NodeJS.ProcessEnv): Promise<string> {
  const result = await execFileAsync(file, args, {
    timeout,
    windowsHide: true,
    maxBuffer: 4 * 1024 * 1024,
    ...env === undefined ? {} : { env },
  })
  return `${result.stdout}${result.stderr}`.trim()
}

async function locateOllama(): Promise<string | undefined> {
  const candidates = [
    process.env.OLLAMA_EXECUTABLE,
    process.platform === 'win32'
      ? path.join(process.env.LOCALAPPDATA ?? '', 'Programs', 'Ollama', 'ollama.exe')
      : undefined,
    'ollama',
  ].filter((item): item is string => Boolean(item))
  for (const candidate of candidates) {
    try {
      await command(candidate, ['--version'], 5_000)
      return candidate
    } catch {}
  }
  return undefined
}

async function probeModelServer(config: ModelConfig): Promise<ModelProbe> {
  const root = ollamaRoot(config.baseUrl)
  try {
    const response = await fetch(`${root}/api/tags`, { signal: AbortSignal.timeout(4_000) })
    if (response.ok) {
      const value = await response.json() as { models?: Array<{ name?: string; model?: string }> }
      return {
        reachable: true,
        protocol: 'ollama',
        models: (value.models ?? []).map(item => item.name || item.model || '').filter(Boolean),
      }
    }
  } catch {}
  try {
    const response = await fetch(`${config.baseUrl}/models`, { signal: AbortSignal.timeout(4_000) })
    if (response.ok) {
      const value = await response.json() as { data?: Array<{ id?: string }> }
      return {
        reachable: true,
        protocol: 'openai',
        models: (value.data ?? []).map(item => item.id ?? '').filter(Boolean),
      }
    }
  } catch (error) {
    return { reachable: false, protocol: 'unknown', models: [], error: error instanceof Error ? error.message : String(error) }
  }
  return { reachable: false, protocol: 'unknown', models: [], error: '模型服务无响应' }
}

async function startOllama(executable: string): Promise<boolean> {
  const config = await loadModelConfig()
  if ((await probeModelServer(config)).reachable) return true
  ollamaProcess = spawn(executable, ['serve'], {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    env: { ...process.env, OLLAMA_HOST: ollamaRoot(config.baseUrl) },
  })
  ollamaProcess.unref()
  for (let index = 0; index < 30; index += 1) {
    await new Promise(resolve => setTimeout(resolve, 500))
    if ((await probeModelServer(config)).reachable) return true
  }
  return false
}

async function stopOllama(): Promise<boolean> {
  const config = await loadModelConfig()
  const url = new URL(config.baseUrl)
  if (!isLoopbackHost(url.hostname)) throw new Error('当前为自定义模型地址，请到对应服务中关闭')
  const port = url.port || '11434'
  if (process.platform === 'win32') {
    try {
      const output = await command('powershell.exe', [
        '-NoProfile', '-Command',
        `$c=Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; if($c){$c.OwningProcess}`,
      ], 10_000)
      const pid = Number(output.trim())
      if (Number.isSafeInteger(pid) && pid > 0) {
        await command('taskkill.exe', ['/PID', String(pid), '/T', '/F'], 10_000)
        return true
      }
    } catch {}
  } else {
    try {
      await command('pkill', ['-f', 'ollama serve'], 10_000)
      return true
    } catch {}
  }
  if (ollamaProcess && !ollamaProcess.killed) {
    ollamaProcess.kill()
    return true
  }
  return !(await probeModelServer(config)).reachable
}

async function detectHardware(): Promise<HardwareInfo> {
  const cpus = os.cpus()
  const gpus: HardwareInfo['gpus'] = []
  try {
    const raw = await command('nvidia-smi.exe', [
      '--query-gpu=name,memory.total', '--format=csv,noheader,nounits',
    ], 8_000)
    for (const line of raw.split(/\r?\n/u)) {
      const [name, memory] = line.split(',').map(value => value.trim())
      if (name) gpus.push({ name, memoryGb: Number(memory) / 1024, source: 'nvidia-smi' })
    }
  } catch {}
  if (gpus.length === 0 && process.platform === 'win32') {
    try {
      const raw = await command('powershell.exe', [
        '-NoProfile', '-Command',
        'Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM | ConvertTo-Json -Compress',
      ], 10_000)
      const parsed = JSON.parse(raw) as { Name?: string; AdapterRAM?: number } | Array<{ Name?: string; AdapterRAM?: number }>
      for (const item of Array.isArray(parsed) ? parsed : [parsed]) {
        if (!item.Name) continue
        gpus.push({
          name: item.Name,
          memoryGb: item.AdapterRAM && item.AdapterRAM > 0 ? item.AdapterRAM / 1024 ** 3 : null,
          source: 'Win32_VideoController',
        })
      }
    } catch {}
  }
  let diskFreeGb = 0
  try {
    const info = await statfs(process.cwd(), { bigint: true })
    diskFreeGb = Number(info.bavail * info.bsize) / 1024 ** 3
  } catch {}
  return {
    cpu: cpus[0]?.model.trim() || '未知 CPU',
    cores: cpus.length,
    memoryGb: os.totalmem() / 1024 ** 3,
    freeMemoryGb: os.freemem() / 1024 ** 3,
    diskFreeGb,
    platform: process.platform,
    arch: process.arch,
    gpus,
  }
}

function modelView(spec: ModelSpec, hardware: HardwareInfo, installed: readonly string[]) {
  const vram = Math.max(0, ...hardware.gpus.map(gpu => gpu.memoryGb ?? 0))
  const memoryOk = hardware.memoryGb >= spec.minRamGb
  const diskOk = hardware.diskFreeGb === 0 || hardware.diskFreeGb >= spec.sizeGb + 1
  const gpuSufficient = vram >= spec.minVramGb
  const compatible = memoryOk && diskOk
  const recommended = compatible && hardware.memoryGb >= spec.recommendedRamGb && (vram === 0 || gpuSufficient)
  const reason = !diskOk
    ? `磁盘空间不足：至少需要约 ${(spec.sizeGb + 1).toFixed(1)} GB 可用空间`
    : !memoryOk
      ? `内存不足：建议至少 ${spec.minRamGb} GB 内存`
      : vram === 0
        ? `可用 CPU 运行；建议 ${spec.recommendedRamGb} GB 内存`
        : !gpuSufficient
          ? `显存低于 ${spec.minVramGb} GB，将回退到 CPU`
          : `当前设备可运行；建议至少 ${spec.recommendedRamGb} GB 内存`
  return {
    ...spec,
    installed: installed.some(model => model === spec.id || model.startsWith(`${spec.id}-`)),
    compatible,
    recommended,
    reason,
  }
}

async function listSkills(): Promise<SkillEntry[]> {
  const entries: SkillEntry[] = []
  for (const item of await readdir(SKILL_SOURCE, { withFileTypes: true })) {
    if (!item.isDirectory() || item.name.startsWith('_')) continue
    const sourcePath = path.join(SKILL_SOURCE, item.name)
    const skillFile = path.join(sourcePath, 'SKILL.md')
    try {
      const text = await readFile(skillFile, 'utf8')
      const meta = frontmatter(text)
      const installPath = path.join(SKILL_INSTALL_ROOT, item.name)
      let installed = true
      try { await access(installPath, fsConstants.F_OK) } catch { installed = false }
      entries.push({
        id: item.name,
        name: meta.name || item.name,
        displayName: meta.displayName || meta.name || item.name,
        description: meta.description || meta.summary || '',
        version: meta.version || '',
        category: skillCategory(item.name),
        installed,
        sourcePath,
        installPath,
        fileCount: await countFiles(sourcePath),
      })
    } catch {}
  }
  return entries.sort((a, b) => a.category.localeCompare(b.category, 'zh-CN') || a.displayName.localeCompare(b.displayName, 'zh-CN'))
}

async function skillDetail(id: string): Promise<Record<string, unknown>> {
  if (!/^[a-zA-Z0-9._-]+$/u.test(id)) throw new Error('非法技能 ID')
  const root = path.join(SKILL_SOURCE, id)
  const text = await readFile(path.join(root, 'SKILL.md'), 'utf8')
  return { id, path: path.join(root, 'SKILL.md'), meta: frontmatter(text), content: text.slice(0, 40_000) }
}

async function installSkill(id: string): Promise<void> {
  if (!/^[a-zA-Z0-9._-]+$/u.test(id)) throw new Error('非法技能 ID')
  const source = path.join(SKILL_SOURCE, id)
  const target = path.join(SKILL_INSTALL_ROOT, id)
  await stat(path.join(source, 'SKILL.md'))
  await mkdir(SKILL_INSTALL_ROOT, { recursive: true })
  await rm(target, { recursive: true, force: true })
  await cp(source, target, { recursive: true, force: true })
}

async function uninstallSkill(id: string): Promise<void> {
  if (!/^[a-zA-Z0-9._-]+$/u.test(id)) throw new Error('非法技能 ID')
  const target = path.resolve(SKILL_INSTALL_ROOT, id)
  const root = path.resolve(SKILL_INSTALL_ROOT) + path.sep
  if (!target.startsWith(root)) throw new Error('技能安装路径越界')
  await rm(target, { recursive: true, force: true })
}

function pullModel(executable: string, name: string, config: ModelConfig): Promise<{ ok: boolean; log: string }> {
  return new Promise((resolve) => {
    const child = spawn(executable, ['pull', name], {
      windowsHide: true,
      env: { ...process.env, OLLAMA_HOST: ollamaRoot(config.baseUrl) },
    })
    let output = ''
    const append = (chunk: Buffer): void => { if (output.length < MAX_PULL_LOG) output += chunk.toString('utf8') }
    child.stdout.on('data', append)
    child.stderr.on('data', append)
    child.on('error', (error) => {
      resolve({ ok: false, log: `${output}\n${error.message}`.trim() })
    })
    child.on('close', (code) => {
      resolve({ ok: code === 0, log: output.trim() })
    })
  })
}

async function wingetAvailable(): Promise<boolean> {
  if (process.platform !== 'win32') return false
  try {
    await command('winget.exe', ['--version'], 8_000)
    return true
  } catch {
    return false
  }
}

async function installOllamaEnvironment(): Promise<{ ok: boolean; log: string }> {
  let log = ''
  if (process.platform === 'win32') {
    log = await command('winget.exe', [
      'install', '--id', 'Ollama.Ollama', '--exact', '--silent',
      '--accept-package-agreements', '--accept-source-agreements',
    ], 900_000)
  } else if (process.platform === 'darwin') {
    log = await command('brew', ['install', '--cask', 'ollama'], 900_000)
  } else {
    throw new Error('当前系统请按 Ollama 官方文档安装')
  }
  const executable = await locateOllama()
  if (!executable) return { ok: false, log: `${log}\n安装完成后仍未找到 ollama 可执行文件`.trim() }
  await startOllama(executable)
  return { ok: true, log: log || 'Ollama 已安装' }
}

async function saveModelUpload(req: IncomingMessage, name: string): Promise<string> {
  await mkdir(MODEL_IMPORT_ROOT, { recursive: true })
  const safeName = name.replaceAll(/[^A-Za-z0-9._-]/gu, '_')
  const target = path.join(MODEL_IMPORT_ROOT, `${safeName}-${Date.now()}.gguf`)
  const temp = `${target}.part`
  const handle = await open(temp, 'w')
  let total = 0
  let magic = false
  try {
    for await (const chunk of req) {
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
      if (!magic && bytes.length > 0) {
        if (bytes.subarray(0, 4).toString('ascii') !== 'GGUF') throw new Error('文件不是 GGUF 模型')
        magic = true
      }
      total += bytes.length
      if (total > MAX_MODEL_UPLOAD) throw new Error('模型文件超过 64 GB 限制')
      await handle.write(bytes)
    }
  } catch (error) {
    await handle.close()
    await rm(temp, { force: true })
    throw error
  }
  await handle.close()
  if (!magic) {
    await rm(temp, { force: true })
    throw new Error('没有收到模型文件')
  }
  await rename(temp, target)
  return target
}

async function importGgufModel(model: string, ggufPath: string): Promise<{ ok: boolean; log: string; path: string }> {
  const config = await loadModelConfig()
  const executable = await locateOllama()
  if (!executable) throw new Error('请先一键安装 Ollama')
  if (!(await probeModelServer(config)).reachable && !(await startOllama(executable))) {
    throw new Error('Ollama 服务启动失败')
  }
  const file = await stat(ggufPath)
  if (!file.isFile() || path.extname(ggufPath).toLowerCase() !== '.gguf') throw new Error('请选择 GGUF 模型文件')
  await mkdir(MODEL_IMPORT_ROOT, { recursive: true })
  const modelfile = path.join(MODEL_IMPORT_ROOT, `Modelfile.${Date.now()}`)
  await writeFile(modelfile, `FROM "${ggufPath.replaceAll('\\', '/')}"\nPARAMETER num_ctx 32768\n`, 'utf8')
  try {
    const log = await command(executable, ['create', model, '-f', modelfile], 900_000, {
      ...process.env,
      OLLAMA_HOST: ollamaRoot(config.baseUrl),
    })
    await saveModelConfig({
      ...config,
      activeModel: model,
      importedModels: [...config.importedModels, model],
    })
    return { ok: true, log, path: ggufPath }
  } finally {
    await rm(modelfile, { force: true })
  }
}

async function testModelCall(config: ModelConfig): Promise<{ ok: boolean; text: string }> {
  const response = await fetch(`${config.baseUrl}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...config.apiKey === '' ? {} : { Authorization: `Bearer ${config.apiKey}` },
    },
    body: JSON.stringify({
      model: config.activeModel,
      messages: [{ role: 'user', content: '只回复：审小牛已连接' }],
      max_tokens: 32,
      stream: false,
    }),
    signal: AbortSignal.timeout(60_000),
  })
  const text = await response.text()
  if (!response.ok) throw new Error(text || `HTTP ${response.status}`)
  const value = JSON.parse(text) as { choices?: Array<{ message?: { content?: string } }> }
  return { ok: true, text: value.choices?.[0]?.message?.content ?? '' }
}

function rewriteGatewayModel(raw: Buffer, activeModel: string): Buffer {
  try {
    const value = JSON.parse(raw.toString('utf8')) as Record<string, unknown>
    if (typeof value.model === 'string' && value.model.startsWith('auditox-custom')) {
      value.model = activeModel
      return Buffer.from(JSON.stringify(value))
    }
  } catch {}
  return raw
}

async function forwardModelRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
  const config = await loadModelConfig()
  const pathname = req.url ?? '/v1'
  const suffix = pathname.startsWith('/v1') ? pathname.slice(3) : pathname
  const target = `${config.baseUrl}${suffix.startsWith('/') ? suffix : `/${suffix}`}`
  const headers = new Headers()
  for (const [name, value] of Object.entries(req.headers)) {
    if (value === undefined || name === 'host' || name === 'content-length' || name === 'connection') continue
    for (const item of Array.isArray(value) ? value : [value]) headers.append(name, item)
  }
  if (config.apiKey !== '' && !headers.has('authorization')) headers.set('Authorization', `Bearer ${config.apiKey}`)
  let requestBody: ArrayBuffer | undefined
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    const chunks: Uint8Array[] = []
    let size = 0
    for await (const chunk of req) {
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)
      size += bytes.length
      if (size > MAX_GATEWAY_BODY) throw new Error('模型请求体超过 64 MB')
      chunks.push(new Uint8Array(bytes))
    }
    const combined = Buffer.concat(chunks)
    let bytes: Buffer = combined
    if (target.endsWith('/chat/completions') || target.endsWith('/embeddings')) {
      bytes = rewriteGatewayModel(combined, config.activeModel)
    }
    requestBody = new ArrayBuffer(bytes.byteLength)
    new Uint8Array(requestBody).set(bytes)
  }
  const upstream = await fetch(target, {
    method: req.method ?? 'GET',
    headers,
    ...requestBody === undefined ? {} : { body: requestBody },
    signal: AbortSignal.timeout(10 * 60 * 1000),
  })
  res.statusCode = upstream.status
  for (const [name, value] of upstream.headers) {
    if (name === 'content-length' || name === 'content-encoding' || name === 'transfer-encoding') continue
    res.setHeader(name, value)
  }
  if (upstream.body !== null) {
    const reader = upstream.body.getReader()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      res.write(value)
    }
  }
  res.end()
}

function startModelGateway(ctx: Context): () => void {
  const server = createServer((req, res) => {
    void forwardModelRequest(req, res).catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error)
      if (!res.headersSent) json(res, 502, { error: message })
      else res.end()
      ctx.logger.warn(`auditox model gateway: ${message}`)
    })
  })
  server.on('error', (error) => { ctx.logger.warn(`auditox model gateway: ${error.message}`) })
  server.listen(MODEL_GATEWAY_PORT, '127.0.0.1')
  return () => { server.close() }
}

export const inject = ['webServer']

export function apply(ctx: Context): void {
  ctx.effect(() => startModelGateway(ctx), 'auditox-local: model gateway')
  ctx.effect(() => startAuditOxMcpServer({
    harnessStatus: async () => ({
      name: '审小牛AIAuditOx HARNESS',
      version: '0.2.3-alpha.2',
      platform: process.platform,
      arch: process.arch,
      modelGateway: MODEL_GATEWAY_URL,
      mcpEndpoint: `http://127.0.0.1:${process.env.AUDITOX_MCP_PORT ?? '11436'}/mcp`,
      runtimeUrl: RUNTIME_SERVICE_URL,
      skillSource: SKILL_SOURCE,
      installedSkills: (await listSkills()).filter(skill => skill.installed).length,
    }),
    listSkills: async () => ({ source: SKILL_SOURCE, skills: await listSkills() }),
    readSkill: async id => await skillDetail(id),
    runtimeRequest: async (path, init) => await runtimeRequest(path, init),
  }), 'auditox-local: MCP server')

  const route = (pathname: string, handler: (req: IncomingMessage, res: ServerResponse) => Promise<void>): void => {
    ctx.effect(() => ctx.webServer.register({
      kind: 'exact',
      path: pathname,
      handler: (req, res) => handler(req, res),
    }), `auditox-local: ${pathname}`)
  }

  route('/auditox/api/system', async (_req, res) => {
    const config = await loadModelConfig()
    const [hardware, probe, executable, winget] = await Promise.all([
      detectHardware(), probeModelServer(config), locateOllama(), wingetAvailable(),
    ])
    const models = MODEL_CATALOG.map(spec => modelView(spec, hardware, probe.models))
    const llm = models.filter(model => model.kind === 'llm' && model.compatible)
      .sort((a, b) => b.recommendedRamGb - a.recommendedRamGb)[0]
    const vision = models.filter(model => model.kind === 'vision' && model.compatible)
      .sort((a, b) => b.recommendedRamGb - a.recommendedRamGb)[0]
    json(res, 200, {
      hardware,
      ollama: {
        installed: Boolean(executable),
        running: probe.reachable && probe.protocol === 'ollama',
        executable: executable ?? null,
        reachable: probe.reachable,
        protocol: probe.protocol,
      },
      environment: { winget, platform: process.platform },
      connection: probe,
      config: modelConfigView(config),
      installedModels: probe.models,
      models,
      recommended: { llm: llm?.id ?? null, vision: vision?.id ?? null },
      importRoot: MODEL_IMPORT_ROOT,
      fetchedAt: new Date().toISOString(),
    })
  })

  route('/auditox/api/config', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    try {
      const payload = await body(req)
      const current = await loadModelConfig()
      const next = await saveModelConfig({
        baseUrl: textField(payload, 'baseUrl') || current.baseUrl,
        activeModel: textField(payload, 'activeModel') || current.activeModel,
        apiKey: payload.apiKey === undefined ? current.apiKey : textField(payload, 'apiKey'),
        importedModels: Array.isArray(payload.importedModels)
          ? payload.importedModels.filter((value): value is string => typeof value === 'string')
          : current.importedModels,
      })
      json(res, 200, { ok: true, config: modelConfigView(next), connection: await probeModelServer(next) })
    } catch (error) {
      json(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/ollama/install', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    try {
      const result = await installOllamaEnvironment()
      json(res, result.ok ? 200 : 500, result)
    } catch (error) {
      json(res, 500, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/models/start', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    const config = await loadModelConfig()
    const executable = await locateOllama()
    if (!executable) { json(res, 409, { error: '未检测到 Ollama，请先一键安装。' }); return }
    if (!(await probeModelServer(config)).reachable && !(await startOllama(executable))) {
      json(res, 503, { error: '模型服务启动失败' }); return
    }
    json(res, 200, { ok: true, running: true })
  })

  route('/auditox/api/models/stop', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    try {
      const ok = await stopOllama()
      json(res, ok ? 200 : 503, { ok, running: !ok })
    } catch (error) {
      json(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/models/pull', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    const payload = await body(req)
    const name = modelName(textField(payload, 'name'))
    if (!MODEL_CATALOG.some(model => model.id === name)) { json(res, 400, { error: '模型不在推荐目录中。' }); return }
    const executable = await locateOllama()
    if (!executable) { json(res, 409, { error: '请先一键安装 Ollama。' }); return }
    const config = await loadModelConfig()
    if (!(await probeModelServer(config)).reachable && !(await startOllama(executable))) {
      json(res, 503, { error: 'Ollama 启动失败' }); return
    }
    const result = await pullModel(executable, name, config)
    if (result.ok) await saveModelConfig({ ...config, activeModel: name })
    json(res, result.ok ? 200 : 500, result)
  })

  route('/auditox/api/models/test-chat', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    try {
      json(res, 200, await testModelCall(await loadModelConfig()))
    } catch (error) {
      json(res, 502, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/models/import-path', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    try {
      const payload = await body(req)
      const model = modelName(textField(payload, 'modelName'))
      const source = path.resolve(textField(payload, 'path'))
      json(res, 200, await importGgufModel(model, source))
    } catch (error) {
      json(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/models/import-upload', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    try {
      const model = modelName(headerText(req, 'x-auditox-model-name'))
      const saved = await saveModelUpload(req, model)
      json(res, 200, await importGgufModel(model, saved))
    } catch (error) {
      json(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/skills', async (_req, res) => {
    try {
      json(res, 200, { source: SKILL_SOURCE, installRoot: SKILL_INSTALL_ROOT, skills: await listSkills() })
    } catch (error) {
      json(res, 500, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/skills/detail', async (req, res) => {
    const url = new URL(req.url ?? '/', 'http://127.0.0.1')
    try {
      json(res, 200, await skillDetail(url.searchParams.get('id') ?? ''))
    } catch (error) {
      json(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/skills/install', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    const payload = await body(req)
    try {
      await installSkill(textField(payload, 'id'))
      json(res, 200, { ok: true })
    } catch (error) {
      json(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/skills/uninstall', async (req, res) => {
    if (req.method !== 'POST') { json(res, 405, { error: 'POST required' }); return }
    const payload = await body(req)
    try {
      await uninstallSkill(textField(payload, 'id'))
      json(res, 200, { ok: true })
    } catch (error) {
      json(res, 400, { error: error instanceof Error ? error.message : String(error) })
    }
  })

  route('/auditox/api/skills/sync', async (_req, res) => {
    try {
      const skills = await listSkills()
      json(res, 200, { ok: true, count: skills.length, source: SKILL_SOURCE })
    } catch (error) {
      json(res, 500, { error: error instanceof Error ? error.message : String(error) })
    }
  })
}
async function runtimeRequest(path: string, init?: RequestInit): Promise<unknown> {
  const headers = new Headers(init?.headers)
  if (init?.body !== undefined && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await fetch(`${RUNTIME_SERVICE_URL}${path}`, {
    ...init,
    headers,
    signal: init?.signal ?? AbortSignal.timeout(120_000),
  })
  const body = await response.text()
  let value: unknown = body
  try { value = body === '' ? null : JSON.parse(body) as unknown } catch {}
  if (!response.ok) throw new Error(`AuditOx Runtime HTTP ${response.status}: ${body}`)
  return value
}
