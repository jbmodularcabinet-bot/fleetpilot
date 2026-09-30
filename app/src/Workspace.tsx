import { useEffect, useState, useSyncExternalStore } from 'react'
import type { FormEvent } from 'react'
import { WorkspaceClient } from './scope-client'
import type { Detail } from './scope-client'
import './Workspace.css'

const defaultClient = new WorkspaceClient()
const text = (value: unknown) => value == null ? '' : typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)

export default function Workspace({ client = defaultClient }: { client?: WorkspaceClient }) {
  const state = useSyncExternalStore(client.subscribe, client.snapshot)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
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
  return <div className="workspace-shell">
    <header className="workspace-header"><strong>CreativeOS</strong><span>Campaign workspace</span>
      {session && <button disabled={busy} onClick={() => void client.logout()}>Sign out {session.user.username}</button>}
    </header>
    {state.error && <p role="alert" className="workspace-error">{state.error}</p>}
    {!session ? <main className="signin-card">
      <p className="eyebrow">YOUR CREATIVE WORKSPACE</p><h1>Sign in to CreativeOS</h1>
      <p>Use the account provided by your workspace administrator.</p>
      <form onSubmit={login}>
        <label>Username<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>Password<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
        <button disabled={busy} type="submit">Sign in</button>
      </form>
    </main> : <main>
      <section className="scope-selectors" aria-label="Active workspace">
        <label>Organization<select aria-label="Organization" disabled={busy} value={session.scope?.organization_id || ''}
          onChange={e => void client.select(e.target.value, null)}>
          <option value="" disabled>Select organization</option>
          {session.organizations.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}
        </select></label>
        <label>Brand / product<select aria-label="Brand / product" disabled={busy || !organization} value={session.scope?.brand_profile_id || ''}
          onChange={e => void client.select(organization!.id, e.target.value)}>
          <option value="" disabled>Select brand or product</option>
          {state.brands.map(brand => <option key={brand.id} value={brand.id}>{brand.name} ({brand.entity_type || 'BRAND'})</option>)}
        </select></label>
        <span>{organization?.role.toLowerCase()}</span>
      </section>
      {busy && <p role="status">Updating workspace...</p>}
      {!session.organizations.length && <p>Your account has no active organization membership. Contact your administrator.</p>}
      {!workspace && !busy && organization && <p>Select a brand or product to open its campaigns. If none are available, ask your administrator to create one.</p>}
      {workspace && <div className="workspace-grid">
        <aside>
          <h2>{workspace.brand.name}</h2>
          <details><summary>Brand Brain</summary>
            <dl>{['business_type', 'audience', 'core_promise', 'tone_of_voice', 'positioning'].map(key =>
              <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{text(workspace.brand[key]) || 'Not set'}</dd></div>)}</dl>
          </details>
          <h3>Campaigns</h3>
          {workspace.campaigns.length === 0 && <p>No campaigns in this brand yet.</p>}
          <ul className="campaign-list">{workspace.campaigns.map(campaign => <li key={campaign.id}>
            <button disabled={busy} aria-pressed={detail?.campaign.id === campaign.id} onClick={() => void client.openCampaign(campaign.id)}>{campaign.title}</button>
          </li>)}</ul>
          {canWrite && <CampaignForm key={session.version} client={client} busy={busy} />}
        </aside>
        <section className="campaign-content">
          {detail ? <CampaignPanel key={session.version + ':' + detail.campaign.id} detail={detail} client={client} disabled={busy || !canWrite} busy={busy} mediaUrl={state.mediaUrl} /> :
            <><h1>Make your next campaign</h1><p>Create or open a campaign in {workspace.brand.name}.</p></>}
        </section>
      </div>}
      {session.user.platform_admin && organization?.role === 'OWNER' && <section className="adoption-panel">
        <h2>Legacy ownership adoption</h2>
        <p>Only confirmed records become accessible to this organization. Unowned records remain outside campaign workspaces.</p>
        <button disabled={busy} onClick={() => void client.inventory()}>Inspect unowned legacy records</button>
        {state.inventory && <>
          <p>{state.inventory.notice} Unassigned assets: {state.inventory.unassigned_assets}.</p>
          <ul>{state.inventory.brands.map(brand => <li key={brand.id}>{brand.name}
            <button disabled={busy} onClick={() => void client.preview(brand.id)}>Preview adoption of {brand.name}</button>
          </li>)}</ul>
        </>}
        {state.preview && <AdoptionConfirmation key={state.preview.id} name={state.preview.brand_name}
          organization={organization.name} counts={state.preview.counts} conflicts={state.preview.conflicts}
          notice={state.preview.notice} busy={busy} confirm={() => void client.confirmAdoption()} />}
      </section>}
    </main>}
  </div>
}

