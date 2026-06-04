const DEFAULT_SIZE = 64
const GRID_SIZE = 5
const MIRROR_COLUMNS = 3
const DEFAULT_BACKGROUND = '#f3f4f6'

const COLOR_PALETTE = [
  '#265c96',
  '#3996ae',
  '#13c2c2',
  '#52c41a',
  '#faad14',
  '#ff7a45',
  '#ff4d4f',
  '#9254de',
  '#597ef7',
  '#4f4f4f'
]

const normalizeSeed = (id) => {
  if (id === null || id === undefined || String(id).trim() === '') {
    throw new Error('generatePixelAvatar requires an id')
  }
  return String(id).trim()
}

const hashSeed = (seed) => {
  let hash = 2166136261

  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i)
    hash = Math.imul(hash, 16777619)
  }

  return hash >>> 0
}

const buildCells = (hash) => {
  const cells = []

  for (let row = 0; row < GRID_SIZE; row += 1) {
    for (let col = 0; col < MIRROR_COLUMNS; col += 1) {
      const bitIndex = row * MIRROR_COLUMNS + col
      const filled = ((hash >>> bitIndex) & 1) === 1

      if (!filled) continue

      cells.push([col, row])

      const mirroredCol = GRID_SIZE - col - 1
      if (mirroredCol !== col) {
        cells.push([mirroredCol, row])
      }
    }
  }

  if (cells.length === 0) {
    cells.push([2, 2])
  }

  return cells
}

export const generatePixelAvatar = (id) => {
  const seed = normalizeSeed(id)
  const hash = hashSeed(seed)
  const color = COLOR_PALETTE[(hash >>> 16) % COLOR_PALETTE.length]
  const cells = buildCells(hash)
    .map(([x, y]) => `<rect x="${x}" y="${y}" width="1" height="1"/>`)
    .join('')

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${DEFAULT_SIZE}" height="${DEFAULT_SIZE}" viewBox="0 0 ${GRID_SIZE} ${GRID_SIZE}" shape-rendering="crispEdges"><rect width="${GRID_SIZE}" height="${GRID_SIZE}" fill="${DEFAULT_BACKGROUND}"/><g fill="${color}">${cells}</g></svg>`

  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}
