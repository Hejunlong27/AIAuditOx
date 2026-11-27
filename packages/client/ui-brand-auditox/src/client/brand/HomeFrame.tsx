import type { ReactNode } from 'react'
import type { HeroFrameOwnerProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import css from './HomeFrame.module.css'

const STAGES = [
  ['01', '项目资料', '报表 · 账套 · 凭证'],
  ['02', '审计计划', '范围 · 风险 · 重要性'],
  ['03', '控制测试', '穿行 · 样本 · 偏差'],
  ['04', '实质程序', '测算 · 函证 · 调整'],
  ['05', '项目复核', '证据链 · 结论 · 报告'],
] as const

/** AuditOx project cockpit layered behind the blank Conversation home. */
export function AuditOxHomeFrame({ hero, children }: HeroFrameOwnerProps & { children: ReactNode }) {
  return (
    <>
      {hero && (
        <div className={css.canvas} aria-hidden="true">
          <div className={css.headerRule}>
            <span>审小牛AIAuditOx HARNESS</span>
            <span>一切审计程序皆可 Skill 化</span>
          </div>
          <section className={css.flow}>
            <p className={css.railKicker}>审计流程</p>
            <ol>
              {STAGES.map(([index, title, detail]) => (
                <li key={index}>
                  <span>{index}</span>
                  <div><strong>{title}</strong><small>{detail}</small></div>
                </li>
              ))}
            </ol>
          </section>
        </div>
      )}
      {children}
    </>
  )
}
