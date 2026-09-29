import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as api from './api'

vi.mock('./api', () => ({
  API_BASE: 'http://127.0.0.1:8765',
  listCampaigns: vi.fn(),
  createCampaign: vi.fn(),
  getCampaign: vi.fn(),
  updateCampaign: vi.fn(),
  advanceCampaign: vi.fn(),
  getBrand: vi.fn(),
  getDirector: vi.fn(),
  generateDirector: vi.fn(),
  approveDirector: vi.fn(),
  getStoryboard: vi.fn(),
  getAssetPlan: vi.fn(),
  createGenerationRequest: vi.fn(),
  getGenerationRequest: vi.fn(),
  getGovernance: vi.fn(),
}))

const campaign = {
  id: 'campaign-1',
  title: 'FleetPilot Meta Lead Campaign',
  objective: 'Generate qualified demo and inquiry interest from Philippine trucking and logistics owners.',
  audience: 'Philippine trucking and logistics owners/operators managing fleets and delivery operations.',
  offer: 'Book a guided FleetPilot demo.',
  cta: 'Book a FleetPilot demo',
  format: '30s Ad',
  duration_seconds: 30,
  aspect_ratio: '1:1',
  tone: 'clear, operational, credible',
  status: 'DIRECTOR',
}

const directorPlan = {
  id: 'plan-1',
  status: 'DRAFT',
  version: 1,
  provider_mode: 'MOCK',
  output_json: {
    strategy: { campaign_angle: 'Product truth first' },
    hooks: ['Profit leaks start where visibility ends.'],
    script: [
      { scene_number: 1, voiceover: 'Hook', on_screen_copy: 'Hook', timing_seconds: 4 },
      { scene_number: 2, voiceover: 'Product', on_screen_copy: 'Command Center', timing_seconds: 4 },
    ],
    scene_plan: [
      { scene_number: 1, title: 'Hook', duration_seconds: 4, scene_type: 'AI_VIDEO', recommended_generation_method: 'GENERATIVE' },
      { scene_number: 2, title: 'Command Center', duration_seconds: 4, scene_type: 'REAL_UI', recommended_generation_method: 'COMPOSITING_ONLY' },
      { scene_number: 3, title: 'Live Fleet', duration_seconds: 4, scene_type: 'REAL_UI', recommended_generation_method: 'COMPOSITING_ONLY' },
      { scene_number: 4, title: 'Dispatch', duration_seconds: 4, scene_type: 'REAL_UI', recommended_generation_method: 'COMPOSITING_ONLY' },
      { scene_number: 5, title: 'Accountability', duration_seconds: 3, scene_type: 'REAL_UI', recommended_generation_method: 'COMPOSITING_ONLY' },
      { scene_number: 6, title: 'Profitability', duration_seconds: 4, scene_type: 'REAL_UI', recommended_generation_method: 'COMPOSITING_ONLY' },
      { scene_number: 7, title: 'Intelligence', duration_seconds: 4, scene_type: 'REAL_UI', recommended_generation_method: 'COMPOSITING_ONLY' },
      { scene_number: 8, title: 'Close', duration_seconds: 3, scene_type: 'TYPOGRAPHY', recommended_generation_method: 'GENERATIVE' },
    ],
  },
}

const storyboard = {
  storyboard: { id: 'board-1', title: 'FleetPilot Meta Lead Campaign', status: 'READY' },
  scenes: directorPlan.output_json.scene_plan.map(scene => ({
    id: 'scene-' + scene.scene_number,
    position: scene.scene_number,
    title: scene.title,
    duration_seconds: scene.duration_seconds,
    scene_type: scene.scene_type,
    generation_method: scene.recommended_generation_method,
    immutable_ui: scene.scene_type === 'REAL_UI',
    script: scene.title,
  })),
  duration_seconds: 30,
  campaign_duration_seconds: 30,
  aspect_ratio: '1:1',
}
const assetPlan = {
  campaign_id: campaign.id,
  quantity: 2,
  items: [
    {
      kind: 'GENERATED',
      purpose: 'FleetPilot Meta lead-generation campaign creative',
      status: 'NOT_GENERATED',
      provider: 'HIGGSFIELD',
      model: 'marketing-studio/image',
      format: 'image',
      aspect_ratio: '1:1',
      quantity: 1,
    },
    {
      kind: 'REAL_UI',
      purpose: 'Command Center',
      status: 'REQUIRED',
      provider: 'COMPOSITING',
      model: null,
      format: 'approved product UI',
      aspect_ratio: '1:1',
      quantity: 1,
    },
  ],
}

