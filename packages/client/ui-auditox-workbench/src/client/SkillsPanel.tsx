import { useEffect, useMemo, useState, type ReactNode } from 'react'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import { apiJson, type SkillRecord } from './api.ts'
import css from './Workbench.module.css'

/** AuditOx SkillHub mirror browser and per-project installation surface. */
export function SkillsPanel(_props: PropsRuntime<'main'>): ReactNode {
  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('全部')
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<{ id: string; content: string } | null>(null)

  const load = async (): Promise<void> => {
    try {
      const value = await apiJson<{ skills: SkillRecord[] }>('/auditox/api/skills')
      setSkills(value.skills)
      setError('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    }
  }

  useEffect(() => { void load() }, [])

  const categories = ['全部', ...new Set(skills.map(skill => skill.category))]
  const filtered = useMemo(() => skills.filter((skill) => {
    const inCategory = category === '全部' || skill.category === category
    const text = `${skill.displayName} ${skill.id} ${skill.description}`.toLowerCase()
    return inCategory && (!query || text.includes(query.toLowerCase()))
  }), [skills, category, query])

  const sync = async (): Promise<void> => {
    setBusy('sync')
    try {
      const result = await apiJson<{ count: number }>('/auditox/api/skills/sync', { method: 'POST' })
      setMessage(`已同步本地 SkillHub 镜像，共 ${result.count} 个技能`)
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy('') }
  }

  const install = async (skill: SkillRecord): Promise<void> => {
    setBusy(skill.id)
    try {
      await apiJson(skill.installed ? '/auditox/api/skills/uninstall' : '/auditox/api/skills/install', {
        method: 'POST',
        body: JSON.stringify({ id: skill.id }),
      })
      setMessage(skill.installed ? `${skill.displayName} 已卸载` : `${skill.displayName} 已安装到本机技能目录`)
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy('') }
  }

  const open = async (skill: SkillRecord): Promise<void> => {
    setBusy(skill.id)
    try {
      const value = await apiJson<{ id: string; content: string }>(`/auditox/api/skills/detail?id=${encodeURIComponent(skill.id)}`)
      setDetail(value)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause))
    } finally { setBusy('') }
  }

  return (
    <div className={css.page}>
      <header className={css.pageHeader}>
        <div>
          <h1>技能中心</h1>
        </div>
        <button className={css.primaryButton} onClick={() => { void sync() }} disabled={Boolean(busy)}>
          {busy === 'sync' ? '同步中…' : '同步技能库'}
        </button>
      </header>

      <div className={css.skillToolbar}>
        <input
          value={query}
          onChange={(event) => { setQuery(event.target.value) }}
          placeholder="搜索技能、科目或程序……"
        />
        <div className={css.categoryRow}>
          {categories.map(item => (
            <button
              key={item}
              className={item === category ? css.categoryActive : css.category}
              onClick={() => { setCategory(item) }}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {(message || error) && <div className={error ? css.errorBanner : css.infoBanner}>{error || message}</div>}

      <div className={css.skillStats}>
        <span>共 {skills.length} 个技能</span>
        <span>已安装 {skills.filter(skill => skill.installed).length}</span>
        <span>当前显示 {filtered.length}</span>
      </div>

      <section className={css.skillGrid}>
        {filtered.map(skill => (
          <article key={skill.id} className={css.skillCard}>
            <button className={css.skillTitleButton} onClick={() => { void open(skill) }}>
              <span className={css.skillCategory}>{skill.category}</span>
              <strong>{skill.displayName}</strong>
              <small>{skill.id}</small>
            </button>
            <p>{skill.description || '暂无技能说明'}</p>
            <div className={css.skillFooter}>
              <span>{skill.version ? `v${skill.version}` : `${skill.fileCount} 个文件`}</span>
              <button
                className={skill.installed ? css.secondaryButton : css.primaryButton}
                onClick={() => { void install(skill) }}
                disabled={Boolean(busy)}
              >
                {busy === skill.id ? '处理中…' : skill.installed ? '卸载' : '安装'}
              </button>
            </div>
          </article>
        ))}
      </section>

      {detail && (
        <div className={css.detailOverlay} onClick={() =>{  setDetail(null) }}>
          <article className={css.detailPanel} onClick={(event) =>{  event.stopPropagation() }}>
            <header><h2>{detail.id}</h2><button onClick={() =>{  setDetail(null) }}>关闭</button></header>
            <pre>{detail.content}</pre>
          </article>
        </div>
      )}
      <p className={css.footnote}>本机 SkillHub 镜像</p>
    </div>
  )
}
