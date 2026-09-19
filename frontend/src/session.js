// A random key for this browser, kept in localStorage, sent with every API call so each person only
// sees their own runs. If storage is blocked (some private modes), the key lasts until the page closes.
const KEY = 'macs.session'
let current = null

function randomKey() {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

export function sessionKey() {
  if (current) return current
  try {
    current = localStorage.getItem(KEY)
  } catch (_) {}
  if (!current || !/^[A-Za-z0-9_-]{16,128}$/.test(current)) {
    current = randomKey()
    try {
      localStorage.setItem(KEY, current)
    } catch (_) {}
  }
  return current
}

export const SESSION_HEADER = 'X-MACS-Session'
