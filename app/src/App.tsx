import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'
import {
  advanceCampaign,
  approveDirector,
  createCampaign,
  createGenerationRequest,
  generateDirector,
  getAssetPlan,
  getBrand,
  getCampaign,
  getDirector,
  getGenerationRequest,
  getGovernance,
  getStoryboard,
  listCampaigns,
  updateCampaign,
  type AssetPlan,
  type Brand,
  type Campaign,
  type DirectorPlan,
  type GenerationRequest,
  type Governance,
  type StoryboardData,
} from './api'

type Screen =
  | 'home'
  | 'objective'
  | 'audience'
  | 'offer'
  | 'brand'
  | 'director'
  | 'script'
  | 'storyboard'
  | 'assets'
  | 'generate'
  | 'review'

const scenario =
  'Create a Meta ad campaign for Philippine trucking and logistics owners that drives qualified demo inquiries.'

const stageScreen: Record<string, Screen> = {
  OBJECTIVE: 'objective',
  AUDIENCE: 'audience',
  OFFER: 'offer',
  BRAND: 'brand',
  DIRECTOR: 'director',
  SCRIPT: 'script',
  STORYBOARD: 'storyboard',
  ASSET_PLAN: 'assets',
  GENERATION_REQUEST: 'generate',
  COST_APPROVAL_REQUIRED: 'generate',
}

const workflow: Array<[Screen, string]> = [
  ['objective', 'Objective'],
  ['audience', 'Audience'],
  ['offer', 'Offer'],
  ['brand', 'Brand Brain'],
  ['director', 'Director'],
  ['script', 'Script'],
  ['storyboard', 'Storyboard'],
  ['assets', 'Asset Plan'],
  ['generate', 'Generation'],
  ['review', 'Governance'],
]

const screenLabels: Record<Screen, string> = {
  home: 'Command Center',
  objective: 'Objective',
  audience: 'Audience',
  offer: 'Offer',
  brand: 'Brand Brain',
  director: 'Creative Studio',
  script: 'Script',
  storyboard: 'Storyboard',
  assets: 'Assets',
  generate: 'Generation',
  review: 'Governance',
}

const stateLabels: Record<string, string> = {
  NOT_GENERATED: 'Not generated yet',
  WAITING_FOR_QA: 'Waiting for QA',
  NOT_AVAILABLE: 'Not available yet',
  MANUAL_ONLY: 'Manual publishing only',
  DISABLED: 'Disabled',
  COST_APPROVAL_REQUIRED: 'Awaiting cost approval',
  COSTED: 'Costed',
  GENERATED: 'Generated',
  AVAILABLE: 'Available',
  READY_FOR_EXPORT: 'Ready for export',
  DRAFT: 'Draft',
  APPROVED: 'Approved',
  READY: 'Ready',
  EXISTING: 'Existing',
  REQUIRED: 'Required',
  PENDING: 'Pending',
  REAL_UI: 'Real UI',
  AI_VIDEO: 'AI video',
  AI_IMAGE: 'AI image',
  COMPOSITING_ONLY: 'Compositing only',
  TYPOGRAPHY: 'Typography',
}

function humanizeState(value: string | null | undefined): string {
  if (!value) return 'Not available yet'
  if (stateLabels[value]) return stateLabels[value]
  const normalized = value.replaceAll('_', ' ').toLowerCase()
  return normalized.charAt(0).toUpperCase() + normalized.slice(1)
}

function sidebarSection(screen: Screen): Screen {
  if (screen === 'objective' || screen === 'audience' || screen === 'offer') {
    return 'objective'
  }
  if (screen === 'director' || screen === 'script' || screen === 'storyboard') {
    return 'director'
  }
  return screen
}

function screenFromUrl(): Screen {
  const raw = new URLSearchParams(window.location.search).get('screen')
  return workflow.some(([id]) => id === raw) || raw === 'home'
    ? (raw as Screen)
    : 'home'
}

