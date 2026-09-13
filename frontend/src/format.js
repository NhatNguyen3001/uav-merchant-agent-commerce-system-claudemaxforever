// Numbers the way a merchant reads them: $179, $522.70, $1,650; discounts as whole percents.
export function money(n) {
  const x = Number(n)
  if (!Number.isFinite(x)) return ''
  const whole = Number.isInteger(x)
  return '$' + x.toLocaleString('en-US', { minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2 })
}

export function pct(n) {
  return `${Math.round(Number(n))}%`
}

export function days(n) {
  return `${n} day${Number(n) === 1 ? '' : 's'}`
}

// "6/6" -> "All 6 requirements met"; "5/6" -> "5 of 6 requirements met".
export function coverage(s) {
  const m = /^(\d+)\/(\d+)$/.exec(String(s || ''))
  if (!m) return ''
  const [, a, b] = m
  return a === b ? `All ${b} requirements met` : `${a} of ${b} requirements met`
}
