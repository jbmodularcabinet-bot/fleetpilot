import { useEffect, useState, useSyncExternalStore } from 'react'
import type { FormEvent } from 'react'
import { WorkspaceClient } from './scope-client'
import type { Detail } from './scope-client'
import CreativeIntelligence from './CreativeIntelligence'
import './Workspace.css'

const defaultClient = new WorkspaceClient()
const text = (value: unknown) => value == null ? '' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
const navigation = [
  { id: 'workspace-overview', label: 'Dashboard', icon: '◈' },
  { id: 'campaigns-panel', label: 'Campaigns', icon: '▤' },
  { id: 'brand-brain', label: 'Brand Brain', icon: '◇' },
  { id: 'creative-intelligence', label: 'Creative Intelligence', icon: '◉' },
  { id: 'creative-director', label: 'Creative Director', icon: '✳' },
  { id: 'storyboard', label: 'Storyboard', icon: '▧' },
  { id: 'generation', label: 'Generation', icon: '✧' },
  { id: 'qa', label: 'Automated QA', icon: '✓' },
  { id: 'human-review', label: 'Human review', icon: '◎' },
  { id: 'export', label: 'Export', icon: '↗' },
]

export default function Workspace({ client = defaultClient }: { client?: WorkspaceClient }) {
  const state = useSyncExternalStore(client.subscribe, client.snapshot)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [activeArea, setActiveArea] = useState('workspace-overview')
  useEffect(() => {
    const disconnect = client.connect()
    void client.refresh()
    return disconnect
  }, [client])
  const { session, workspace, detail, busy } = state
  const organization = session?.organizations.find(o => o.id === session.scope?.organization_id)
  const canWrite = organization?.role === 'OWNER' || organization?.role === 'EDITOR'
  const login = (event: FormEvent) => {
    event.preventDefault()
    void client.login(username, password)
    setPassword('')
  }
  const navigate = (id: string) => {
    setActiveArea(id)
    requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView?.({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }))
  }
  return <div className="workspace-shell">
    <header className="workspace-header">
      <a className="platform-brand" href="#workspace-overview" aria-label="CreativeOS, Ideas to Impact" onClick={event => { event.preventDefault(); navigate('workspace-overview') }}>
        <img className="platform-symbol" src="/creativeos-approved-ribbon.png" alt="" />
        <img className="platform-wordmark" src="/creativeos-approved-wordmark.png" alt="CreativeOS — Creative Production OS" />
      </a>
      <span className="header-promise">IDEAS TO IMPACT <i /> CREATE · GOVERN · SHIP</span>
      {session && <div className="account-controls"><span className="account-name">{session.user.username}</span>
        <button className="ghost-button" disabled={busy} onClick={() => void client.logout()}>Sign out {session.user.username}</button></div>}
    </header>
    {state.error && <div role="alert" className="workspace-error">{state.error}</div>}
    {!session ? <main className="signin-layout">
      <section className="signin-editorial">
        <p className="eyebrow">THE CREATIVE PRODUCTION OS</p>
        <h1>Ideas <em>to Impact.</em></h1>
        <p className="editorial-lead">Build better campaigns with every creative decision, generation and approval in one governed workspace.</p>
        <div className="signin-pillars"><span>01 / Create</span><span>02 / Govern</span><span>03 / Ship</span></div>
        <p className="signin-footer">One platform. Every brand. Independent organizations and products stay in their own workspaces.</p>
      </section>
      <section className="signin-card" aria-label="Sign in">
        <span className="login-marker">PRIVATE WORKSPACE</span>
        <p className="eyebrow">WELCOME BACK</p><h2>Make your next idea real.</h2>
        <p>Sign in with your administrator-provisioned account. There is no public registration.</p>
        <form onSubmit={login}>
          <label>Username<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} /></label>
          <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
          <button className="primary-button" disabled={busy} type="submit">Sign in <span aria-hidden="true">↗</span></button>
        </form>
        <p className="security-footnote">Authenticated access · Organization-scoped production</p>
      </section>
    </main> : <main className="authenticated-app">
      <section className="scope-selectors" aria-label="Active workspace">
        <div className="scope-heading"><span className="eyebrow">YOUR WORKSPACE</span><strong>Choose your creative context</strong></div>
        <label>Organization<select aria-label="Organization" disabled={busy} value={session.scope?.organization_id || ''}
          onChange={e => { setActiveArea('workspace-overview'); void client.select(e.target.value, null) }}>
          <option value="" disabled>Select organization</option>
          {session.organizations.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}
        </select></label>
        <label>Brand / product<select aria-label="Brand / product" disabled={busy || !organization} value={session.scope?.brand_profile_id || ''}
          onChange={e => { setActiveArea('workspace-overview'); void client.select(organization!.id, e.target.value) }}>
          <option value="" disabled>Select brand or product</option>
          {state.brands.map(brand => <option key={brand.id} value={brand.id}>{brand.name} ({brand.entity_type || 'BRAND'})</option>)}
        </select></label>
        <span className="role-pill">{organization?.role || 'NO ACTIVE ROLE'}</span>
      </section>
      {busy && <p className="workspace-loading" role="status"><span className="loading-dot" /> Updating workspace...</p>}
      {!session.organizations.length && <div className="empty-context">Your account has no active organization membership. Contact your administrator.</div>}
      {!workspace && !busy && !!organization && <div className="empty-context">Select a brand or product to open its campaigns. If none are available, ask your administrator to create one.</div>}
      {workspace && <div className="workspace-grid" id="workspace-overview">
        <aside className="workspace-sidebar" aria-label="Workspace navigation">
          <div className="sidebar-context"><span className="eyebrow">ACTIVE CUSTOMER BRAND</span>
            <h2>{workspace.brand.name}</h2>
            <span className="tenant-tag">{organization?.classification === 'NATIVE' ? 'Native organization' : 'Independent organization'}</span>
          </div>
          <nav className="production-nav" aria-label="Production navigation">
            <span className="nav-caption">PRODUCTION</span>
            {navigation.map(item => <button key={item.id} type="button" className={activeArea === item.id ? 'nav-link active' : 'nav-link'}
              aria-pressed={activeArea === item.id} disabled={busy || (!detail && !['workspace-overview', 'campaigns-panel', 'brand-brain', 'creative-intelligence'].includes(item.id))}
              onClick={() => navigate(item.id)}><span aria-hidden="true" className="nav-icon">{item.icon}</span>{item.label}</button>)}
          </nav>
          <section className="sidebar-campaigns" id="campaigns-panel">
            <div className="sidebar-section-heading"><h3>Campaigns</h3><span>{workspace.campaigns.length}</span></div>
            {workspace.campaigns.length === 0 && <p className="muted">No campaigns yet.</p>}
            <ul className="campaign-list">{workspace.campaigns.map(campaign => <li key={campaign.id}>
              <button disabled={busy} aria-pressed={detail?.campaign.id === campaign.id} onClick={() => { setActiveArea('workspace-overview'); void client.openCampaign(campaign.id) }}>{campaign.title}</button>
            </li>)}</ul>
            {canWrite && <CampaignForm key={session.version} client={client} busy={busy} />}
          </section>
        </aside>
        <div className="workspace-main">
          <section className="dashboard-hero">
            <div><p className="eyebrow">CREATIVEOS / COMMAND CENTER</p>
              <h1>Ideas <em>to Impact.</em></h1>
              <p>Create boldly. Govern confidently. Ship with clarity.</p>
              <span className="context-footnote">Active customer brand: <strong>{workspace.brand.name}</strong></span>
            </div><div className="hero-orb" aria-hidden="true"><span /></div>
          </section>
          <div className="metric-grid" aria-label="Workspace summary">
            <div className="metric-card"><span>Brand campaigns</span><strong>{workspace.campaigns.length}</strong><small>In this selected brand only</small></div>
            <div className="metric-card"><span>Current production</span><strong>{detail?.generation_requests[0] ? detail.generation_requests[0].lifecycle_step + ' / 10' : '—'}</strong><small>Server-backed workflow</small></div>
            <div className="metric-card"><span>Automated QA</span><strong>{detail?.qa_runs.length ? text(detail.qa_runs[detail.qa_runs.length - 1].overall_result) : 'PENDING'}</strong><small>Not human approval</small></div>
            <div className="metric-card"><span>Publishing</span><strong>MANUAL</strong><small>Automatic publishing disabled</small></div>
          </div>
          {activeArea === 'creative-intelligence' && <CreativeIntelligence key={'ci:'+session.version} session={session} canWrite={!!canWrite} />}
          <section className="workspace-project" aria-label="Selected campaign">
            {detail ? <CampaignPanel key={session.version + ':' + detail.campaign.id} detail={detail} client={client} disabled={busy || !canWrite} busy={busy} mediaUrl={state.mediaUrl} /> :
              <div className="no-campaign"><span className="eyebrow">CAMPAIGN STUDIO</span><h2>Make your next campaign.</h2>
                <p>Create a campaign or select an existing campaign from the sidebar. Your work stays inside <strong>{workspace.brand.name}</strong>.</p>
                <div className="empty-workflow">Brief <span>→</span> Director <span>→</span> Storyboard <span>→</span> MOCK preview <span>→</span> QA <span>→</span> Human review <span>→</span> Export</div>
              </div>}
          </section>
          <section className="surface-card brand-brain-panel" id="brand-brain">
            <div className="section-heading"><div><p className="eyebrow">BRAND INTELLIGENCE</p><h2>Brand Brain</h2></div><span className="stage-chip">CUSTOMER DATA</span></div>
            <p className="section-intro">The selected customer's persisted profile powers its campaigns. Platform styling never changes customer ownership.</p>
            <dl className="brand-facts">{['business_type', 'audience', 'core_promise', 'tone_of_voice', 'positioning'].map(key =>
              <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{text(workspace.brand[key]) || 'Not configured'}</dd></div>)}</dl>
          </section>
        </div>
      </div>}
      {session.user.platform_admin && organization?.role === 'OWNER' && <section className="adoption-panel">
        <div className="section-heading"><div><p className="eyebrow">PRIVILEGED ADMINISTRATION</p><h2>Legacy ownership adoption</h2></div><span className="stage-chip">EXPLICIT CONFIRMATION</span></div>
        <p>Only confirmed records become accessible to this organization. Unowned records remain outside campaign workspaces.</p>
        <button disabled={busy} onClick={() => void client.inventory()}>Inspect unowned legacy records</button>
        {state.inventory && <><p>{state.inventory.notice} Unassigned assets: {state.inventory.unassigned_assets}.</p>
          <ul>{state.inventory.brands.map(brand => <li key={brand.id}>{brand.name}
            <button disabled={busy} onClick={() => void client.preview(brand.id)}>Preview adoption of {brand.name}</button>
          </li>)}</ul></>}
        {state.preview && <AdoptionConfirmation key={state.preview.id} name={state.preview.brand_name}
          organization={organization.name} counts={state.preview.counts} conflicts={state.preview.conflicts}
          notice={state.preview.notice} busy={busy} confirm={() => void client.confirmAdoption()} />}
      </section>}
    </main>}
    <footer className="platform-footer"><span>CreativeOS · Ideas to Impact.</span><span>Create. Govern. Ship.</span></footer>
  </div>
}

