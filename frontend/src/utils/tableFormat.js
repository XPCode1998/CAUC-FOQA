export function formatTableCellValue(value, digits = 4, emptyText = '-') {
  if (value === null || value === undefined || value === '') return emptyText

  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return emptyText
    return value.toFixed(digits)
  }

  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (!trimmed) return emptyText

    const normalized = trimmed.toLowerCase()
    if (normalized === 'nan' || normalized === 'inf' || normalized === 'infinity' || normalized === '-inf' || normalized === '-infinity') {
      return emptyText
    }

    const numericValue = Number(trimmed)
    if (Number.isFinite(numericValue)) {
      return numericValue.toFixed(digits)
    }

    return value
  }

  return String(value)
}