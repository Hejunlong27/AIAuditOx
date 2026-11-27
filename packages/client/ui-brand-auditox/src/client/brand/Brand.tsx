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
      <rect x="2" y="2" width="44" height="44" rx="12" fill="#0F172A" />
      <path
        d="M10 16.2C11.8 12.9 14.9 11.9 17.5 14.3M38 16.2C36.2 12.9 33.1 11.9 30.5 14.3"
        fill="none"
        stroke="#E2E8F0"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <path
        d="M13.5 17.5L19 14.2H29L34.5 17.5L32.4 27.5L24 34.2L15.6 27.5L13.5 17.5Z"
        fill="#EAF2FF"
        stroke="#93C5FD"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path
        d="M19 23.3L22.8 27L30 19.8"
        fill="none"
        stroke="#0071E3"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
