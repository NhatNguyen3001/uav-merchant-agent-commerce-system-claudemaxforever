import { ref } from 'vue'

const API = import.meta.env.VITE_API_BASE || ''

export function useRun() {
  const events = ref([])
  const runId = ref(null)
  const running = ref(false)
  let source = null

  async function start(scenario) {
    if (source) source.close()
    events.value = []
    running.value = true
    const res = await fetch(`${API}/api/runs`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ scenario }),
    })
    if (!res.ok) {
      running.value = false
      throw new Error(await res.text())
    }
    runId.value = (await res.json()).run_id
    source = new EventSource(`${API}/api/runs/${runId.value}/events`)
    source.addEventListener('event', (e) => {
      events.value.push(JSON.parse(e.data))
    })
    source.onerror = () => {
      source.close()
      source = null
      running.value = false
    }
  }

  return { events, runId, running, start }
}

export async function fetchRules() {
  return (await fetch(`${API}/api/config/rules`)).json()
}

export async function saveRules(rules) {
  const res = await fetch(`${API}/api/config/rules`, {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(rules),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function fetchRuns() {
  return (await fetch(`${API}/api/runs`)).json()
}