function App() {
  const [screen, setScreen] = useState<Screen>(screenFromUrl())
  const [campaign, setCampaign] = useState<Campaign | null>(null)
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [homeBrief, setHomeBrief] = useState(scenario)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const navigate = useCallback(
    (next: Screen, campaignId = campaign?.id, replace = false) => {
      const params = new URLSearchParams()
      if (campaignId) params.set('campaign', campaignId)
      params.set('screen', next)
      const url = '?' + params.toString()
      if (replace) window.history.replaceState({}, '', url)
      else window.history.pushState({}, '', url)
      setScreen(next)
      setError('')
    },
    [campaign?.id],
  )

  const reloadCampaign = useCallback(async (id: string) => {
    const response = await getCampaign(id)
    setCampaign(response.campaign)
    return response.campaign
  }, [])

  const loadLocation = useCallback(async () => {
    const params = new URLSearchParams(window.location.search)
    const campaignId = params.get('campaign')
    if (!campaignId) {
      setCampaign(null)
      setScreen(screenFromUrl())
      return
    }
    try {
      const loaded = await reloadCampaign(campaignId)
      const requested = params.get('screen')
      const restored =
        requested && (workflow.some(([id]) => id === requested) || requested === 'home')
          ? (requested as Screen)
          : stageScreen[loaded.status] || 'objective'
      setScreen(restored)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setCampaign(null)
      setScreen('home')
    }
  }, [reloadCampaign])

  useEffect(() => {
    listCampaigns().then(r => setCampaigns(r.campaigns)).catch(() => {})
    const timer = window.setTimeout(() => void loadLocation(), 0)
    const onPop = () => void loadLocation()
    window.addEventListener('popstate', onPop)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('popstate', onPop)
    }
  }, [loadLocation])

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setError('')
    try {
      await action()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const createFleetPilotCampaign = () =>
    run(async () => {
      const response = await createCampaign(
        'FleetPilot Meta Lead Campaign',
        homeBrief,
      )
      setCampaign(response.campaign)
      setCampaigns(prev => {
        const next = prev.filter(x => x.id !== response.campaign.id)
        return [response.campaign, ...next]
      })
      navigate('objective', response.campaign.id)
    })

  const selectCampaign = (item: Campaign) =>
    run(async () => {
      const loaded = await reloadCampaign(item.id)
      navigate(stageScreen[loaded.status] || 'objective', loaded.id)
    })

  const saveAndAdvance = (
    values: Partial<Campaign>,
    stage: string,
    next: Screen,
  ) =>
    run(async () => {
      if (!campaign) throw new Error('Campaign is required')
      const updated = await updateCampaign(campaign.id, values)
      const advanced = await advanceCampaign(campaign.id, stage)
      setCampaign({ ...updated.campaign, status: advanced.campaign.status })
      navigate(next, campaign.id)
    })

  const currentIndex = useMemo(
    () => workflow.findIndex(([id]) => id === screen),
    [screen],
  )

  return (
    <div className="app-shell">
      <Sidebar
        active={screen}
        campaign={campaign}
        onNavigate={next => navigate(next)}
      />
      <main className="workspace">
        <Topbar campaign={campaign} busy={busy} screen={screen} />
        {campaign && screen !== 'home' && (
          <Progress activeIndex={currentIndex} />
        )}
        {error && <div className="error-banner" role="alert">{error}</div>}
        {screen === 'home' && (
          <Home
            value={homeBrief}
            onChange={setHomeBrief}
            onCreate={createFleetPilotCampaign}
            campaigns={campaigns}
            onSelect={selectCampaign}
            busy={busy}
          />
        )}
        {campaign && screen === 'objective' && (
          <ObjectiveScreen
            campaign={campaign}
            busy={busy}
            onNext={objective => {
              if (!objective.trim()) {
                setError('Campaign objective is required')
                return
              }
              void saveAndAdvance({ objective }, 'AUDIENCE', 'audience')
            }}
          />
        )}
        {campaign && screen === 'audience' && (
          <AudienceScreen
            campaign={campaign}
            busy={busy}
            onNext={audience => {
              if (!audience.trim()) {
                setError('Audience is required')
                return
              }
              void saveAndAdvance({ audience }, 'OFFER', 'offer')
            }}
          />
        )}
        {campaign && screen === 'offer' && (
          <OfferScreen
            campaign={campaign}
            busy={busy}
            onNext={values => {
              if (!values.offer?.trim()) {
                setError('Core offer is required')
                return
              }
              void saveAndAdvance(values, 'BRAND', 'brand')
            }}
          />
        )}
        {campaign && screen === 'brand' && (
          <BrandScreen
            campaign={campaign}
            busy={busy}
            onContinue={() =>
              void run(async () => {
                const response = await advanceCampaign(campaign.id, 'DIRECTOR')
                setCampaign(response.campaign)
                navigate('director', campaign.id)
              })
            }
          />
        )}
        {campaign && screen === 'director' && (
          <DirectorScreen
            campaign={campaign}
            busy={busy}
            onCampaign={setCampaign}
            onContinue={() => navigate('script', campaign.id)}
            run={run}
          />
        )}
        {campaign && screen === 'script' && (
          <ScriptScreen
            campaign={campaign}
            busy={busy}
            onContinue={() =>
              void run(async () => {
                const response = await advanceCampaign(campaign.id, 'STORYBOARD')
                setCampaign(response.campaign)
                navigate('storyboard', campaign.id)
              })
            }
          />
        )}
        {campaign && screen === 'storyboard' && (
          <StoryboardScreen
            campaign={campaign}
            busy={busy}
            onContinue={() => navigate('assets', campaign.id)}
          />
        )}
        {campaign && screen === 'assets' && (
          <AssetPlanScreen
            campaign={campaign}
            busy={busy}
            onCampaign={setCampaign}
            onContinue={() =>
              void run(async () => {
                const response = await advanceCampaign(
                  campaign.id,
                  'GENERATION_REQUEST',
                )
                setCampaign(response.campaign)
                navigate('generate', campaign.id)
              })
            }
          />
        )}
        {campaign && screen === 'generate' && (
          <GenerationScreen
            campaign={campaign}
            busy={busy}
            onCampaign={setCampaign}
            onReview={() => navigate('review', campaign.id)}
          />
        )}
        {campaign && screen === 'review' && (
          <GovernanceScreen campaign={campaign} />
        )}
        {!campaign && screen !== 'home' && (
          <section className="page">
            <h1>No campaign selected</h1>
            <button className="primary" onClick={() => navigate('home')}>
              Return Home
            </button>
          </section>
        )}
      </main>
    </div>
  )
}

