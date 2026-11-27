import type { ReactNode } from 'react'
import type { HeroFrameOwnerProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import css from './HomeFrame.module.css'

/** Layout-neutral AuditOx layer behind the blank Conversation home. */
export function AuditOxHomeFrame({ hero, children }: HeroFrameOwnerProps & { children: ReactNode }) {
  return (
    <div className={css.layer}>
      {hero && (
        <div className={css.field} aria-hidden="true">
          <div className={css.seal}>
            <span>底稿</span>
            <span>证据</span>
            <span>复核</span>
          </div>
          <div className={css.caption}>
            <strong>审小牛</strong>
            <span>WORKPAPER · EVIDENCE · REVIEW</span>
          </div>
        </div>
      )}
      {children}
    </div>
  )
}
