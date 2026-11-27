import css from './Workbench.module.css'

export function ModelPanelIcon({ size = 16, active = false }: { size?: number; active?: boolean }) {
  return <svg className={active ? css.iconActive : css.icon} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M5 5h14v11H5zM8 20h8M12 16v4M8 9h8M8 12h5" />
  </svg>
}

export function SkillPanelIcon({ size = 16, active = false }: { size?: number; active?: boolean }) {
  return <svg className={active ? css.iconActive : css.icon} width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M5 4h6v6H5zM13 4h6v6h-6zM5 14h6v6H5zM13 14h6v6h-6z" />
  </svg>
}
