/**
 * Построчное сравнение двух вариантов SQL.
 * Используется при показе предложения модели Qwen перед одобрением.
 *
 * Алгоритм — наибольшая общая подпоследовательность строк.
 */

export function diffLines(oldText, newText) {
  const oldLines = String(oldText || '').split('\n')
  const newLines = String(newText || '').split('\n')

  const rows = oldLines.length
  const cols = newLines.length

  // Таблица длин LCS
  const lcs = Array.from({ length: rows + 1 }, () => new Uint32Array(cols + 1))
  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = cols - 1; j >= 0; j -= 1) {
      lcs[i][j] =
        oldLines[i] === newLines[j]
          ? lcs[i + 1][j + 1] + 1
          : Math.max(lcs[i + 1][j], lcs[i][j + 1])
    }
  }

  const result = []
  let i = 0
  let j = 0

  while (i < rows && j < cols) {
    if (oldLines[i] === newLines[j]) {
      result.push({ type: 'equal', text: oldLines[i], oldNo: i + 1, newNo: j + 1 })
      i += 1
      j += 1
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      result.push({ type: 'removed', text: oldLines[i], oldNo: i + 1, newNo: null })
      i += 1
    } else {
      result.push({ type: 'added', text: newLines[j], oldNo: null, newNo: j + 1 })
      j += 1
    }
  }
  while (i < rows) {
    result.push({ type: 'removed', text: oldLines[i], oldNo: i + 1, newNo: null })
    i += 1
  }
  while (j < cols) {
    result.push({ type: 'added', text: newLines[j], oldNo: null, newNo: j + 1 })
    j += 1
  }

  return result
}

export function diffSummary(rows) {
  return {
    added: rows.filter((r) => r.type === 'added').length,
    removed: rows.filter((r) => r.type === 'removed').length,
  }
}
