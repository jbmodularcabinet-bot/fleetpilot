export interface Row {
  id: string
  name?: string
  title?: string
  entity_type?: string
  lifecycle_step?: number
  state?: string
  [key: string]: unknown
}
export interface Session {
  user: { id: string; username: string; platform_admin: boolean }
  organizations: { id: string; name: string; classification: string; role: string }[]
  scope: { organization_id: string; brand_profile_id: string | null } | null
  version: number
  csrf: string
}
export interface Detail {
  campaign: Row
  director_plans: Row[]
  storyboards: Row[]
  generation_requests: Row[]
  generation_queue: Row[]
  qa_runs: Row[]
  qa_reviews: Row[]
  generation_approvals: Row[]
  generation_spend_ledger: Row[]
  export_jobs: Row[]
  generation_attempts: Row[]
  render_jobs: Row[]
}
export interface AdoptionPreview {
  id: string; digest: string; brand_name: string; organization_id: string
  counts: Record<string, number>; conflicts: string[]; notice: string; legacy_tenant_labels: string[]
}
interface State {
  session: Session | null
  brands: Row[]
  workspace: { brand: Row; campaigns: Row[] } | null
  detail: Detail | null
  inventory: { brands: Row[]; unassigned_assets: number; notice: string } | null
  preview: AdoptionPreview | null
  mediaUrl: string | null
  busy: boolean
  error: string
}
class RequestError extends Error {
  status: number
  constructor(message: string, status: number) { super(message); this.status = status }
}
class Superseded extends Error {}
const empty = (): State => ({
  session: null, brands: [], workspace: null, detail: null, inventory: null, preview: null, mediaUrl: null, busy: false, error: '',
})

