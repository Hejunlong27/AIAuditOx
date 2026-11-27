/** AuditOx workbench: local model manager, SkillHub center and the home status switch. */
import type { Context as ClientContext } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'
import type {} from '@deepseek-ai/dsh-client-ui-sidebar/client'
import type {} from '@deepseek-ai/dsh-client-ui-layout/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
import type { MainPanelId } from '@deepseek-ai/dsh-client-ui-layout/client'
import { LocalModelToggle } from './LocalModelToggle.tsx'
import { LocalModelsPanel } from './LocalModelsPanel.tsx'
import { ModelPanelIcon, SkillPanelIcon } from './PanelIcons.tsx'
import { SkillsPanel } from './SkillsPanel.tsx'

export const inject = ['slots']

export const MODELS_PANEL = 'auditox-models' as MainPanelId
export const SKILLS_PANEL = 'auditox-skills' as MainPanelId

/** Register the AuditOx-owned panels without depending on the upstream plugin manager. */
export function apply(ctx: ClientContext): void {
  ctx.slots.inject('main', function* () {
    yield ctx.slots.register({ name: 'main', key: MODELS_PANEL }, LocalModelsPanel)
    yield ctx.slots.register({ name: 'main', key: SKILLS_PANEL }, SkillsPanel)
  })

  ctx.slots.inject('sidebar.panellist', function* () {
    yield ctx.slots.register({
      name: 'sidebar.panellist', id: MODELS_PANEL, order: 20, label: '本地模型',
    }, ModelPanelIcon)
    yield ctx.slots.register({
      name: 'sidebar.panellist', id: SKILLS_PANEL, order: 30, label: '技能中心',
    }, SkillPanelIcon)
  })

  ctx.slots.inject('conversation.hero.options', () => ctx.slots.register({
    name: 'conversation.hero.options', id: 'auditox-local-model-toggle', order: 20,
  }, LocalModelToggle))

  ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register({
    name: 'conversation.session.header.actions', id: 'auditox-local-model-toggle', order: 20,
  }, LocalModelToggle))
}