function Sidebar({
  active,
  campaign,
  onNavigate,
}: {
  active: Screen
  campaign: Campaign | null
  onNavigate: (screen: Screen) => void
}) {
  const items: Array<[Screen, string, string]> = [
    ['home', 'Command Center', 'C'],
    ['objective', 'Campaigns', 'P'],
    ['brand', 'Brand Brain', 'B'],
    ['director', 'Creative Studio', 'S'],
    ['assets', 'Assets', 'A'],
    ['generate', 'Generation', 'G'],
    ['review', 'Review & QA', 'Q'],
  ]
  const activeSection = sidebarSection(active)
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark">C</span>
        <strong>Creative<span>OS</span></strong>
      </div>
      <nav aria-label="CreativeOS navigation">
        {items.map(([id, label, icon]) => (
          <button
            key={id}
            className={activeSection === id ? 'active' : ''}
            onClick={() => onNavigate(id)}
            disabled={id !== 'home' && !campaign}
            title={label}
          >
            <span className="nav-icon" aria-hidden="true">{icon}</span>
            <span className="nav-label">{label}</span>
          </button>
        ))}
      </nav>
      <div className="local-badge">● LOCAL V1</div>
    </aside>
  )
}

function Topbar({
  campaign,
  busy,
  screen,
}: {
  campaign: Campaign | null
  busy: boolean
  screen: Screen
}) {
  return (
    <header className="topbar">
      <div className="topbar-context">
        <small>Campaign workflow</small>
        <div className="crumb">
          <b>{campaign?.title || 'CreativeOS'}</b>
          {campaign && screen !== 'home' && <span>/ {screenLabels[screen]}</span>}
        </div>
      </div>
      <div className="top-actions">
        <span>{busy ? 'Working…' : 'Saved to CreativeOS DB'}</span>
        {campaign && (
          <span className="status-pill">{campaign.duration_seconds}s · {campaign.aspect_ratio}</span>
        )}
      </div>
    </header>
  )
}

function Progress({ activeIndex }: { activeIndex: number }) {
  return (
    <div className="progress-strip" aria-label="Campaign workflow">
      {workflow.map(([, label], index) => (
        <div
          key={label}
          className={
            'progress-step ' +
            (index === activeIndex ? 'active ' : '') +
            (index < activeIndex ? 'done' : '')
          }
        >
          <span>{index + 1}</span>
          <b>{label}</b>
        </div>
      ))}
    </div>
  )
}

