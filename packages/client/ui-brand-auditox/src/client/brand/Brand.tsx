import type { HeroBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { SidebarBrandMarkOwnerProps } from '@deepseek-ai/dsh-client-ui-sidebar/client'
import css from './Brand.module.css'

/** AuditOx seal mark shared by the sidebar and the blank home. */
export function AuditOxBrandMark({ size }: SidebarBrandMarkOwnerProps) {
  return <Seal size={size} />
}

/** AuditOx sidebar wordmark, separate from the seal slot. */
export function AuditOxBrandName() {
  return (
    <span className={css.name}>
      <span className={css.zh}>审小牛</span>
      <span className={css.en}>AUDITOX HARNESS</span>
    </span>
  )
}

/** Larger seal shown before the blank-home headline. */
export function AuditOxHeroMark({ size, className }: HeroBrandMarkOwnerProps) {
  return <Seal size={size} className={className} />
}

function Seal({ size, className }: { size: number; className?: string | undefined }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="审小牛"
    >
      <rect x="5" y="3" width="38" height="42" className={css.seal} />
      <path d="M13 14h22M13 21h22M13 28h14" className={css.rule} />
      <path d="M29 29h7v7h-7z" className={css.check} />
    </svg>
  )
}