function CampaignForm({ client, busy }: { client: WorkspaceClient; busy: boolean }) {
  const [fields, setFields] = useState({ title: '', objective: '', audience: '', offer: '', cta: '' })
  return <form className="campaign-form" onSubmit={event => {
    event.preventDefault()
    void client.createCampaign(fields)
  }}>
    <h3>New campaign</h3>
    {Object.entries(fields).map(([key, value]) => <label key={key}>{key === 'cta' ? 'Call to action' : key[0].toUpperCase() + key.slice(1)}
      <input required={key === 'title'} maxLength={2000} value={value}
        onChange={event => setFields(current => ({ ...current, [key]: event.target.value }))} />
    </label>)}
    <button disabled={busy}>Create campaign</button>
  </form>
}

function CampaignPanel({ detail, client, disabled, busy, mediaUrl }: { detail: Detail; client: WorkspaceClient; disabled: boolean; busy: boolean; mediaUrl: string | null }) {
  const [note, setNote] = useState('')
  const campaign = detail.campaign
  const request = detail.generation_requests[0]
  const step = request?.lifecycle_step || 0
  const plan = detail.director_plans[0]
  const campaignPath = '/api/campaigns/' + campaign.id
  const requestPath = '/api/requests/' + request?.id
  return <>
    <p className="eyebrow">CAMPAIGN PRODUCTION</p><h1>{campaign.title}</h1>
    <p>{text(campaign.objective)}</p>
    <p className="preview-notice">Local MOCK preview: a two-second placeholder visual and mock voice. Real rendering, QA checks and human approval; no paid AI provider calls.</p>
    <div className="workflow-actions">
      <button disabled={disabled || !!plan} onClick={() => void client.action(campaignPath + '/plan')}>Generate strategy</button>
      <button disabled={disabled || !plan || !!detail.storyboards.length} onClick={() => void client.action(campaignPath + '/approve-plan', { plan_id: plan?.id })}>Approve plan and storyboard</button>
      <button disabled={disabled || !detail.storyboards.length || !!request} onClick={() => void client.action(campaignPath + '/generate')}>Generate local MOCK preview</button>
      <button disabled={disabled || step !== 6} onClick={() => void client.action(requestPath + '/qa')}>Run QA</button>
    </div>
    {plan && <details><summary>Review strategy and storyboard</summary><pre>{text(plan.plan_json || plan)}</pre></details>}
    {request && step >= 6 && <button disabled={busy} onClick={() => void client.viewPreview(request.id)}>View generated preview</button>}
    {mediaUrl && <video controls src={mediaUrl} aria-label="Generated preview" className="generated-preview" />}
    {request && <p data-testid="generation-state">Generation stage: {step} / 10</p>}
    {!!detail.qa_runs.length && <p>QA result: {text(detail.qa_runs[detail.qa_runs.length - 1].overall_result)}</p>}
    {step >= 8 && <section className="human-review"><h2>Human review</h2>
      <label>Review note<textarea value={note} maxLength={2000} onChange={e => setNote(e.target.value)} disabled={disabled || step !== 8} /></label>
      <button disabled={disabled || step !== 8 || !note.trim()} onClick={() => void client.action(requestPath + '/review', { decision: 'ACCEPTED', note })}>Accept preview</button>
      <button disabled={disabled || step !== 8 || !note.trim()} onClick={() => void client.action(requestPath + '/review', { decision: 'REJECTED', note })}>Reject preview</button>
    </section>}
    <button disabled={disabled || step !== 9} onClick={() => void client.action(requestPath + '/export')}>Export approved preview</button>
    {detail.export_jobs.map(job => <p key={job.id}><button disabled={busy} onClick={() => void client.download(job.id)}>Download approved export</button></p>)}
    <details><summary>Queue, QA, approvals, costs and exports</summary>
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
