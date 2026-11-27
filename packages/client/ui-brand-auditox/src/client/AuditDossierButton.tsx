import type { ReactNode } from 'react'
import type { PropsRuntime } from '@deepseek-ai/dsh-client-ui-slots'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import css from './AuditDossier.module.css'

/** Injected navigation face for the AuditOx dossier tab. */
export interface AuditDossierButtonInjected {
  openDossier: () => void
}

/** Header action that opens the AuditOx workpaper dossier. */
export function AuditDossierButton({
  openDossier,
}: PropsRuntime<'conversation.session.header.actions'> & AuditDossierButtonInjected): ReactNode {
  return (
    <button type="button" className={css.headerButton} onClick={openDossier}>
      <span className={css.headerMark} aria-hidden="true">档</span>
      审计档案
    </button>
  )
}
