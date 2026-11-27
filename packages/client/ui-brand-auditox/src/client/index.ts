/** AuditOx browser identity: branded slots, paper-ledger tokens and blank-home artwork. */
import globalCss from './AuditOxGlobal.css?inline'
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type {} from '@deepseek-ai/dsh-client-ui-theme/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import type { SidebarRightTabDefinition } from '@deepseek-ai/dsh-client-ui-sidebar-right/client'
import type { ThemeTokenOverrides } from '@deepseek-ai/dsh-client-ui-theme/client'
import { AuditOxBrandMark, AuditOxBrandName, AuditOxHeroMark } from './brand/Brand.tsx'
import { AuditOxHomeFrame } from './brand/HomeFrame.tsx'
import { AuditDossier, AuditDossierTitle } from './AuditDossier.tsx'
import { AuditDossierButton } from './AuditDossierButton.tsx'

/** Client services consumed by the brand contribution. */
export const inject = ['slots', 'theme', 'sidebarRight', 'sidebarRightTabs']

const DOSSIER_ID = '@deepseek-ai/dsh-client-ui-brand-auditox:dossier'
const DOSSIER_KIND = 'auditox-dossier'
const dossierDefinition: SidebarRightTabDefinition = {
  id: DOSSIER_ID,
  kind: DOSSIER_KIND,
  priority: 'extension',
  title: () => '审计档案',
}

const TOKENS: ThemeTokenOverrides = {
  '--dsw-alias-bg-base': { light: '#f3f6fa', dark: '#05070d' },
  '--dsw-alias-bg-layer-1': { light: '#ffffff', dark: '#111827' },
  '--dsw-alias-bg-layer-2': { light: '#eef2f7', dark: '#172033' },
  '--dsw-alias-bg-overlay': { light: '#ffffff', dark: '#151e2e' },
  '--dsw-alias-border-l1': { light: 'rgba(15, 23, 42, .10)', dark: 'rgba(148, 163, 184, .15)' },
  '--dsw-alias-border-l2': { light: 'rgba(15, 23, 42, .16)', dark: 'rgba(148, 163, 184, .24)' },
  '--dsw-alias-brand-primary': { light: '#0071e3', dark: '#60a5fa' },
  '--dsw-alias-label-primary': { light: '#0f172a', dark: '#f8fafc' },
  '--dsw-alias-label-secondary': { light: '#475569', dark: '#a7b3c8' },
  '--dsw-alias-state-error-primary': { light: '#dc2626', dark: '#fb7185' },
  '--dsw-alias-state-idle-primary': { light: '#64748b', dark: '#8494ab' },
  '--dsw-alias-state-success-primary': { light: '#059669', dark: '#34d399' },
  '--dsw-alias-state-warn-primary': { light: '#d97706', dark: '#fbbf24' },
  '--dsw-specific-sidebar-fill': { light: 'rgba(248, 250, 252, .78)', dark: 'rgba(10, 15, 28, .78)' },
}

/** Register AuditOx theme overrides and the shipped brand slot occupants. */
export function apply(ctx: ClientContext): void {
  ctx.effect(() => {
    const style = document.createElement('style')
    style.dataset.auditoxGlobal = ''
    style.textContent = globalCss
    document.head.append(style)
    return () => { style.remove() }
  }, 'ui-brand-auditox: global workbench surface')
  ctx.effect(
    () => ctx.theme.overrideTokens('@deepseek-ai/dsh-client-ui-brand-auditox', TOKENS),
    'ui-brand-auditox: titanium blue palette',
  )
  ctx.slots.inject('sidebar.brand.mark', () =>
    ctx.slots.register({ name: 'sidebar.brand.mark' }, AuditOxBrandMark),
  )
  ctx.slots.inject('sidebar.brand.name', () =>
    ctx.slots.register({ name: 'sidebar.brand.name' }, AuditOxBrandName),
  )
  ctx.slots.inject('conversation.hero.brand.mark', () =>
    ctx.slots.register({ name: 'conversation.hero.brand.mark' }, AuditOxHeroMark),
  )
  ctx.slots.inject('conversation.hero.frame', () =>
    ctx.slots.register({ name: 'conversation.hero.frame', id: 'auditox-paper-ledger' }, AuditOxHomeFrame),
  )
  ctx.effect(() => ctx.sidebarRightTabs.register(dossierDefinition), 'ui-brand-auditox: dossier tab type')
  ctx.slots.inject('sidebar.right.pane.tab', () =>
    ctx.slots.register({ name: 'sidebar.right.pane.tab', key: DOSSIER_ID }, AuditDossier),
  )
  ctx.slots.inject('sidebar.right.pane.tab.title', () =>
    ctx.slots.register({ name: 'sidebar.right.pane.tab.title', key: DOSSIER_ID }, AuditDossierTitle),
  )
  ctx.slots.inject('conversation.session.header.actions', () =>
    ctx.slots.register({
      name: 'conversation.session.header.actions',
      id: 'auditox-dossier',
      order: 10,
      inject: () => ({ openDossier: () => { ctx.sidebarRight.openTab(DOSSIER_KIND) } }),
    }, AuditDossierButton),
  )
}
