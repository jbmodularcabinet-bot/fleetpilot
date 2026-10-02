import { useCallback, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import type { Row, Session } from './scope-client'
import './CreativeIntelligence.css'

type Hypothesis = Row & { objective?: string; audience?: string; pain_point?: string; offer?: string; angle?: string; hook?: string; proof?: string; cta?: string; format?: string; funnel_stage?: string; platform?: string; success_metric?: string; evidence_state?: string; unresolved_assumptions?: string; status?: string; evidence?: Row[] }
type Experiment = Row & { hypothesis_id?: string; variant?: string; status?: string; assets?: Row[] }
type Overview = { market_intelligence: Row[]; hypotheses: Hypothesis[]; reference_patterns: Row[]; experiments: Experiment[]; assets: Row[]; provider_capabilities: Row[] }
const empty: Overview = { market_intelligence: [], hypotheses: [], reference_patterns: [], experiments: [], assets: [], provider_capabilities: [] }
const hypothesisBlank = { objective:'', audience:'', pain_point:'', offer:'', angle:'', hook:'', proof:'', cta:'', format:'', funnel_stage:'', platform:'', success_metric:'', evidence_state:'INSUFFICIENT', unresolved_assumptions:'', status:'DRAFT' }
const marketBlank = { subject:'', subject_type:'SERVICE', intelligence_type:'PAIN_POINT', evidence_source:'', notes:'', active:true }
const referenceBlank = { reference_source:'', hook_pattern:'', offer_pattern:'', composition_pattern:'', proof_mechanism:'', cta_pattern:'', format:'', audience_stage:'', brand_safe_adaptation_notes:'' }
const experimentBlank = { hypothesis_id:'', variant:'', campaign_external_id:'', ad_external_id:'', status:'DRAFT' }
const evidenceBlank = { hypothesis_id:'', source:'', source_url:'', observation:'', sample_size:'', evidence_strength:'LIMITED' }

export default function CreativeIntelligence({ session, canWrite, fetcher = (...args) => fetch(...args) }: { session: Session; canWrite: boolean; fetcher?: typeof fetch }) {
  const [overview,setOverview]=useState<Overview>(empty), [busy,setBusy]=useState(false), [error,setError]=useState('')
  const [hypothesis,setHypothesis]=useState(hypothesisBlank), [editing,setEditing]=useState<string|null>(null)
  const [market,setMarket]=useState(marketBlank), [reference,setReference]=useState(referenceBlank)
  const [experiment,setExperiment]=useState(experimentBlank), [evidence,setEvidence]=useState(evidenceBlank)
  const [assetLink,setAssetLink]=useState({experiment_id:'',asset_key:''})
  const request=useCallback(async<T,>(path:string,body?:unknown):Promise<T>=>{
    const headers:Record<string,string>={'X-Scope-Version':String(session.version),'X-CSRF-Token':session.csrf}
    if(body!==undefined) headers['Content-Type']='application/json'
    const response=await fetcher(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers,body:body===undefined?undefined:JSON.stringify(body)})
    if(!response.ok){const payload=await response.json().catch(()=>({})) as {error?:string};throw new Error(payload.error||'Creative Intelligence request failed')}
    return response.json() as Promise<T>
  },[fetcher,session.csrf,session.version])
  useEffect(()=>{let live=true;void request<Overview>('/api/intelligence').then(value=>{if(live)setOverview(value)}).catch(reason=>{if(live)setError(reason instanceof Error?reason.message:'Request failed')});return()=>{live=false}},[request])
  const mutate=async(path:string,body:unknown,reset?:()=>void)=>{setBusy(true);setError('');try{await request(path,body);reset?.();setOverview(await request<Overview>('/api/intelligence'))}catch(e){setError(e instanceof Error?e.message:'Request failed')}finally{setBusy(false)}}
  const hypothesisMap=useMemo(()=>new Map(overview.hypotheses.map(x=>[x.id,x])),[overview.hypotheses])
  const assetOptions=overview.assets.map(a=>({key:String(a.asset_kind)+':'+a.id,label:String(a.label||a.title||a.id),kind:String(a.asset_kind||'ASSET'),id:a.id}))
  const submitHypothesis=(e:FormEvent)=>{e.preventDefault();void mutate(editing?'/api/intelligence/hypotheses/'+editing:'/api/intelligence/hypotheses',hypothesis,()=>{setHypothesis(hypothesisBlank);setEditing(null)})}
  const editHypothesis=(item:Hypothesis)=>{setEditing(item.id);setHypothesis({...hypothesisBlank,...Object.fromEntries(Object.keys(hypothesisBlank).map(k=>[k,String(item[k]??hypothesisBlank[k as keyof typeof hypothesisBlank])]))} as typeof hypothesisBlank)}
  const selectedAsset=assetOptions.find(x=>x.key===assetLink.asset_key)
  return <section className="creative-intelligence" id="creative-intelligence">
    <div className="ci-hero"><div><p className="eyebrow">CREATIVE INTELLIGENCE</p><h2>Evidence before generation.</h2><p>Market signal → hypothesis → experiment → existing production pipeline → evidence.</p></div><span className="stage-chip">{busy?'SYNCING':'SERVER-BACKED'}</span></div>
    {error&&<div role="alert" className="workspace-error">{error}</div>}
    <div className="ci-grid">
      <section className="surface-card"><h3>Market intelligence</h3><p className="section-intro">Record pain points, triggers, objections, proof and competitor patterns without scraping.</p>
        <form className="ci-form" onSubmit={e=>{e.preventDefault();void mutate('/api/intelligence/market',market,()=>setMarket(marketBlank))}}>
          <input aria-label="Market subject" required placeholder="Product / service / brand" value={market.subject} onChange={e=>setMarket({...market,subject:e.target.value})}/>
          <select aria-label="Market intelligence type" value={market.intelligence_type} onChange={e=>setMarket({...market,intelligence_type:e.target.value})}>{['PAIN_POINT','TRIGGER','OBJECTION','PROOF','COMPETITOR_PATTERN'].map(x=><option key={x}>{x}</option>)}</select>
          <input aria-label="Evidence source" placeholder="Source or observation" value={market.evidence_source} onChange={e=>setMarket({...market,evidence_source:e.target.value})}/>
          <textarea aria-label="Market notes" placeholder="Notes" value={market.notes} onChange={e=>setMarket({...market,notes:e.target.value})}/>
          <button disabled={!canWrite||busy}>Save intelligence</button>
        </form>
        <div className="ci-list">{overview.market_intelligence.map(x=><article key={x.id}><b>{String(x.subject)}</b><span>{String(x.intelligence_type).replaceAll('_',' ')}</span><p>{String(x.notes||x.evidence_source||'No notes')}</p></article>)}</div>
      </section>
      <section className="surface-card ci-wide"><h3>Creative hypothesis</h3><p className="section-intro">No predictive conversion score. Evidence remains explicit and reviewable.</p>
        <form className="ci-form ci-form-grid" onSubmit={submitHypothesis}>
          {(['objective','audience','pain_point','offer','angle','hook','proof','cta','format','funnel_stage','platform','success_metric','unresolved_assumptions'] as const).map(k=><input key={k} required={k==='objective'} aria-label={'Hypothesis '+k.replaceAll('_',' ')} placeholder={k.replaceAll('_',' ')} value={hypothesis[k]} onChange={e=>setHypothesis({...hypothesis,[k]:e.target.value})}/>)}
          <select aria-label="Evidence state" value={hypothesis.evidence_state} onChange={e=>setHypothesis({...hypothesis,evidence_state:e.target.value})}>{['INSUFFICIENT','LIMITED','MODERATE','STRONG'].map(x=><option key={x}>{x}</option>)}</select>
          <select aria-label="Hypothesis status" value={hypothesis.status} onChange={e=>setHypothesis({...hypothesis,status:e.target.value})}>{['DRAFT','READY','EXPERIMENTING','ARCHIVED'].map(x=><option key={x}>{x}</option>)}</select>
          <button disabled={!canWrite||busy}>{editing?'Update hypothesis':'Create hypothesis'}</button>
        </form>
        <div className="ci-list">{overview.hypotheses.map(x=><article key={x.id}><div className="ci-row"><b>{String(x.objective)}</b><span>Evidence: {String(x.evidence_state||'INSUFFICIENT')}</span></div><p>{String(x.hook||x.angle||'No hook yet')}</p>{x.unresolved_assumptions&&<p><strong>Unresolved assumptions:</strong> {String(x.unresolved_assumptions)}</p>}<small>{x.evidence?.length||0} evidence item(s) · {String(x.status||'DRAFT')}</small>{x.evidence?.map(item=><div className="ci-evidence-item" key={item.id}><span>{String(item.evidence_strength||'LIMITED')}</span><p>{String(item.observation||'Observation not recorded')}</p><small>{item.sample_size==null?'Sample size not recorded':'Sample size: '+String(item.sample_size)}</small></div>)}{canWrite&&<button type="button" onClick={()=>editHypothesis(x)}>Edit</button>}</article>)}</div>
      </section>
      <section className="surface-card"><h3>Attach evidence</h3>
        <form className="ci-form" onSubmit={e=>{e.preventDefault();if(!evidence.hypothesis_id)return;const body={...evidence,sample_size:evidence.sample_size===''?null:Number(evidence.sample_size)};void mutate('/api/intelligence/hypotheses/'+evidence.hypothesis_id+'/evidence',body,()=>setEvidence(evidenceBlank))}}>
          <select aria-label="Evidence hypothesis" required value={evidence.hypothesis_id} onChange={e=>setEvidence({...evidence,hypothesis_id:e.target.value})}><option value="">Choose hypothesis</option>{overview.hypotheses.map(x=><option key={x.id} value={x.id}>{String(x.objective)}</option>)}</select>
          <input aria-label="Evidence source name" required placeholder="Evidence source" value={evidence.source} onChange={e=>setEvidence({...evidence,source:e.target.value})}/>
          <input aria-label="Evidence URL" placeholder="Source URL" value={evidence.source_url} onChange={e=>setEvidence({...evidence,source_url:e.target.value})}/>
          <textarea aria-label="Evidence observation" required placeholder="Supporting observation" value={evidence.observation} onChange={e=>setEvidence({...evidence,observation:e.target.value})}/>
          <input aria-label="Evidence sample size" type="number" min="0" placeholder="Sample size" value={evidence.sample_size} onChange={e=>setEvidence({...evidence,sample_size:e.target.value})}/>
          <select aria-label="Evidence strength" value={evidence.evidence_strength} onChange={e=>setEvidence({...evidence,evidence_strength:e.target.value})}>{['INSUFFICIENT','LIMITED','MODERATE','STRONG'].map(x=><option key={x}>{x}</option>)}</select>
          <button disabled={!canWrite||busy}>Attach evidence</button>
        </form>
      </section>
      <section className="surface-card"><h3>Reference pattern</h3>
        <form className="ci-form" onSubmit={e=>{e.preventDefault();void mutate('/api/intelligence/references',reference,()=>setReference(referenceBlank))}}>
          <input aria-label="Reference source" required placeholder="Reference source" value={reference.reference_source} onChange={e=>setReference({...reference,reference_source:e.target.value})}/>
          {(['hook_pattern','offer_pattern','composition_pattern','proof_mechanism','cta_pattern','format','audience_stage','brand_safe_adaptation_notes'] as const).map(k=><input key={k} aria-label={'Reference '+k.replaceAll('_',' ')} placeholder={k.replaceAll('_',' ')} value={reference[k]} onChange={e=>setReference({...reference,[k]:e.target.value})}/>)}
          <button disabled={!canWrite||busy}>Save pattern</button>
        </form><div className="ci-list">{overview.reference_patterns.map(x=><article key={x.id}><b>{String(x.reference_source)}</b><p>{String(x.hook_pattern||x.composition_pattern||'Pattern recorded')}</p></article>)}</div>
      </section>
      <section className="surface-card"><h3>Experiment</h3>
        <form className="ci-form" onSubmit={e=>{e.preventDefault();void mutate('/api/intelligence/experiments',experiment,()=>setExperiment(experimentBlank))}}>
          <select aria-label="Experiment hypothesis" required value={experiment.hypothesis_id} onChange={e=>setExperiment({...experiment,hypothesis_id:e.target.value})}><option value="">Choose hypothesis</option>{overview.hypotheses.map(x=><option key={x.id} value={x.id}>{String(x.objective)}</option>)}</select>
          <input aria-label="Experiment variant" required placeholder="Variant" value={experiment.variant} onChange={e=>setExperiment({...experiment,variant:e.target.value})}/>
          <input aria-label="Campaign external ID" placeholder="Campaign external ID" value={experiment.campaign_external_id} onChange={e=>setExperiment({...experiment,campaign_external_id:e.target.value})}/>
          <input aria-label="Ad external ID" placeholder="Ad external ID" value={experiment.ad_external_id} onChange={e=>setExperiment({...experiment,ad_external_id:e.target.value})}/>
          <button disabled={!canWrite||busy}>Create experiment</button>
        </form>
        <div className="ci-list">{overview.experiments.map(x=><article key={x.id}><b>{String(x.variant)}</b><p>{String(hypothesisMap.get(String(x.hypothesis_id))?.objective||'Linked hypothesis')}</p><small>{x.assets?.length||0} linked asset(s) · {String(x.status||'DRAFT')}</small></article>)}</div>
      </section>
      <section className="surface-card"><h3>Link existing asset</h3><form className="ci-form" onSubmit={e=>{e.preventDefault();if(!selectedAsset||!assetLink.experiment_id)return;void mutate('/api/intelligence/experiments/'+assetLink.experiment_id+'/assets',{asset_id:selectedAsset.id,asset_kind:selectedAsset.kind},()=>setAssetLink({experiment_id:'',asset_key:''}))}}>
        <select aria-label="Asset experiment" required value={assetLink.experiment_id} onChange={e=>setAssetLink({...assetLink,experiment_id:e.target.value})}><option value="">Choose experiment</option>{overview.experiments.map(x=><option key={x.id} value={x.id}>{String(x.variant)}</option>)}</select>
        <select aria-label="Existing asset" required value={assetLink.asset_key} onChange={e=>setAssetLink({...assetLink,asset_key:e.target.value})}><option value="">Choose existing asset</option>{assetOptions.map(x=><option key={x.key} value={x.key}>{x.label} · {x.kind}</option>)}</select>
        <button disabled={!canWrite||busy}>Link asset</button>
      </form></section>
      <section className="surface-card"><h3>Provider capability registry</h3><p className="section-intro">Read-only capability metadata. This surface does not enable paid generation.</p><div className="ci-list">{overview.provider_capabilities.length?overview.provider_capabilities.map(x=><article key={x.id}><b>{String(x.provider)} / {String(x.model)}</b><p>Reference fidelity: {String(x.reference_fidelity_capability||'NONE')} · {Number(x.enabled)?'Enabled':'Disabled'}</p></article>):<p className="muted">No provider capabilities registered.</p>}</div></section>
    </div>
  </section>
}
