import type { ReactNode } from 'react'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import css from './AuditDossier.module.css'

const STAGES = [
  '财务报表分析',
  '审计计划',
  '重要性水平',
  '审计程序',
  '穿行与控制',
  '实质性底稿',
  '资料缺口',
  '复核包',
]

/** AuditOx right-Sidebar dossier overview for the current Session. */
export function AuditDossier({ sessionId }: PropsRuntime<'sidebar.right.pane.tab'>): ReactNode {
  return (
    <section className={css.panel} data-auditox-dossier={sessionId}>
      <header className={css.hero}>
        <span className={css.kicker}>AUDITOX · WORKPAPER DESK</span>
        <h2>审计档案</h2>
        <p>项目资料、风险判断、程序执行和证据链在同一会话中留痕。</p>
      </header>
      <div className={css.rule} />
      <section className={css.section}>
        <div className={css.sectionHead}>
          <h3>引导阶段</h3>
          <span>8 个阶段</span>
        </div>
        <ol className={css.stageList}>
          {STAGES.map((stage, index) => <li key={stage}><span>{String(index + 1).padStart(2, '0')}</span>{stage}</li>)}
        </ol>
      </section>
      <section className={css.section}>
        <div className={css.sectionHead}><h3>工作边界</h3></div>
        <ul className={css.boundaryList}>
          <li>金额计算使用确定性工具，不采用模型估算。</li>
          <li>每次工具调用写入本机哈希链 Trace，底稿保留程序、证据和修订记录。</li>
          <li>未取得资料的程序保持待补充，不写成已执行。</li>
          <li>最终判断由项目组和签字人完成。</li>
        </ul>
      </section>
      <footer className={css.footer}>客户资料留在本机 · 证据与底稿可追溯</footer>
    </section>
  )
}

/** Short title used by the right-Sidebar tab chip. */
export function AuditDossierTitle(): ReactNode {
  return <span>审计档案</span>
}
