/** Small same-origin client for AuditOx local services. */
async function decode<T>(response: Response): Promise<T> {
  const text = await response.text()
  let value: unknown = null
  try { value = text ? JSON.parse(text) : null } catch {}
  if (!response.ok) {
    const serverError = typeof value === 'object' && value !== null && 'error' in value && typeof value.error === 'string'
      ? value.error
      : undefined
    throw new Error(serverError || text || `HTTP ${response.status}`)
  }
  return value as T
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (init?.body !== undefined && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  return decode<T>(await fetch(path, {
    ...init,
    credentials: 'same-origin',
    headers,
  }))
}

export async function apiUpload<T>(path: string, file: File, headers: Record<string, string>): Promise<T> {
  return decode<T>(await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers,
    body: file,
  }))
}

export interface ModelConfigView {
  baseUrl: string
  activeModel: string
  importedModels: string[]
  apiKeyConfigured: boolean
  gatewayUrl: string
}

export interface SystemState {
  hardware: {
    cpu: string
    cores: number
    memoryGb: number
    freeMemoryGb: number
    diskFreeGb: number
    platform: string
    arch: string
    gpus: Array<{ name: string; memoryGb: number | null; source: string }>
  }
  ollama: {
    installed: boolean
    running: boolean
    executable: string | null
    reachable: boolean
    protocol: 'ollama' | 'openai' | 'unknown'
  }
  environment: { winget: boolean; platform: string }
  connection: {
    reachable: boolean
    protocol: 'ollama' | 'openai' | 'unknown'
    models: string[]
    error?: string
  }
  config: ModelConfigView
  installedModels: string[]
  models: Array<{
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
    installed: boolean
    compatible: boolean
    recommended: boolean
    reason: string
  }>
  recommended: { llm: string | null; vision: string | null }
  importRoot: string
}

export interface SkillRecord {
  id: string
  name: string
  displayName: string
  description: string
  version: string
  category: string
  installed: boolean
  fileCount: number
}