function Home({
  value,
  onChange,
  onCreate,
  campaigns,
  onSelect,
  busy,
}: {
  value: string
  onChange: (value: string) => void
  onCreate: () => void
  campaigns: Campaign[]
  onSelect: (campaign: Campaign) => void
  busy: boolean
}) {
  return (
    <section className="page home-page">
      <div className="eyebrow">AI CREATIVE PRODUCTION OS</div>
      <h1>Create something that moves the business.</h1>
      <p className="lede">
        Plan, govern, cost, review, and export from one local creative workspace.
      </p>
      <div className="command-card">
        <label htmlFor="campaign-brief">Campaign brief</label>
        <textarea
          id="campaign-brief"
          value={value}
          onChange={event => onChange(event.target.value)}
        />
        <div className="command-row">
          <div className="chips">
            <span>FleetPilot</span>
            <span>Meta Lead Campaign</span>
            <span>Governed Cost</span>
          </div>
          <button className="primary" disabled={busy} onClick={onCreate}>
            Create FleetPilot Campaign →
          </button>
        </div>
      </div>
      <div className="section-head">
        <h2>Campaigns</h2>
        <span>{campaigns.length} saved</span>
      </div>
      <div className="campaign-grid">
        {campaigns.map(item => (
          <button
            className="campaign-card"
            key={item.id}
            onClick={() => onSelect(item)}
          >
            <div className="thumb" />
            <b>{item.title}</b>
            <span>{humanizeState(item.status)} · {item.duration_seconds}s · {item.aspect_ratio}</span>
          </button>
        ))}
        {!campaigns.length && (
          <div className="empty-card">No campaigns yet. Create the first governed campaign above.</div>
        )}
      </div>
    </section>
  )
}

function ObjectiveScreen({
  campaign,
  busy,
  onNext,
}: {
  campaign: Campaign
  busy: boolean
  onNext: (objective: string) => void
}) {
  const [value, setValue] = useState(campaign.objective)
  return (
    <BriefStep
      eyebrow="01 · OBJECTIVE"
      title="What should this campaign achieve?"
      help="Define a measurable business objective before creative direction begins."
    >
      <label htmlFor="objective">Campaign objective</label>
      <textarea
        id="objective"
        aria-label="Campaign objective"
        value={value}
        onChange={event => setValue(event.target.value)}
      />
      <StepFooter>
        <button className="primary" disabled={busy} onClick={() => onNext(value)}>
          Save Objective →
        </button>
      </StepFooter>
    </BriefStep>
  )
}

function AudienceScreen({
  campaign,
  busy,
  onNext,
}: {
  campaign: Campaign
  busy: boolean
  onNext: (audience: string) => void
}) {
  const [value, setValue] = useState(campaign.audience)
  return (
    <BriefStep
      eyebrow="02 · AUDIENCE"
      title="Who needs to see this?"
      help="FleetPilot is being positioned for Philippine trucking and logistics operators."
    >
      <label htmlFor="audience">Target audience</label>
      <textarea
        id="audience"
        aria-label="Campaign audience"
        value={value}
        onChange={event => setValue(event.target.value)}
      />
      <div className="pain-grid">
        {['Fuel leakage','Dispatch confusion','Downtime','Late deliveries','Driver accountability','Trip profitability','Collections'].map(pain => (
          <span key={pain}>{pain}</span>
        ))}
      </div>
      <StepFooter>
        <button className="primary" disabled={busy} onClick={() => onNext(value)}>
          Save Audience →
        </button>
      </StepFooter>
    </BriefStep>
  )
}

