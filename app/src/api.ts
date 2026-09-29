export const API_BASE = import.meta.env.VITE_CREATIVEOS_API_BASE || 'http://127.0.0.1:8765'

export type Campaign = {
  id: string
  title: string
  objective: string
  audience: string
  offer: string
  cta: string
  format: string
  duration_seconds: number
  aspect_ratio: string
  tone: string
  status: string
}

export type Brand = {
  id: string
  name: string
  positioning: string
  audience: string
  core_promise: string
  tagline: string
  messaging_json: string[] | string
  default_immutable_ui: number | boolean
}

export type DirectorPlan = {
  id: string
  status: string
  version: number
  provider_mode: string
  output_json: {
    strategy: Record<string, unknown>
    hooks: string[]
    script: Array<{
      scene_number: number
      voiceover: string
      on_screen_copy: string
      timing_seconds: number
    }>
    scene_plan: Array<{
      scene_number: number
      title: string
      duration_seconds: number
      scene_type: string
      recommended_generation_method: string
    }>
  }
}
export type StoryboardData = {
  storyboard: { id: string; title: string; status: string }
  scenes: Array<{
    id: string
    position: number
    title: string
    duration_seconds: number
    scene_type: string
    generation_method: string
    immutable_ui: number | boolean
    script: string
  }>
  duration_seconds: number
  campaign_duration_seconds: number
  aspect_ratio: string
}

export type AssetPlan = {
  campaign_id: string
  quantity: number
  items: Array<{
    kind: string
    purpose: string
    status: string
    provider: string
    model: string | null
    format: string
    aspect_ratio: string
    quantity: number
  }>
}

export type GenerationRequest = {
  id: string
  lifecycle_state: string
  provider: string
  model: string
  quantity: number
  estimated_cost_minor: number
  estimated_cost: string
  currency: string
  approval_required: boolean
  approval_state: string
  campaign_duration_seconds: number
  aspect_ratio: string
  provider_submissions: number
  generation_attempts: number
  budget_reservations: number
  spend_events: number
  actual_spend: string | null
}
export type Governance = {
  automated_qa: string
  provenance: string
  human_review: string
  export: string
  publishing: string
  auto_publish: boolean
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(API_BASE + path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
  })
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.error || 'CreativeOS API request failed')
  }
  return payload as T
}

export async function listCampaigns() {
  return request<{ campaigns: Campaign[] }>('/api/campaigns')
}

export async function createCampaign(title: string, objective: string) {
  return request<{ campaign: Campaign }>('/api/campaigns', {
    method: 'POST',
    body: JSON.stringify({ title, objective }),
  })
}

export async function getCampaign(id: string) {
  return request<{ campaign: Campaign }>('/api/campaigns/' + id)
}

export async function updateCampaign(
  id: string,
  values: Partial<Campaign>,
) {
  return request<{ campaign: Campaign }>('/api/campaigns/' + id, {
    method: 'PATCH',
    body: JSON.stringify(values),
  })
}
export async function advanceCampaign(id: string, stage: string) {
  return request<{ campaign: Campaign }>(
    '/api/campaigns/' + id + '/advance',
    {
      method: 'POST',
      body: JSON.stringify({ stage }),
    },
  )
}

export async function getBrand(id: string) {
  return request<{ brand: Brand }>('/api/campaigns/' + id + '/brand')
}

export async function getDirector(id: string) {
  return request<{ plan: DirectorPlan | null }>(
    '/api/campaigns/' + id + '/director',
  )
}

export async function generateDirector(id: string) {
  return request<{ plan: DirectorPlan }>(
    '/api/campaigns/' + id + '/director',
    { method: 'POST', body: '{}' },
  )
}

export async function approveDirector(id: string) {
  return request<{
    plan: DirectorPlan
    storyboard: StoryboardData['storyboard']
    scenes: StoryboardData['scenes']
  }>('/api/campaigns/' + id + '/director/approve', {
    method: 'POST',
    body: '{}',
  })
}

export async function getStoryboard(id: string) {
  return request<StoryboardData>('/api/campaigns/' + id + '/storyboard')
}

export async function getAssetPlan(id: string) {
  return request<AssetPlan>('/api/campaigns/' + id + '/asset-plan', {
    method: 'POST',
    body: '{}',
  })
}

export async function createGenerationRequest(id: string) {
  return request<{ generation_request: GenerationRequest }>(
    '/api/campaigns/' + id + '/generation-request',
    { method: 'POST', body: '{}' },
  )
}

export async function getGenerationRequest(id: string) {
  return request<{ generation_request: GenerationRequest | null }>(
    '/api/campaigns/' + id + '/generation-request',
  )
}

export async function getGovernance(id: string) {
  return request<{ governance: Governance }>(
    '/api/campaigns/' + id + '/governance',
  )
}