function CampaignForm({ client, busy }: { client: WorkspaceClient; busy: boolean }) {
  const [fields, setFields] = useState({ title: '', objective: '', audience: '', offer: '', cta: '' })
  return <form className="campaign-form" onSubmit={event => { event.preventDefault(); void client.createCampaign(fields) }}>
    <h3>New campaign <span aria-hidden="true">＋</span></h3>
    {Object.entries(fields).map(([key, value]) => <label key={key}>{key === 'cta' ? 'Call to action' : key[0].toUpperCase() + key.slice(1)}
      <input required={key === 'title'} maxLength={2000} value={value}
        onChange={event => setFields(current => ({ ...current, [key]: event.target.value }))} /></label>)}
    <button className="primary-button" disabled={busy}>Create campaign <span aria-hidden="true">↗</span></button>
  </form>
}

function CampaignPanel({ detail, client, disabled, busy, mediaUrl }: { detail: Detail; client: WorkspaceClient; disabled: boolean; busy: boolean; mediaUrl: string | null }) {
  const [note, setNote] = useState('')
  const campaign = detail.campaign
  const request = detail.generation_requests[0]
  const step = request?.lifecycle_step || 0
  const plan = detail.director_plans[0]
  const qaResult = detail.qa_runs.length ? text(detail.qa_runs[detail.qa_runs.length - 1].overall_result) : ''
  const campaignPath = '/api/campaigns/' + campaign.id
  const requestPath = '/api/requests/' + request?.id
  return <>
    <div className="campaign-title"><div><p className="eyebrow">CAMPAIGN STUDIO / SERVER-BACKED</p><h2>{campaign.title}</h2>
      <p>{text(campaign.objective) || 'No objective provided.'}</p></div><span className="stage-chip">{request ? 'STAGE ' + step + ' / 10' : 'BRIEF'}</span></div>
    <section className="governance-grid" aria-label="Governance stages">
      <div><span>01 / Automated QA</span><strong>{qaResult || 'NOT RUN'}</strong><small>Evidence checks only</small></div>
      <div><span>02 / Human review</span><strong>{step >= 9 ? 'ACCEPTED' : step === 8 ? 'AWAITING REVIEW' : 'NOT APPROVED'}</strong><small>Independent human decision</small></div>
      <div><span>03 / Export</span><strong>{detail.export_jobs.length ? 'AVAILABLE' : 'NOT AVAILABLE'}</strong><small>Requires approved evidence</small></div>
      <div><span>04 / Publishing</span><strong>MANUAL ONLY</strong><small>Auto publishing disabled</small></div>
    </section>
    <section className="surface-card flow-section" id="creative-director">
      <div className="section-heading"><div><p className="eyebrow">01 / STRATEGY</p><h3>Creative Director</h3></div><span className="stage-chip">{plan ? 'PLAN CREATED' : 'AWAITING STRATEGY'}</span></div>
      <p className="section-intro">Turn the campaign brief and the selected Brand Brain into a documented creative plan.</p>
      <div className="brief-grid"><div><span>Objective</span><p>{text(campaign.objective) || 'Not specified'}</p></div>
        <div><span>Audience</span><p>{text(campaign.audience) || 'Not specified'}</p></div>
        <div><span>Offer</span><p>{text(campaign.offer) || 'Not specified'}</p></div>
        <div><span>Call to action</span><p>{text(campaign.cta) || 'Not specified'}</p></div></div>
      <div className="workflow-actions"><button disabled={disabled || !!plan} onClick={() => void client.action(campaignPath + '/plan')}>Generate strategy</button>
        <button className="outline-button" disabled={disabled || !plan || !!detail.storyboards.length} onClick={() => void client.action(campaignPath + '/approve-plan', { plan_id: plan?.id })}>Approve plan and storyboard</button></div>
      {plan && <details><summary>Review strategy and storyboard</summary><pre>{text(plan.plan_json || plan)}</pre></details>}
    </section>
    <section className="surface-card flow-section" id="storyboard">
      <div className="section-heading"><div><p className="eyebrow">02 / COMPOSITION</p><h3>Storyboard</h3></div><span className="stage-chip">{detail.storyboards.length ? 'MATERIALIZED' : 'AWAITING APPROVAL'}</span></div>
      <p className="section-intro">The storyboard is materialized only after the Director plan is approved. Original assets and immutable UI protections remain enforced.</p>
      {detail.storyboards.length > 0 && <details><summary>Inspect approved storyboard evidence</summary><pre>{text(detail.storyboards)}</pre></details>}
    </section>
    <section className="surface-card flow-section" id="generation">
      <div className="section-heading"><div><p className="eyebrow">03 / PRODUCTION</p><h3>Generation workspace</h3></div><span className="stage-chip mock-chip">LOCAL MOCK ONLY</span></div>
      <p className="preview-notice"><strong>MOCK GENERATION</strong> — a two-second placeholder visual and mock voice. Real local rendering, QA checks and human approval are separate. No paid AI provider calls.</p>
      <div className="workflow-actions"><button disabled={disabled || !detail.storyboards.length || !!request} onClick={() => void client.action(campaignPath + '/generate')}>Generate local MOCK preview</button>
        {request && step >= 6 && <button className="outline-button" disabled={busy} onClick={() => void client.viewPreview(request.id)}>View generated preview</button>}</div>
      {mediaUrl && <div className="preview-frame"><video controls src={mediaUrl} aria-label="Generated preview" className="generated-preview" /><span className="preview-watermark">LOCAL MOCK</span></div>}
      {request && <p className="generation-stage" data-testid="generation-state">Generation stage: {step} / 10</p>}
    </section>
    <section className="surface-card flow-section" id="qa">
      <div className="section-heading"><div><p className="eyebrow">04 / VALIDATION</p><h3>Automated QA</h3></div><span className="stage-chip">{qaResult || 'NOT RUN'}</span></div>
      <p className="section-intro">Deterministic QA evaluates generated evidence. A passing result does not authorize export or replace a human decision.</p>
      <button disabled={disabled || step !== 6} onClick={() => void client.action(requestPath + '/qa')}>Run QA</button>
      {!!detail.qa_runs.length && <p className="qa-result">QA result: {qaResult}</p>}
    </section>
    <section className="surface-card flow-section" id="human-review">
      <div className="section-heading"><div><p className="eyebrow">05 / ACCOUNTABILITY</p><h3>Human review</h3></div><span className="stage-chip">{step >= 9 ? 'ACCEPTED' : step === 8 ? 'READY FOR REVIEW' : 'WAITING FOR QA'}</span></div>
      <p className="section-intro">A person must independently accept or reject the preview after automated QA.</p>
      {step >= 8 && <div className="human-review">
        <label>Review note<textarea value={note} maxLength={2000} onChange={e => setNote(e.target.value)} disabled={disabled || step !== 8} /></label>
        <div className="workflow-actions"><button disabled={disabled || step !== 8 || !note.trim()} onClick={() => void client.action(requestPath + '/review', { decision: 'ACCEPTED', note })}>Accept preview</button>
          <button className="danger-outline" disabled={disabled || step !== 8 || !note.trim()} onClick={() => void client.action(requestPath + '/review', { decision: 'REJECTED', note })}>Reject preview</button></div>
      </div>}
    </section>
    <section className="surface-card flow-section" id="export">
      <div className="section-heading"><div><p className="eyebrow">06 / DELIVERY</p><h3>Approved export</h3></div><span className="stage-chip">{detail.export_jobs.length ? 'DOWNLOAD READY' : 'AWAITING APPROVAL'}</span></div>
      <p className="section-intro">Export uses the existing governed workflow. Publishing stays manual; automatic publishing is disabled.</p>
      <button disabled={disabled || step !== 9} onClick={() => void client.action(requestPath + '/export')}>Export approved preview</button>
      {detail.export_jobs.map(job => <p key={job.id} className="export-download"><button className="outline-button" disabled={busy} onClick={() => void client.download(job.id)}>Download approved export</button></p>)}
    </section>
    <details className="audit-details"><summary>Queue, QA, approvals, costs and exports</summary>
      {(['generation_queue', 'qa_runs', 'qa_reviews', 'generation_approvals', 'generation_spend_ledger', 'export_jobs', 'generation_attempts', 'render_jobs'] as const).map(table =>
        <section key={table}><h3>{table.replaceAll('_', ' ')}</h3><pre>{JSON.stringify(detail[table], null, 2)}</pre></section>)}
    </details>
  </>
}

function AdoptionConfirmation({ name, organization, counts, conflicts, notice, busy, confirm }: {
  name: string; organization: string; counts: Record<string, number>; conflicts: string[]; notice: string; busy: boolean; confirm: () => void
}) {
  const [checked, setChecked] = useState(false)
  return <div className="adoption-preview">
    <h3>Adopt {name} into {organization}</h3><p>{notice}</p>
    <ul>{Object.entries(counts).map(([table, count]) => <li key={table}>{table.replaceAll('_', ' ')}: {count}</li>)}</ul>
    {conflicts.length > 0 ? <div role="alert"><strong>Ownership needs investigation. Adoption is blocked.</strong><ul>{conflicts.map(item => <li key={item}>{item}</li>)}</ul></div> :
      <label className="confirmation"><input type="checkbox" checked={checked} onChange={e => setChecked(e.target.checked)} />
        I confirm that this complete legacy brand belongs to {organization}.</label>}
    <button disabled={busy || !checked || conflicts.length > 0} onClick={confirm}>Confirm ownership adoption</button>
  </div>
}
