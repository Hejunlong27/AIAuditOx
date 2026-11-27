/** AuditOx browser identity: branded slots, paper-ledger tokens and blank-home artwork. */
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
  '--dsw-alias-bg-base': { light: '#f1eee6', dark: '#101612' },
  '--dsw-alias-bg-layer-1': { light: '#fbf8f0', dark: '#18211d' },
  '--dsw-alias-bg-layer-2': { light: '#ece6d9', dark: '#202b26' },
  '--dsw-alias-bg-overlay': { light: '#fffaf1', dark: '#202b26' },
  '--dsw-alias-border-l1': { light: '#d8d0c2', dark: '#34423c' },
  '--dsw-alias-border-l2': { light: '#c2b7a6', dark: '#4a5a52' },
  '--dsw-alias-brand-primary': { light: '#a33d2e', dark: '#d36a59' },
  '--dsw-alias-label-primary': { light: '#1d2522', dark: '#eef2ec' },
  '--dsw-alias-label-secondary': { light: '#68716b', dark: '#aab4ad' },
  '--dsw-alias-state-error-primary': { light: '#9c342e', dark: '#e2786b' },
  '--dsw-alias-state-idle-primary': { light: '#7b827e', dark: '#8f9993' },
  '--dsw-alias-state-success-primary': { light: '#3c6957', dark: '#65a98a' },
  '--dsw-alias-state-warn-primary': { light: '#a9752e', dark: '#d2a257' },
  '--dsw-specific-sidebar-fill': { light: '#e7e1d4', dark: '#0b1110' },
}

/** Register AuditOx theme overrides and the shipped brand slot occupants. */
export function apply(ctx: ClientContext): void {
  ctx.effect(
    () => ctx.theme.overrideTokens('@deepseek-ai/dsh-client-ui-brand-auditox', TOKENS),
    'ui-brand-auditox: paper-ledger palette',
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