function OfferScreen({
  campaign,
  busy,
  onNext,
}: {
  campaign: Campaign
  busy: boolean
  onNext: (values: Partial<Campaign>) => void
}) {
  const [offer, setOffer] = useState(campaign.offer)
  const [cta, setCta] = useState(campaign.cta || 'Book a FleetPilot demo')
  const [duration, setDuration] = useState(campaign.duration_seconds || 30)
  const [ratio, setRatio] = useState(campaign.aspect_ratio || '1:1')

  return (
    <BriefStep
      eyebrow="03 · OFFER"
      title="What is the operator being asked to do?"
      help="Campaign parameters become authoritative downstream production controls."
    >
      <label htmlFor="offer">Core offer</label>
      <textarea
        id="offer"
        aria-label="Core offer"
        value={offer}
        onChange={event => setOffer(event.target.value)}
      />
      <div className="form-grid">
        <div>
          <label htmlFor="cta">CTA</label>
          <input
            id="cta"
            aria-label="CTA"
            value={cta}
            onChange={event => setCta(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="duration">Duration</label>
          <input
            id="duration"
            aria-label="Duration"
            type="number"
            min={8}
            max={600}
            value={duration}
            onChange={event => setDuration(Number(event.target.value))}
          />
        </div>
        <div>
          <label htmlFor="ratio">Aspect ratio</label>
          <select
            id="ratio"
            aria-label="Aspect ratio"
            value={ratio}
            onChange={event => setRatio(event.target.value)}
          >
            <option>16:9</option>
            <option>9:16</option>
            <option>1:1</option>
          </select>
        </div>
      </div>
      <StepFooter>
        <button
          className="primary"
          disabled={busy}
          onClick={() =>
            onNext({
              offer,
              cta,
              format: duration === 30 ? '30s Ad' : campaign.format,
              duration_seconds: duration,
              aspect_ratio: ratio,
            })
          }
        >
          Lock Offer & Production Controls →
        </button>
      </StepFooter>
    </BriefStep>
  )
}

function BriefStep({
  eyebrow,
  title,
  help,
  children,
}: {
  eyebrow: string
  title: string
  help: string
  children: React.ReactNode
}) {
  return (
    <section className="page focused-page">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      <p className="lede">{help}</p>
      <div className="panel form-panel">{children}</div>
    </section>
  )
}

function StepFooter({ children }: { children: React.ReactNode }) {
  return <div className="step-footer">{children}</div>
}

function BrandScreen({
  campaign,
  busy,
  onContinue,
}: {
  campaign: Campaign
  busy: boolean
  onContinue: () => void
}) {
  const [brand, setBrand] = useState<Brand | null>(null)
  useEffect(() => {
    getBrand(campaign.id).then(response => setBrand(response.brand))
  }, [campaign.id])
  if (!brand) return <LoadingPage label="Loading Brand Brain…" />
  const messaging = Array.isArray(brand.messaging_json)
    ? brand.messaging_json
    : []
  return (
    <section className="page">
      <div className="eyebrow">04 · BRAND BRAIN</div>
      <h1>Product truth is locked before production.</h1>
      <div className="brand-layout">
        <div className="panel">
          <small>BRAND</small>
          <h2>{brand.name}</h2>
          <p>{brand.positioning}</p>
          <div className="fact-grid">
            <Fact label="Audience" value={brand.audience} />
            <Fact label="Promise" value={brand.core_promise} />
            <Fact label="Tagline" value={brand.tagline} />
            <Fact label="UI protection" value={brand.default_immutable_ui ? 'LOCKED' : 'OFF'} good />
          </div>
          <div className="chips">
            {messaging.map(item => <span key={item}>{item}</span>)}
          </div>
        </div>
        <aside className="panel guard-card">
          <div className="ai-status">● AUTHORITATIVE BRAND PROFILE</div>
          <h2>Generation guardrails active</h2>
          <p>No unsupported FleetPilot claims, regenerated product UI, or invented metrics.</p>
          <button className="primary wide" disabled={busy} onClick={onContinue}>
            Continue to Creative Director →
          </button>
        </aside>
      </div>
    </section>
  )
}

function Fact({
  label,
  value,
  good = false,
}: {
  label: string
  value: string
  good?: boolean
}) {
  return (
    <div className="fact">
      <small>{label}</small>
      <b className={good ? 'good' : ''}>{value}</b>
    </div>
  )
}

function DirectorScreen({
  campaign,
  busy,
  onCampaign,
  onContinue,
  run,
}: {
  campaign: Campaign
  busy: boolean
  onCampaign: (campaign: Campaign) => void
  onContinue: () => void
  run: (action: () => Promise<void>) => Promise<void>
}) {
  const [plan, setPlan] = useState<DirectorPlan | null>(null)
  useEffect(() => {
    getDirector(campaign.id).then(response => setPlan(response.plan))
  }, [campaign.id])

  const generate = () =>
    void run(async () => {
      const response = await generateDirector(campaign.id)
      setPlan(response.plan)
    })

  const approve = () =>
    void run(async () => {
      const response = await approveDirector(campaign.id)
      setPlan(response.plan)
      const latest = await getCampaign(campaign.id)
      onCampaign(latest.campaign)
      onContinue()
    })

  return (
    <section className="page director-grid">
      <div>
        <div className="eyebrow">05 · CREATIVE DIRECTOR</div>
        <h1>Turn the authoritative brief into a production plan.</h1>
        <div className="parameter-strip">
          <Fact label="Duration" value={`${campaign.duration_seconds}s`} good />
          <Fact label="Aspect" value={campaign.aspect_ratio} good />
          <Fact label="Format" value={campaign.format} />
          <Fact label="CTA" value={campaign.cta} />
        </div>
        <div className="panel">
          <small>OBJECTIVE</small>
          <p>{campaign.objective}</p>
          <small>AUDIENCE</small>
          <p>{campaign.audience}</p>
          <small>OFFER</small>
          <p>{campaign.offer}</p>
        </div>
        {plan && (
          <div className="panel director-output">
            <h2>{String(plan.output_json.strategy.campaign_angle || 'Product truth first')}</h2>
            <p className="hook">{plan.output_json.hooks[0]}</p>
            <div className="scene-summary">
              {plan.output_json.scene_plan.map(scene => (
                <span key={scene.scene_number}>
                  {scene.scene_number}. {scene.title} · {scene.duration_seconds}s
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
      <aside className="intel-panel">
        <div className="ai-status">● MOCK DIRECTOR · BACKEND</div>
        <h2>{plan ? `Proposal V${plan.version}` : 'Ready to generate'}</h2>
        {plan && (
          <>
            <Fact label="Status" value={humanizeState(plan.status)} good={plan.status === 'APPROVED'} />
            <Fact
              label="Planned duration"
              value={`${plan.output_json.scene_plan.reduce((sum, scene) => sum + scene.duration_seconds, 0)}s`}
              good
            />
            <Fact label="Output ratio" value={campaign.aspect_ratio} good />
          </>
        )}
        <button className="ghost wide" disabled={busy} onClick={generate}>
          {plan ? 'Regenerate Direction' : 'Generate Direction'}
        </button>
        <button className="primary wide" disabled={busy || !plan} onClick={approve}>
          Approve Plan & Continue →
        </button>
      </aside>
    </section>
  )
}

function ScriptScreen({
  campaign,
  busy,
  onContinue,
}: {
  campaign: Campaign
  busy: boolean
  onContinue: () => void
}) {
  const [plan, setPlan] = useState<DirectorPlan | null>(null)
  useEffect(() => {
    getDirector(campaign.id).then(response => setPlan(response.plan))
  }, [campaign.id])
  if (!plan) return <LoadingPage label="Loading script…" />
  return (
    <section className="page">
      <div className="eyebrow">06 · SCRIPT</div>
      <h1>Scene-linked script</h1>
      <p className="lede">
        {campaign.duration_seconds}s · {campaign.aspect_ratio} · {campaign.cta}
      </p>
      <div className="script-list">
        {plan.output_json.script.map(line => (
          <article className="panel script-line" key={line.scene_number}>
            <span>{String(line.scene_number).padStart(2, '0')} · {line.timing_seconds}s</span>
            <h3>{line.on_screen_copy}</h3>
            <p>{line.voiceover}</p>
          </article>
        ))}
      </div>
      <StepFooter>
        <button className="primary" disabled={busy} onClick={onContinue}>
          Continue to Storyboard →
        </button>
      </StepFooter>
    </section>
  )
}

function StoryboardScreen({
  campaign,
  busy,
  onContinue,
}: {
  campaign: Campaign
  busy: boolean
  onContinue: () => void
}) {
  const [data, setData] = useState<StoryboardData | null>(null)
  useEffect(() => {
    getStoryboard(campaign.id).then(setData)
  }, [campaign.id])
  if (!data?.storyboard) return <LoadingPage label="Loading storyboard…" />
  return (
    <section className="page storyboard-page">
      <div className="story-head">
        <div>
          <div className="eyebrow">07 · STORYBOARD</div>
          <h1>{data.storyboard.title}</h1>
          <p>{data.duration_seconds}s total · {data.aspect_ratio} · {data.scenes.length} scenes</p>
        </div>
        <button className="primary" disabled={busy} onClick={onContinue}>
          Build Asset Plan →
        </button>
      </div>
      <div className="scene-strip">
        {data.scenes.map(scene => (
          <article className="scene-card" key={scene.id}>
            <div className="scene-preview" />
            <small>SCENE {String(scene.position).padStart(2, '0')} · {scene.duration_seconds}s</small>
            <b>{scene.title}</b>
            <span className={scene.scene_type === 'REAL_UI' ? 'real' : 'ai'}>
              {humanizeState(scene.scene_type)}
            </span>
            <small>{humanizeState(scene.generation_method)}</small>
          </article>
        ))}
      </div>
      <div className="panel inspector-wide">
        <Fact label="Campaign duration" value={`${campaign.duration_seconds}s`} good />
        <Fact label="Storyboard duration" value={`${data.duration_seconds}s`} good={data.duration_seconds === campaign.duration_seconds} />
        <Fact label="Output aspect ratio" value={data.aspect_ratio} good={data.aspect_ratio === campaign.aspect_ratio} />
        <Fact label="Publishing" value="Not authorized" />
      </div>
    </section>
  )
}

function AssetPlanScreen({
  campaign,
  busy,
  onCampaign,
  onContinue,
}: {
  campaign: Campaign
  busy: boolean
  onCampaign: (campaign: Campaign) => void
  onContinue: () => void
}) {
  const [plan, setPlan] = useState<AssetPlan | null>(null)
  const [loadError, setLoadError] = useState('')
  useEffect(() => {
    getAssetPlan(campaign.id)
      .then(async response => {
        setPlan(response)
        const latest = await getCampaign(campaign.id)
        onCampaign(latest.campaign)
      })
      .catch(err => setLoadError(err instanceof Error ? err.message : String(err)))
  }, [campaign.id, onCampaign])
  if (loadError) return <ErrorPage message={loadError} />
  if (!plan) return <LoadingPage label="Building campaign Asset Plan…" />
  return (
    <section className="page">
      <div className="eyebrow">08 · ASSET PLAN</div>
      <h1>Know exactly what exists and what must be generated.</h1>
      <p className="lede">{campaign.duration_seconds}s · {campaign.aspect_ratio} · {plan.quantity} planned asset dependencies</p>
      <div className="asset-grid">
        {plan.items.map((item, index) => (
          <article className="panel asset-card" key={`${item.kind}-${index}`}>
            <span className="asset-kind">{humanizeState(item.kind)}</span>
            <h3>{item.purpose}</h3>
            <Fact label="Status" value={humanizeState(item.status)} good={item.status === 'EXISTING'} />
            <Fact label="Provider" value={item.provider} />
            <Fact label="Model" value={item.model || 'N/A'} />
            <Fact label="Format" value={`${item.format} · ${item.aspect_ratio}`} />
            <Fact label="Quantity" value={String(item.quantity)} />
          </article>
        ))}
      </div>
      <StepFooter>
        <button className="primary" disabled={busy} onClick={onContinue}>
          Continue to Generation Request →
        </button>
      </StepFooter>
    </section>
  )
}

function GenerationScreen({
  campaign,
  busy,
  onCampaign,
  onReview,
}: {
  campaign: Campaign
  busy: boolean
  onCampaign: (campaign: Campaign) => void
  onReview: () => void
}) {
  const [request, setRequest] = useState<GenerationRequest | null>(null)
  const [localError, setLocalError] = useState('')
  useEffect(() => {
    getGenerationRequest(campaign.id)
      .then(response => setRequest(response.generation_request))
      .catch(() => {})
  }, [campaign.id])

  const create = async () => {
    setLocalError('')
    try {
      const response = await createGenerationRequest(campaign.id)
      setRequest(response.generation_request)
      const latest = await getCampaign(campaign.id)
      onCampaign(latest.campaign)
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <section className="page generation-page">
      <div className="eyebrow">09 · GENERATION REQUEST</div>
      <h1>Cost is visible before any provider submission.</h1>
      <p className="lede">
        This screen can create and cost a request. It cannot approve, reserve, queue, or submit it.
      </p>
      {!request && (
        <div className="panel gate-card">
          <h2>Ready to create governed request</h2>
          <p>One FleetPilot Meta image · {campaign.duration_seconds}s campaign · {campaign.aspect_ratio}</p>
          <button className="primary" disabled={busy} onClick={() => void create()}>
            Create Generation Request
          </button>
        </div>
      )}
      {localError && <div className="error-banner">{localError}</div>}
      {request && (
        <div className="generation-grid">
          <div className="panel request-card">
            <div className="request-header">
              <div>
                <small>REQUEST</small>
                <h2>{request.provider} / {request.model}</h2>
              </div>
              <span className="status-pill">{humanizeState(request.lifecycle_state)}</span>
            </div>
            <div className="fact-grid">
              <Fact label="Quantity" value={String(request.quantity)} />
              <Fact label="Estimated cost" value={request.estimated_cost} good />
              <Fact label="Campaign duration" value={`${request.campaign_duration_seconds}s`} good />
              <Fact label="Output ratio" value={request.aspect_ratio} good />
            </div>
          </div>
          <aside className="panel approval-card">
            <div className="approval-icon">⛔</div>
            <small>APPROVAL STATE</small>
            <h2>{humanizeState(request.approval_state)}</h2>
            <p>
              Provider submission is disabled until a separate explicit cost approval occurs.
            </p>
            <div className="zero-grid">
              <Fact label="Provider submissions" value={String(request.provider_submissions)} good />
              <Fact label="Generation attempts" value={String(request.generation_attempts)} good />
              <Fact label="Reservations" value={String(request.budget_reservations)} good />
              <Fact label="Spend events" value={String(request.spend_events)} good />
            </div>
            <b className="zero-spend">Actual spend · USD 0.00</b>
          </aside>
        </div>
      )}
      {request && (
        <StepFooter>
          <button className="ghost" onClick={() => void create()}>
            Re-open same idempotent request
          </button>
          <button className="primary" onClick={onReview}>
            Inspect Downstream Governance →
          </button>
        </StepFooter>
      )}
    </section>
  )
}

function GovernanceScreen({ campaign }: { campaign: Campaign }) {
  const [governance, setGovernance] = useState<Governance | null>(null)
  const [request, setRequest] = useState<GenerationRequest | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    Promise.all([getGovernance(campaign.id), getGenerationRequest(campaign.id)])
      .then(([governanceResponse, requestResponse]) => {
        setGovernance(governanceResponse.governance)
        setRequest(requestResponse.generation_request)
        setLoaded(true)
      })
  }, [campaign.id])

  if (!governance || !loaded) {
    return <LoadingPage label="Loading governance state…" />
  }

  const campaignStatus =
    request?.approval_state === 'COST_APPROVAL_REQUIRED'
      ? humanizeState(request.approval_state)
      : request
        ? humanizeState(request.lifecycle_state)
        : humanizeState(campaign.status)

  const nextAction =
    request?.approval_state === 'COST_APPROVAL_REQUIRED'
      ? 'Approve generation cost to create the first asset.'
      : !request
        ? 'Create a governed generation request before production begins.'
        : governance.automated_qa === 'NOT_GENERATED'
          ? 'Complete generation before automated QA can run.'
          : governance.human_review === 'WAITING_FOR_QA'
            ? 'Complete automated QA before human review.'
            : governance.export === 'NOT_AVAILABLE'
              ? 'Complete required review before export becomes available.'
              : 'Review the governed output before manual publishing.'

  const generationState =
    request?.approval_state === 'COST_APPROVAL_REQUIRED'
      ? request.approval_state
      : request?.lifecycle_state || 'NOT_GENERATED'

  const items = [
    ['Generation', generationState, 'Generation remains bounded by explicit cost approval and provider controls.'],
    ['Automated QA', governance.automated_qa, 'System checks are independent of human acceptance.'],
    ['Provenance', governance.provenance, 'Provider, model, and output lineage appears only after generation.'],
    ['Human Review', governance.human_review, 'A human decision is required after automated QA.'],
    ['Export', governance.export, 'Export cannot become available before required reviews pass.'],
  ]

  return (
    <section className="page governance-page">
      <div className="eyebrow">10 · GOVERNANCE</div>
      <h1>QA ≠ Human Review ≠ Export ≠ Publishing</h1>
      <p className="lede">
        Governance reflects persisted campaign and generation state without authorizing spend or publishing.
      </p>

      <div className="panel governance-status">
        <div>
          <small>Campaign status</small>
          <h2>{campaignStatus}</h2>
        </div>
        <div>
          <small>Next action</small>
          <p>{nextAction}</p>
        </div>
      </div>

      <div className="lifecycle-flow" aria-label="Governance lifecycle">
        Generation → Automated QA → Provenance → Human Review → Export
      </div>

      <div className="governance-grid">
        {items.map(([label, value, note]) => (
          <article className="panel governance-card" key={label}>
            <small>{label}</small>
            <h2>{humanizeState(value)}</h2>
            <p>{note}</p>
          </article>
        ))}
      </div>

      <div className="panel publishing-control">
        <div>
          <small>Publishing control</small>
          <h2>Manual only</h2>
          <p>Publishing remains separate from generation, QA, review, and export.</p>
        </div>
        <div className="publish-state">
          <small>Automatic publishing</small>
          <b>{governance.auto_publish ? 'Enabled' : 'Disabled'}</b>
        </div>
      </div>
    </section>
  )
}

function LoadingPage({ label }: { label: string }) {
  return <section className="page"><div className="loading-card">{label}</div></section>
}

function ErrorPage({ message }: { message: string }) {
  return <section className="page"><div className="error-banner">{message}</div></section>
}

export default App
