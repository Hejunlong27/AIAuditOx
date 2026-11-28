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
      <span className={css.en}>AIAUDITOX HARNESS</span>
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
      className={className === undefined ? css.mark : `${css.mark} ${className}`}
      width={size}
      height={size}
      viewBox="0 0 48 48"
      role="img"
      aria-label="审小牛"
    >
      <rect x="2" y="2" width="44" height="44" rx="11" fill="#14547F" />
      <path d="M10.3 17C10.3 12 13.6 8.4 17.5 8.4" fill="none" stroke="#F0E0BF" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M37.7 17C37.7 12 34.4 8.4 30.5 8.4" fill="none" stroke="#F0E0BF" strokeWidth="2.6" strokeLinecap="round" />
      <path d="M15.8 15.1h16.4c2.1 0 3.8 1.6 3.8 3.8v8.4c0 6.1-5.4 11-12 11s-12-4.9-12-11v-8.4c0-2.2 1.7-3.8 3.8-3.8z" fill="#FFFFFF" opacity=".97" />
      <path d="M18.9 25.9l4.1 4.1 8.1-8.4" fill="none" stroke="#A8792A" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />    </svg>
  )
}