const generationRequest = {
  id: 'request-1',
  lifecycle_state: 'COSTED',
  provider: 'HIGGSFIELD',
  model: 'marketing-studio/image',
  quantity: 1,
  estimated_cost_minor: 190,
  estimated_cost: 'USD 0.0190',
  currency: 'USD',
  approval_required: true,
  approval_state: 'COST_APPROVAL_REQUIRED',
  campaign_duration_seconds: 30,
  aspect_ratio: '1:1',
  provider_submissions: 0,
  generation_attempts: 0,
  budget_reservations: 0,
  spend_events: 0,
  actual_spend: 'USD 0.00',
}

const governance = {
  automated_qa: 'NOT_GENERATED',
  provenance: 'NOT_GENERATED',
  human_review: 'WAITING_FOR_QA',
  export: 'NOT_AVAILABLE',
  publishing: 'MANUAL_ONLY',
  auto_publish: false,
}

const mocked = vi.mocked(api)

function resetApi() {
  mocked.listCampaigns.mockResolvedValue({ campaigns: [campaign] })
  mocked.createCampaign.mockResolvedValue({ campaign })
  mocked.getCampaign.mockResolvedValue({ campaign })
  mocked.updateCampaign.mockResolvedValue({ campaign })
  mocked.advanceCampaign.mockImplementation(async (_id, stage) => ({
    campaign: { ...campaign, status: stage },
  }))
  mocked.getBrand.mockResolvedValue({
    brand: {
      id: 'brand-fleetpilot-golden',
      name: 'FleetPilot',
      positioning: 'One operating system for fleet visibility, dispatch control, accountability, and profitability.',
      audience: campaign.audience,
      core_promise: 'Improved fleet visibility, dispatch control, trip accountability, and profitability.',
      tagline: 'Track. Dispatch. Control. Grow.',
      messaging_json: ['operational visibility', 'trip profitability'],
      default_immutable_ui: true,
    },
  })
  mocked.getDirector.mockResolvedValue({ plan: directorPlan })
  mocked.generateDirector.mockResolvedValue({ plan: directorPlan })
  mocked.approveDirector.mockResolvedValue({
    plan: { ...directorPlan, status: 'APPROVED' },
    storyboard: storyboard.storyboard,
    scenes: storyboard.scenes,
  })
  mocked.getStoryboard.mockResolvedValue(storyboard)
  mocked.getAssetPlan.mockResolvedValue(assetPlan)
  mocked.createGenerationRequest.mockResolvedValue({ generation_request: generationRequest })
  mocked.getGenerationRequest.mockResolvedValue({ generation_request: generationRequest })
  mocked.getGovernance.mockResolvedValue({ governance })
}

async function renderAt(screenName: string) {
  window.history.replaceState({}, '', '/?campaign=' + campaign.id + '&screen=' + screenName)
  render(<App />)
  await waitFor(() => expect(mocked.getCampaign).toHaveBeenCalled())
}

beforeEach(() => {
  vi.clearAllMocks()
  resetApi()
  window.history.replaceState({}, '', '/?screen=home')
})

