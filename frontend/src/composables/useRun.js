import { ref } from 'vue'

const API = import.meta.env.VITE_API_BASE || ''

export function useRun() {
  const events = ref([])
  const runId = ref(null)
  const running = ref(false)
  const error = ref('')
  let source = null

  // body is {scenario} for canned runs and replays, or {agent_id, query} for a typed query
  async function start(body) {
    if (source) source.close()
    events.value = []
    error.value = ''
    running.value = true
    const res = await fetch(`${API}/api/runs`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      running.value = false
      error.value = (await res.json().catch(() => ({}))).detail || `Request failed (${res.status})`
      return
    }
    runId.value = (await res.json()).run_id
    source = new EventSource(`${API}/api/runs/${runId.value}/events`)
    source.addEventListener('event', (e) => {
      events.value.push(JSON.parse(e.data))
    })
    // The server closes the stream after the final stage event; the browser reports that as an error.
    source.onerror = () => {
      source.close()
      source = null
      running.value = false
    }
  }

  return { events, runId, running, error, start }
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

export async function fetchAgents() {
  return (await fetch(`${API}/api/agents`)).json()
}
