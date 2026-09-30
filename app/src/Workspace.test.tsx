import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Workspace from './Workspace'
import { WorkspaceClient } from './scope-client'

afterEach(() => cleanup())
const response = (value: unknown) => new Response(JSON.stringify(value), { status: 200 })
const makeSession = (brand = 'brand-a', version = 1) => ({
  user: { id: 'external-user', username: 'client-owner', platform_admin: false },
  organizations: [{ id: 'outside', name: 'Independent Studio', classification: 'EXTERNAL', role: 'OWNER' }],
  scope: { organization_id: 'outside', brand_profile_id: brand }, version, csrf: 'csrf',
})
const campaign = { id: 'c1', title: 'Independent launch', objective: 'Show a new product', audience: 'Business teams', offer: 'Book a demo', cta: 'Learn more' }
const detail = {
  campaign, director_plans: [{ id: 'plan1', plan_json: { strategy: 'Independent positioning' } }],
  storyboards: [{ id: 'board1' }], generation_requests: [{ id: 'request1', lifecycle_step: 9 }],
  generation_queue: [{ id: 'queue1' }], qa_runs: [{ id: 'qa1', overall_result: 'PASS' }],
  qa_reviews: [], generation_approvals: [], generation_spend_ledger: [],
  export_jobs: [], generation_attempts: [], render_jobs: [],
}
describe('approved authenticated CreativeOS interface', () => {
  it('uses the extracted approved logo and does not replace sign-in with the fixture app', async () => {
    const client = new WorkspaceClient(async () => response(null))
    render(<Workspace client={client} />)
    await screen.findByRole('heading', { name: /Make your next idea real/i })
    expect(screen.getByRole('img', { name: /CreativeOS.*Creative Production OS/i })).toHaveAttribute('src', '/creativeos-approved-wordmark.png')
    expect(document.querySelector('.platform-symbol')).toHaveAttribute('src', '/creativeos-approved-ribbon.png')
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByText(/One platform. Every brand/i)).toBeInTheDocument()
  })
  it('keeps external customer identity distinct and makes production navigation functional', async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input)
      if (path === '/api/session') return response(makeSession())
      if (path.startsWith('/api/brands')) return response([{ id: 'brand-a', name: 'External Blue' }])
      if (path === '/api/workspace') return response({ brand: { id: 'brand-a', name: 'External Blue', positioning: 'Independent value' }, campaigns: [campaign] })
      if (path === '/api/campaigns/c1') return response(detail)
      throw Error('Unexpected API path: ' + path)
    })
    const client = new WorkspaceClient(fetcher)
    render(<Workspace client={client} />)
    expect(await screen.findByText('Independent organization')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'External Blue' })).toBeInTheDocument()
    expect(screen.queryByText(/HABI/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Creative Director/i })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Independent launch' }))
    expect(await screen.findByRole('heading', { name: 'Independent launch' })).toBeInTheDocument()
    expect(screen.getByText('Independent value')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Governance stages' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Creative Director/i }))
    expect(screen.getByRole('button', { name: /Creative Director/i })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText('Local MOCK preview', { exact: false })).toBeDefined()
    expect(screen.getByRole('button', { name: 'Export approved preview' })).toBeEnabled()
    expect(screen.getByText('MANUAL ONLY')).toBeInTheDocument()
  })
  it('discards old campaign panels on server-authoritative cross-brand selection', async () => {
    let currentBrand = 'brand-a'
    let version = 1
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      if (path === '/api/session') return response(makeSession(currentBrand, version))
      if (path === '/api/context') {
        const body = JSON.parse(String(init?.body))
        currentBrand = body.brand_profile_id
        version += 1
        return response(makeSession(currentBrand, version))
      }
      if (path.startsWith('/api/brands')) return response([{ id: 'brand-a', name: 'External Blue' }, { id: 'brand-b', name: 'External Green' }])
      if (path === '/api/workspace') return response(currentBrand === 'brand-a'
        ? { brand: { id: 'brand-a', name: 'External Blue' }, campaigns: [campaign] }
        : { brand: { id: 'brand-b', name: 'External Green' }, campaigns: [] })
      if (path === '/api/campaigns/c1') return response(detail)
      throw Error('Unexpected API path: ' + path)
    })
    render(<Workspace client={new WorkspaceClient(fetcher)} />)
    await screen.findByRole('button', { name: 'Independent launch' })
    fireEvent.click(screen.getByRole('button', { name: 'Independent launch' }))
    await screen.findByRole('heading', { name: 'Independent launch' })
    fireEvent.change(screen.getByLabelText('Brand / product', { exact: true }), { target: { value: 'brand-b' } })
    await waitFor(() => expect(screen.getByRole('heading', { name: 'External Green' })).toBeInTheDocument())
    expect(screen.queryByRole('heading', { name: 'Independent launch' })).not.toBeInTheDocument()
    expect(screen.queryByText('Independent positioning')).not.toBeInTheDocument()
  })
})