afterEach(() => cleanup())
describe('CreativeOS SaaS runtime bridge', () => {
  it('renders saved campaigns and can create/select a campaign', async () => {
    render(<App />)
    expect(await screen.findByRole('heading', { name: /Create something/i })).toBeInTheDocument()
    expect(await screen.findByText('FleetPilot Meta Lead Campaign')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Create FleetPilot Campaign/i }))
    await waitFor(() => expect(mocked.createCampaign).toHaveBeenCalledTimes(1))
    expect(window.location.search).toContain('campaign=campaign-1')
    expect(window.location.search).toContain('screen=objective')
  })

  it('restores campaign and workflow screen from the URL', async () => {
    await renderAt('generate')
    expect(await screen.findByRole('heading', { name: /Cost is visible/i })).toBeInTheDocument()
    expect(window.location.search).toContain('screen=generate')
  })

  it('blocks empty required objective before backend progression', async () => {
    await renderAt('objective')
    const input = await screen.findByLabelText('Campaign objective')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /Save Objective/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/objective is required/i)
    expect(mocked.updateCampaign).not.toHaveBeenCalled()
    expect(mocked.advanceCampaign).not.toHaveBeenCalled()
  })

  it('persists objective through API then advances workflow', async () => {
    await renderAt('objective')
    const input = await screen.findByLabelText('Campaign objective')
    fireEvent.change(input, { target: { value: 'Qualified demo inquiries' } })
    fireEvent.click(screen.getByRole('button', { name: /Save Objective/i }))
    await waitFor(() =>
      expect(mocked.updateCampaign).toHaveBeenCalledWith(
        campaign.id,
        expect.objectContaining({ objective: 'Qualified demo inquiries' }),
      ),
    )
    expect(mocked.advanceCampaign).toHaveBeenCalledWith(campaign.id, 'AUDIENCE')
  })

  it('shows authoritative 30s and 1:1 Director controls', async () => {
    await renderAt('director')
    await screen.findByText(/Turn the authoritative brief/i)
    expect(screen.getAllByText('30s', { selector: 'b' }).length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('1:1', { selector: 'b' }).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Planned duration/i)).toBeInTheDocument()
  })

  it('renders storyboard with propagated 30s and 1:1 values', async () => {
    await renderAt('storyboard')
    expect(await screen.findByText(/30s total/)).toBeInTheDocument()
    expect(screen.getAllByText('1:1').length).toBeGreaterThan(0)
    expect(screen.getByText(/Storyboard duration/i)).toBeInTheDocument()
  })
  it('renders campaign-level Asset Plan with provider, model, quantity and ratio', async () => {
    await renderAt('assets')
    expect(await screen.findByRole('heading', { name: /Know exactly/i })).toBeInTheDocument()
    expect(screen.getByText('HIGGSFIELD')).toBeInTheDocument()
    expect(screen.getByText('marketing-studio/image')).toBeInTheDocument()
    expect(screen.getAllByText(/1:1/).length).toBeGreaterThan(0)
    expect(screen.getAllByText('1').length).toBeGreaterThan(0)
  })

  it('shows exact governed cost and COST_APPROVAL_REQUIRED with zero spend', async () => {
    await renderAt('generate')
    expect(await screen.findByText('COST_APPROVAL_REQUIRED')).toBeInTheDocument()
    expect(screen.getByText('HIGGSFIELD / marketing-studio/image')).toBeInTheDocument()
    expect(screen.getByText('USD 0.0190', { selector: 'b' })).toBeInTheDocument()
    expect(screen.getByText(/Actual spend · USD 0.00/)).toBeInTheDocument()
    expect(screen.getAllByText('0', { selector: 'b' }).length).toBeGreaterThanOrEqual(4)
  })

  it('reopens the same generation request idempotently without approval action', async () => {
    await renderAt('generate')
    const button = await screen.findByRole('button', { name: /Re-open same idempotent request/i })
    fireEvent.click(button)
    await waitFor(() => expect(mocked.createGenerationRequest).toHaveBeenCalledTimes(1))
    expect(screen.getByText('COST_APPROVAL_REQUIRED')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /approve cost/i })).not.toBeInTheDocument()
  })

  it('separates automated QA, provenance, human review, export and publishing', async () => {
    await renderAt('review')
    expect(await screen.findByRole('heading', { name: /QA ≠ Human Review/i })).toBeInTheDocument()
    expect(screen.getByText('Automated QA')).toBeInTheDocument()
    expect(screen.getByText('Provenance')).toBeInTheDocument()
    expect(screen.getByText('Human Review')).toBeInTheDocument()
    expect(screen.getByText('Export')).toBeInTheDocument()
    expect(screen.getByText('Publishing')).toBeInTheDocument()
    expect(screen.getByText(/Automatic publishing: DISABLED/)).toBeInTheDocument()
  })

  it('keeps identifiable navigation labels for responsive layouts', async () => {
    await renderAt('director')
    expect(await screen.findByRole('navigation', { name: /CreativeOS navigation/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Generate \/ Costs/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /QA \/ Review/i })).toBeInTheDocument()
  })
})