export class WorkspaceClient {
  private state = empty()
  private epoch = 0
  private listeners = new Set<() => void>()
  private broadcaster: (() => void) | null = null
  private fetcher: typeof fetch
  constructor(fetcher: typeof fetch = (...args) => fetch(...args)) { this.fetcher = fetcher }
  snapshot = () => this.state
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener) } }
  private put(patch: Partial<State>) {
    if ('mediaUrl' in patch || patch.detail === null) {
      if (this.state.mediaUrl) URL.revokeObjectURL(this.state.mediaUrl)
      if (!('mediaUrl' in patch)) patch.mediaUrl = null
    }
    this.state = { ...this.state, ...patch }
    this.listeners.forEach(listener => listener())
  }
  private begin(clear = false) {
    const epoch = ++this.epoch
    this.put(clear ? { ...empty(), session: this.state.session, busy: true } : { busy: true, error: '' })
    return epoch
  }
  private current(epoch: number) { if (epoch !== this.epoch) throw new Superseded() }
  private async request<T>(epoch: number, path: string, body?: unknown, blob = false): Promise<T> {
    const session = this.state.session
    const headers: Record<string, string> = {}
    if (session) {
      headers['X-Scope-Version'] = String(session.version)
      headers['X-CSRF-Token'] = session.csrf
    }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    const result = await this.fetcher(path, {
      method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    this.current(epoch)
    if (!result.ok) {
      const value = await result.json()
      throw new RequestError(value.error || 'Request failed', result.status)
    }
    const value = blob ? await result.blob() : await result.json()
    this.current(epoch)
    return value as T
  }
  private async populate(epoch: number, session: Session) {
    this.current(epoch)
    this.put({ session })
    if (!session.scope) return
    const brands = await this.request<Row[]>(epoch, '/api/brands?organization_id=' + encodeURIComponent(session.scope.organization_id))
    this.put({ brands })
    if (session.scope.brand_profile_id) {
      const workspace = await this.request<State['workspace']>(epoch, '/api/workspace')
      this.put({ workspace })
    }
  }
  private async run(epoch: number, operation: () => Promise<void>) {
    try { await operation() } catch (error) {
      if (epoch !== this.epoch || error instanceof Superseded) return
      const message = error instanceof Error ? error.message : 'Request failed'
      if (error instanceof RequestError && [401, 403, 409].includes(error.status)) {
        // Clear every dependent view before reconciling. Never replay the rejected mutation.
        this.put({ ...empty(), error: message, busy: true })
        try {
          const session = await this.request<Session>(epoch, '/api/session')
          await this.populate(epoch, session)
        } catch { /* Remain signed out/cleared if session cannot be validated. */ }
      }
      if (epoch === this.epoch) this.put({ error: message })
    } finally {
      if (epoch === this.epoch) this.put({ busy: false })
    }
  }
  refresh = async () => {
    const epoch = this.begin(true)
    await this.run(epoch, async () => this.populate(epoch, await this.request<Session>(epoch, '/api/session')))
  }
  externalChange = () => this.refresh()
  async login(username: string, password: string) {
    const epoch = this.begin(true)
    await this.run(epoch, async () => {
      const session = await this.request<Session>(epoch, '/api/login', { username, password })
      await this.populate(epoch, session)
      this.broadcaster?.()
    })
  }
  async logout() {
    const epoch = this.begin(true)
    await this.run(epoch, async () => {
      await this.request(epoch, '/api/logout', {})
      this.put(empty())
      this.broadcaster?.()
    })
  }
  async select(organization_id: string, brand_profile_id: string | null) {
    const epoch = this.begin(true)
    await this.run(epoch, async () => {
      const session = await this.request<Session>(epoch, '/api/context', { organization_id, brand_profile_id })
      this.broadcaster?.()
      await this.populate(epoch, session)
    })
  }
  async openCampaign(id: string) {
    const epoch = this.begin()
    this.put({ detail: null })
    await this.run(epoch, async () => this.put({ detail: await this.request<Detail>(epoch, '/api/campaigns/' + encodeURIComponent(id)) }))
  }
  async createCampaign(values: Record<string, string>) {
    const epoch = this.begin()
    await this.run(epoch, async () => {
      const campaign = await this.request<Row>(epoch, '/api/campaigns', values)
      const workspace = await this.request<State['workspace']>(epoch, '/api/workspace')
      const detail = await this.request<Detail>(epoch, '/api/campaigns/' + campaign.id)
      this.put({ workspace, detail })
    })
  }
  async action(path: string, body: unknown = {}) {
    const campaignId = this.state.detail?.campaign.id
    const epoch = this.begin()
    await this.run(epoch, async () => {
      const result = await this.request<{ failure?: string }>(epoch, path, body)
      if (campaignId) this.put({ detail: await this.request<Detail>(epoch, '/api/campaigns/' + campaignId) })
      if (result.failure) this.put({ error: result.failure })
    })
  }
  async inventory() {
    const epoch = this.begin()
    this.put({ preview: null })
    await this.run(epoch, async () => this.put({ inventory: await this.request<State['inventory']>(epoch, '/api/adoption') }))
  }
  async preview(legacy_brand_id: string) {
    const epoch = this.begin()
    this.put({ preview: null })
    await this.run(epoch, async () => this.put({ preview: await this.request<AdoptionPreview>(epoch, '/api/adoption/preview', { legacy_brand_id }) }))
  }
  async confirmAdoption() {
    const preview = this.state.preview
    if (!preview) return
    const epoch = this.begin()
    await this.run(epoch, async () => {
      await this.request(epoch, '/api/adoption/confirm', { preview_id: preview.id, digest: preview.digest, confirmation: true })
      this.put({ preview: null, inventory: null, detail: null })
      this.broadcaster?.()
      await this.populate(epoch, await this.request<Session>(epoch, '/api/session'))
    })
  }
  async viewPreview(id: string) {
    const epoch = this.begin()
    await this.run(epoch, async () => {
      const file = await this.request<Blob>(epoch, '/api/requests/' + id + '/preview', undefined, true)
      this.put({ mediaUrl: URL.createObjectURL(file) })
    })
  }
  async download(id: string) {
    const epoch = this.begin()
    await this.run(epoch, async () => {
      const file = await this.request<Blob>(epoch, '/api/exports/' + id + '/download', undefined, true)
      const url = URL.createObjectURL(file)
      const anchor = document.createElement('a')
      anchor.href = url; anchor.download = 'creativeos-local-mock-preview.mp4'; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    })
  }
  connect() {
    const channel = typeof BroadcastChannel === 'undefined' ? null : new BroadcastChannel('creativeos-context')
    const notify = () => { void this.externalChange() }
    if (channel) channel.onmessage = notify
    const storage = (event: StorageEvent) => { if (event.key === 'creativeos.context.changed') notify() }
    this.broadcaster = () => {
      channel?.postMessage('changed')
      try { localStorage.setItem('creativeos.context.changed', String(Date.now()) + Math.random()) } catch { /* Optional notification only. */ }
    }
    window.addEventListener('storage', storage)
    window.addEventListener('focus', notify)
    const visibility = () => { if (document.visibilityState === 'visible') notify() }
    document.addEventListener('visibilitychange', visibility)
    return () => {
      ++this.epoch
      channel?.close(); this.broadcaster = null
      window.removeEventListener('storage', storage)
      window.removeEventListener('focus', notify)
      document.removeEventListener('visibilitychange', visibility)
    }
  }
}
