import { describe, expect, it, vi } from 'vitest'
import { WorkspaceClient } from './scope-client'

const session = (version = 1, brand = 'a') => ({
  user: { id: 'u', username: 'alice', platform_admin: false },
  organizations: [{ id: 'o', name: 'Org', classification: 'EXTERNAL', role: 'OWNER' }],
  scope: { organization_id: 'o', brand_profile_id: brand }, version, csrf: 'csrf',
})
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status })
const deferred = () => {
  let resolve!: (value: Response) => void
  const promise = new Promise<Response>(r => { resolve = r })
  return { promise, resolve }
}
describe('authoritative workspace client', () => {
  it('discards late campaign responses after a brand switch and clears all old state immediately', async () => {
    const slow = deferred()
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/session') return response(session())
      if (path.startsWith('/api/brands')) return response([{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }])
      if (path === '/api/context') return response(session(2, 'b'))
      if (path === '/api/campaigns/old') return slow.promise
      return response({ brand: { id: 'a', name: 'A' }, campaigns: [] })
    })
    const client = new WorkspaceClient(fetcher)
    await client.refresh()
    const opening = client.openCampaign('old')
    const switching = client.select('o', 'b')
    expect(client.snapshot().detail).toBeNull()
    expect(client.snapshot().workspace).toBeNull()
    await switching
    slow.resolve(response({ campaign: { id: 'old', title: 'Private old campaign' }, qa_runs: [{ id: 'old-qa' }] }))
    await opening
    expect(client.snapshot().detail).toBeNull()
    expect(client.snapshot().session?.scope?.brand_profile_id).toBe('b')
  })
  it('sends server context revision and CSRF, never retries stale mutations under a new brand', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === '/api/session') return response(session())
      if (String(input).startsWith('/api/brands')) return response([])
      if (String(input) === '/api/campaigns') return response({ error: 'Workspace changed', code: 'STALE_SCOPE' }, 409)
      return response({ brand: { id: 'a', name: 'A' }, campaigns: [] })
    })
    const client = new WorkspaceClient(fetcher)
    await client.refresh()
    await client.createCampaign({ title: 'A' })
    const calls = fetcher.mock.calls.filter(call => String(call[0]) === '/api/campaigns')
    expect(calls).toHaveLength(1)
    const init = (calls[0] as unknown as [unknown, RequestInit])[1]
    expect(init.credentials).toBe('same-origin')
    expect(init.headers).toMatchObject({ 'X-Scope-Version': '1', 'X-CSRF-Token': 'csrf' })
    expect(client.snapshot().detail).toBeNull()
  })
  it('clears campaign, queue, QA, approvals, costs and export state on external context notification', async () => {
    const pending = deferred()
    let refreshCount = 0
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input) === '/api/session') return ++refreshCount === 1 ? response(session()) : pending.promise
      if (String(input).startsWith('/api/brands')) return response([])
      if (String(input).startsWith('/api/campaigns/')) return response({
        campaign: { id: 'c', title: 'C' }, generation_queue: [{ id: 'q' }],
        qa_runs: [{ id: 'qa' }], generation_approvals: [{ id: 'ap' }],
        generation_spend_ledger: [{ id: 'cost' }], export_jobs: [{ id: 'export' }],
      })
      return response({ brand: { id: 'a', name: 'A' }, campaigns: [] })
    })
    const client = new WorkspaceClient(fetcher)
    await client.refresh()
    await client.openCampaign('c')
    expect(client.snapshot().detail).not.toBeNull()
    const updating = client.externalChange()
    expect(client.snapshot().detail).toBeNull()
    expect(client.snapshot().workspace).toBeNull()
    pending.resolve(response(session(2, 'b')))
    await updating
    expect(client.snapshot().session?.version).toBe(2)
  })
  it('treats an unauthenticated initial session check as a normal signed-out state', async () => {
    const fetcher = vi.fn(async () => response({ error: 'Sign in required' }, 401))
    const client = new WorkspaceClient(fetcher)
    await client.refresh()
    expect(client.snapshot().session).toBeNull()
    expect(client.snapshot().error).toBe('')
    expect(client.snapshot().busy).toBe(false)
  })
})
