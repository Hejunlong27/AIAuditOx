/**
 * Render the installer lockup and Windows application icon from the AuditOx mark.
 * Run `node scripts/render-installer-brand.mjs` from `apps/desktop` after changing
 * the Windows mark, then rerun the tray icon generator.
 */
import { readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import sharp from 'sharp'

const ASSET_DIRECTORY = fileURLToPath(new URL('../installer/assets/', import.meta.url))
const ICON_SOURCE = fileURLToPath(new URL('../resources/icon-windows.svg', import.meta.url))
const ICON_OUTPUT = fileURLToPath(new URL('../resources/icon-windows.png', import.meta.url))

const LIGHT = {
  background: '#F5F7FA',
  glow: '#FFFFFF',
  title: '#0D1F2D',
  subtitle: '#7B93A3',
  accent: '#A8792A',
}
const DARK = {
  background: '#111820',
  glow: '#1B2834',
  title: '#F5F7FA',
  subtitle: '#9EB0BD',
  accent: '#D8AD54',
}
const FONT = "'Microsoft YaHei UI','PingFang SC','Segoe UI',sans-serif"

function backgroundSvg(width, height, palette) {
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <radialGradient id="glow" cx="50%" cy="44%" r="62%">
        <stop offset="0" stop-color="${palette.glow}"/>
        <stop offset=".58" stop-color="${palette.glow}" stop-opacity=".28"/>
        <stop offset="1" stop-color="${palette.background}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect width="${width}" height="${height}" fill="${palette.background}"/>
    <rect width="${width}" height="${height}" fill="url(#glow)"/>
  </svg>`
}

function lockupTextSvg(width, height, scale, palette) {
  const textX = 266 * scale
  const titleY = 106 * scale
  const subtitleY = 130 * scale
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
    <text x="${textX}" y="${titleY}" fill="${palette.title}" font-family="${FONT}" font-size="${31 * scale}px" font-weight="700" letter-spacing="${-0.8 * scale}px">审小牛</text>
    <rect x="${textX + 1 * scale}" y="${112 * scale}" width="${20 * scale}" height="${2 * scale}" rx="${1 * scale}" fill="${palette.accent}"/>
    <text x="${textX + 1 * scale}" y="${subtitleY}" fill="${palette.subtitle}" font-family="${FONT}" font-size="${10 * scale}px" font-weight="650" letter-spacing="${2.4 * scale}px">AIAUDITOX HARNESS</text>
  </svg>`
}

async function renderLockup(file, scale, palette) {
  const width = 600 * scale
  const height = 220 * scale
  const markEdge = Math.round(84 * scale)
  const mark = await sharp(ICON_SOURCE, { density: 96 }).resize(markEdge, markEdge).png().toBuffer()
  const text = await sharp(Buffer.from(lockupTextSvg(width, height, scale, palette))).png().toBuffer()
  await sharp(Buffer.from(backgroundSvg(width, height, palette)))
    .composite([
      { input: mark, left: Math.round(160 * scale), top: Math.round(68 * scale) },
      { input: text, left: 0, top: 0 },
    ])
    .png({ compressionLevel: 9 })
    .toFile(`${ASSET_DIRECTORY}/${file}`)
}

function sidebarSvg(palette) {
  const width = 164
  const height = 314
  return `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <radialGradient id="glow" cx="50%" cy="27%" r="64%">
        <stop offset="0" stop-color="${palette.glow}"/>
        <stop offset=".62" stop-color="${palette.glow}" stop-opacity=".22"/>
        <stop offset="1" stop-color="${palette.background}" stop-opacity="0"/>
      </radialGradient>
    </defs>
    <rect width="164" height="314" fill="${palette.background}"/>
    <rect width="164" height="314" fill="url(#glow)"/>
    <rect x="55" y="228" width="54" height="2" rx="1" fill="${palette.accent}"/>
    <text x="82" y="190" text-anchor="middle" fill="${palette.title}" font-family="${FONT}" font-size="22px" font-weight="700" letter-spacing="-.7px">审小牛</text>
    <text x="82" y="210" text-anchor="middle" fill="${palette.subtitle}" font-family="${FONT}" font-size="8px" font-weight="650" letter-spacing="1.7px">AIAUDITOX</text>
    <text x="82" y="222" text-anchor="middle" fill="${palette.subtitle}" font-family="${FONT}" font-size="8px" font-weight="650" letter-spacing="1.7px">HARNESS</text>
  </svg>`
}

async function renderSidebar() {
  const mark = await sharp(ICON_SOURCE, { density: 96 }).resize(78, 78).png().toBuffer()
  const text = await sharp(Buffer.from(sidebarSvg(LIGHT))).png().toBuffer()
  await sharp({ create: { width: 164, height: 314, channels: 4, background: LIGHT.background } })
    .composite([
      { input: text, left: 0, top: 0 },
      { input: mark, left: 43, top: 66 },
    ])
    .png({ compressionLevel: 9 })
    .toFile(`${ASSET_DIRECTORY}/uninstaller-sidebar.png`)
}

await renderLockup('brand.png', 1, LIGHT)
await renderLockup('brand-2x.png', 2, LIGHT)
await renderLockup('brand-dark.png', 1, DARK)
await renderLockup('brand-dark-2x.png', 2, DARK)
await renderSidebar()
await sharp(ICON_SOURCE, { density: 96 }).resize(512, 512).png({ compressionLevel: 9 }).toFile(ICON_OUTPUT)
await writeFile(`${ASSET_DIRECTORY}/README.md`, 'Generated from resources/icon-windows.svg by scripts/render-installer-brand.mjs.\n')
console.info('Rendered AuditOx installer lockups and Windows icon.')