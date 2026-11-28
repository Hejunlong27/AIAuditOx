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
  '--dsw-alias-bg-base': { light: '#F5F8FA', dark: '#07131E' },
  '--dsw-alias-bg-layer-1': { light: '#ffffff', dark: '#0D1F2D' },
  '--dsw-alias-bg-layer-2': { light: '#EFF4F8', dark: '#153143' },
  '--dsw-alias-bg-overlay': { light: '#ffffff', dark: '#102838' },
  '--dsw-alias-border-l1': { light: 'rgba(13, 31, 45, .10)', dark: 'rgba(203, 216, 226, .15)' },
  '--dsw-alias-border-l2': { light: 'rgba(13, 31, 45, .16)', dark: 'rgba(203, 216, 226, .24)' },
  '--dsw-alias-brand-primary': { light: '#14547F', dark: '#4C8FB5' },
  '--dsw-alias-label-primary': { light: '#0D1F2D', dark: '#F5F8FA' },
  '--dsw-alias-label-secondary': { light: '#46606F', dark: '#A9BCC8' },
  '--dsw-alias-state-error-primary': { light: '#B03A30', dark: '#E58A82' },
  '--dsw-alias-state-idle-primary': { light: '#7B93A3', dark: '#91A6B4' },
  '--dsw-alias-state-success-primary': { light: '#15735A', dark: '#58B596' },
  '--dsw-alias-state-warn-primary': { light: '#A65A0C', dark: '#D8B05B' },
  '--dsw-specific-sidebar-fill': { light: 'rgba(255, 255, 255, .90)', dark: 'rgba(7, 19, 30, .86)' },
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
