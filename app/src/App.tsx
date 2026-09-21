import { useState } from 'react'
import './App.css'

type Screen = 'home' | 'brand' | 'director' | 'storyboard'

const nav = [
  ['home', 'Home'], ['brand', 'Brand Brain'], ['director', 'Creative Director'], ['storyboard', 'Storyboard'],
  ['assets', 'Assets'], ['generate', 'Generate'], ['review', 'Review'],
  ['costs', 'Costs'], ['settings', 'Settings'],
] as const

const scenes = [
  ['01', 'Hook', 'AI VIDEO', '5s'], ['02', 'Command Center', 'REAL UI', '8s'],
  ['03', 'Live Fleet', 'REAL UI', '7s'], ['04', 'Dispatch', 'REAL UI', '8s'],
  ['05', 'Accountability', 'REAL UI', '7s'], ['06', 'Profitability', 'REAL UI', '8s'],
  ['07', 'Intelligence', 'REAL UI', '8s'], ['08', 'Close', 'TYPOGRAPHY', '7s'],
]

function App() {
  const [screen, setScreen] = useState<Screen>('home')
  const [selectedScene, setSelectedScene] = useState(1)

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">C</span><strong>Creative<span>OS</span></strong></div>
      <nav>{nav.map(([id, label]) => <button key={id} className={screen === id ? 'active' : ''}
        onClick={() => ['home','brand','director','storyboard'].includes(id) && setScreen(id as Screen)}>{label}</button>)}</nav>
      <div className="local-badge">● LOCAL V1</div>
    </aside>
    <main>
      <header className="topbar"><div><b>FleetPilot</b><span>/ Launch Explainer</span></div><div className="top-actions"><span>Saved locally</span><button className="ghost">⌘ K</button><button className="primary">Run Director</button></div></header>
      {screen === 'home' && <Home onStart={() => setScreen('director')} />}
      {screen === 'brand' && <BrandBrain />}
      {screen === 'director' && <Director onStoryboard={() => setScreen('storyboard')} />}
      {screen === 'storyboard' && <Storyboard selected={selectedScene} onSelect={setSelectedScene} />}
    </main>
  </div>
}
function Home({ onStart }: { onStart: () => void }) {
  return <section className="page home-page">
    <div className="eyebrow">AI CREATIVE PRODUCTION OS</div>
    <h1>Create something that moves the business.</h1>
    <p className="lede">Plan, direct, generate, review, and export from one local creative workspace.</p>
    <div className="command-card">
      <textarea defaultValue="Create a 60-second FleetPilot explainer for Philippine trucking owners." />
      <div className="command-row"><div className="chips"><span>60s Explainer</span><span>Real UI First</span><span>Balanced Cost</span></div><button className="primary" onClick={onStart}>Direct Campaign →</button></div>
    </div>
    <div className="section-head"><h2>Recent campaigns</h2><span>4 active</span></div>
    <div className="campaign-grid">{['FleetPilot Explainer','SmartRoom Launch','JB Cabinet Promo','Product Screens'].map((x,i)=><article className="campaign-card" key={x}><div className={`thumb t${i+1}`}></div><b>{x}</b><span>{i===0?'Storyboard ready':'Draft'} · {8-i} scenes</span></article>)}</div>
  </section>
}

type DirectorTab = 'Strategy' | 'Script' | 'Visual Plan' | 'Asset Needs' | 'Budget'
type DirectorProposal = { version:number; status:'DRAFT'|'APPROVED'; hook:string; scenes:number; realUi:number; duration:number; low:number; high:number }

function Director({ onStoryboard }: { onStoryboard: () => void }) {
  const [objective,setObjective]=useState('Create a 60-second FleetPilot explainer for Philippine trucking owners.')
  const [audience,setAudience]=useState('Philippine trucking company owners, managers, dispatchers, operators')
  const [offer,setOffer]=useState('Operational control, dispatch visibility, trip profitability, accountability')
  const [cta,setCta]=useState('See FleetPilot in action')
  const [format,setFormat]=useState('60s Explainer')
  const [duration,setDuration]=useState(60)
  const [ratio,setRatio]=useState('16:9')
  const [tab,setTab]=useState<DirectorTab>('Strategy')
  const [proposals,setProposals]=useState<DirectorProposal[]>(()=>{const raw=localStorage.getItem('creativeos.director.fleetpilot');return raw?JSON.parse(raw) as DirectorProposal[]:[]})
  const current=proposals.at(-1)
  const generate=()=>{const next:DirectorProposal={version:(current?.version??0)+1,status:'DRAFT',hook:'Profit leaks start where visibility ends.',scenes:8,realUi:85,duration:58,low:80,high:250};const all=[...proposals,next];setProposals(all);localStorage.setItem('creativeos.director.fleetpilot',JSON.stringify(all))}
  const approve=()=>{if(!current)return;const all=proposals.map((p,i)=>i===proposals.length-1?{...p,status:'APPROVED' as const}:p);setProposals(all);localStorage.setItem('creativeos.director.fleetpilot',JSON.stringify(all))}
  return <section className="page director-grid">
    <div className="director-main"><div className="eyebrow">CREATIVE DIRECTOR</div><h1>Turn the brief into a production plan.</h1>
      <div className="panel"><label>Campaign objective</label><textarea aria-label="Campaign objective" value={objective} onChange={e=>setObjective(e.target.value)} /></div>
      <div className="two-col"><div className="panel"><label>Audience</label><textarea aria-label="Director audience" value={audience} onChange={e=>setAudience(e.target.value)} /></div><div className="panel"><label>Core offer</label><textarea aria-label="Core offer" value={offer} onChange={e=>setOffer(e.target.value)} /></div></div>
      <div className="two-col"><div className="panel"><label>CTA</label><input aria-label="CTA" value={cta} onChange={e=>setCta(e.target.value)} /></div><div className="panel"><label>Format</label><select aria-label="Campaign format" value={format} onChange={e=>setFormat(e.target.value)}><option>60s Explainer</option><option>30s Ad</option><option>15s Reel</option><option>Product Walkthrough</option><option>Landing Hero</option></select></div></div>
      <div className="panel production-row"><label>Production controls</label><input aria-label="Duration" type="number" value={duration} onChange={e=>setDuration(Number(e.target.value))}/><select aria-label="Aspect ratio" value={ratio} onChange={e=>setRatio(e.target.value)}><option>16:9</option><option>9:16</option><option>1:1</option></select><span>English</span><span>Real UI 85%</span><span>Generated 15%</span></div>
      <div className="panel lock-strip"><label>Brand locks</label><span>✓ Logo</span><span>✓ Palette</span><span>✓ Real UI preservation</span><span>✓ Tone</span></div>
      <div className="director-tabs">{(['Strategy','Script','Visual Plan','Asset Needs','Budget'] as DirectorTab[]).map(t=><button className={tab===t?'active':''} onClick={()=>setTab(t)} key={t}>{t}</button>)}</div>
      <div className="panel director-output">{!current?<p>Generate a strategy to create the first Director proposal.</p>:<DirectorTabView tab={tab} proposal={current} offer={offer} cta={cta}/>}</div>
    </div>
    <aside className="intel-panel"><div className="ai-status">● MOCK DIRECTOR</div><h2>{current?'Director proposal':'Ready to generate'}</h2>{current&&<><div className="strategy-block"><small>HOOK</small><b>{current.hook}</b></div><div className="metric-row"><div><small>SCENES</small><b>{current.scenes}</b></div><div><small>REAL UI</small><b>{current.realUi}%</b></div><div><small>DURATION</small><b>{current.duration}s</b></div></div><div className="strategy-block"><small>STATUS</small><b className={current.status==='APPROVED'?'good':''}>{current.status} · V{current.version}</b></div></>}
      <button className="ghost wide" onClick={generate}>{current?'Regenerate Strategy':'Generate Strategy'}</button><button className="primary wide" disabled={!current} onClick={approve}>Approve Plan</button><button className="primary wide" disabled={!current||current.status!=='APPROVED'} onClick={onStoryboard}>Send to Storyboard →</button></aside>
  </section>
}
function DirectorTabView({tab,proposal,offer,cta}:{tab:DirectorTab;proposal:DirectorProposal;offer:string;cta:string}) {
  if(tab==='Strategy') return <div><h2>Product truth first</h2><p><b>Primary promise:</b> {offer}</p><p><b>CTA:</b> {cta}</p><p>Problem → product visibility → operational proof → action.</p></div>
  if(tab==='Script') return <div><h2>Scene-linked script</h2><p>01 Hook · Profit leaks start where visibility ends.</p><p>02–07 Product proof through approved real FleetPilot UI.</p><p>08 Close · {cta}</p></div>
  if(tab==='Visual Plan') return <div><h2>Visual plan</h2><p>85% REAL UI using compositing only. 15% restrained cinematic support footage.</p><p>Approved UI is never regenerated.</p></div>
  if(tab==='Asset Needs') return <div><h2>Asset needs</h2><p>Primary logo · approved dashboard screenshots · dispatch UI · profitability UI · voiceover.</p></div>
  return <div><h2>Budget estimate</h2><p>ESTIMATE · low ₱{proposal.low} / high ₱{proposal.high}</p><p>REAL UI scenes are compositing-only and carry no generation estimate in Batch 4.</p></div>
}
type StoryTab='Direction'|'Script'|'Visual'|'Assets'|'Generation'|'Versions'
type UIScene={id:string;title:string;type:string;duration:number;status:string;approval:string;locked:boolean;qa:string;low:number;high:number;versions:number}
const INITIAL_UI_SCENES:UIScene[]=scenes.map((s,i)=>({id:s[0],title:s[1],type:s[2].replaceAll(' ','_'),duration:Number(s[3].replace('s','')),status:'READY',approval:'DRAFT',locked:false,qa:'READY',low:i===0?18:0,high:i===0?35:0,versions:0}))

function Storyboard({ selected, onSelect }: { selected: number; onSelect: (i:number)=>void }) {
  const [items,setItems]=useState<UIScene[]>(()=>{const raw=localStorage.getItem('creativeos.storyboard.fleetpilot');return raw?JSON.parse(raw) as UIScene[]:INITIAL_UI_SCENES})
  const [tab,setTab]=useState<StoryTab>('Direction')
  const active=items[selected]??items[0]
  const persist=(next:UIScene[])=>{setItems(next);localStorage.setItem('creativeos.storyboard.fleetpilot',JSON.stringify(next))}
  const patch=(values:Partial<UIScene>)=>persist(items.map((x,i)=>i===selected?{...x,...values}:x))
  const duplicate=()=>persist([...items,{...active,id:String(items.length+1).padStart(2,'0'),title:active.title+' Copy',approval:'DRAFT',locked:false,versions:0}])
  const remove=()=>{if(active.locked||active.approval==='APPROVED')return;const next=items.filter((_,i)=>i!==selected);persist(next);onSelect(Math.max(0,selected-1))}
  const move=(delta:number)=>{const j=selected+delta;if(j<0||j>=items.length)return;const next=[...items];[next[selected],next[j]]=[next[j],next[selected]];persist(next);onSelect(j)}
  const version=()=>patch({versions:active.versions+1})
  const total=items.reduce((a,x)=>a+x.duration,0), low=items.reduce((a,x)=>a+x.low,0), high=items.reduce((a,x)=>a+x.high,0)
  const approved=items.filter(x=>x.approval==='APPROVED').length, ready=items.filter(x=>x.status==='READY').length
  return <section className="page storyboard-page">
    <div className="story-head"><div><div className="eyebrow">STORYBOARD</div><h1>FleetPilot Explainer</h1><p>{total}s · ESTIMATE ₱{low}–₱{high} · {approved} approved · {ready} ready</p></div><div><button className="ghost">Preview</button><button className="primary">Generate Ready Scenes</button></div></div>
    <div className="scene-strip">{items.map((x,i)=><button key={x.id} onClick={()=>onSelect(i)} className={'scene-card '+(selected===i?'selected':'')}><div className={'scene-preview p'+((i%8)+1)}></div><small>SCENE {String(i+1).padStart(2,'0')} · {x.duration}s {x.locked?'· LOCKED':''}</small><b>{x.title}</b><span className={x.type==='REAL_UI'?'real':'ai'}>{x.type}</span><small>{x.status} · {x.approval} · QA {x.qa}</small></button>)}</div>
    <div className="scene-workspace">
      <div className="panel scene-editor">
        <div className="tabs">{(['Direction','Script','Visual','Assets','Generation','Versions'] as StoryTab[]).map(t=><button key={t} className={tab===t?'active':''} onClick={()=>setTab(t)}>{t}</button>)}</div>
        <StoryboardTab tab={tab} scene={active} onVersion={version}/>
        <div className="scene-actions"><button onClick={()=>move(-1)}>Move Left</button><button onClick={()=>move(1)}>Move Right</button><button onClick={duplicate}>Duplicate</button><button onClick={()=>patch({locked:!active.locked})}>{active.locked?'Unlock':'Lock'}</button><button onClick={()=>patch({approval:active.approval==='APPROVED'?'DRAFT':'APPROVED'})}>{active.approval==='APPROVED'?'Unapprove':'Approve'}</button><button onClick={remove}>Delete</button></div>
      </div>
      <aside className="panel inspector"><h3>Scene Inspector</h3><div className="kv"><span>Duration</span><b>{active.duration}s</b></div><div className="kv"><span>Output</span><b>16:9 · 1080p</b></div><div className="kv"><span>Scene type</span><b>{active.type}</b></div><div className="kv"><span>UI preservation</span><b className={active.type==='REAL_UI'?'good':''}>{active.type==='REAL_UI'?'LOCKED · COMPOSITING ONLY':'STANDARD'}</b></div><div className="kv"><span>Approval</span><b>{active.approval}</b></div><div className="kv"><span>Lock</span><b>{active.locked?'LOCKED':'OPEN'}</b></div><div className="kv"><span>QA</span><b className="good">{active.qa}</b></div><div className="cost-box"><small>ESTIMATED GENERATION</small><b>₱{active.low}–₱{active.high}</b></div><button className="primary wide" onClick={version}>{active.type==='REAL_UI'?'Create Compositing Version':'Generate Scene'}</button></aside>
    </div>
  </section>
}
function StoryboardTab({tab,scene,onVersion}:{tab:StoryTab;scene:UIScene;onVersion:()=>void}) {
  if(tab==='Direction') return <div><label>Scene purpose</label><h2>{scene.title}</h2><p>Advance the narrative while preserving the approved campaign strategy.</p><p>Transition in: editorial · Transition out: editorial · Motion: low</p></div>
  if(tab==='Script') return <div><h2>Script & timing</h2><p>Voiceover for {scene.title}. On-screen copy and subtitle remain editable in production.</p><p>Timing: {scene.duration}s</p></div>
  if(tab==='Visual') return <div><h2>Visual direction</h2><p>{scene.type==='REAL_UI'?'Use approved real UI only; crop, pan, focus, cursor and callouts.':'Use restrained generated/support visuals.'}</p></div>
  if(tab==='Assets') return <div><h2>Asset assignments</h2><p>{scene.type==='REAL_UI'?'Approved UI asset required · immutable':'Support visual assets may be assigned.'}</p></div>
  if(tab==='Generation') return <div><h2>Generation</h2><p>Method: {scene.type==='REAL_UI'?'COMPOSITING_ONLY':'AUTO / GENERATIVE'}</p><p>Provider recommendation: {scene.type==='REAL_UI'?'COMPOSITING':'AUTO'}</p><button onClick={onVersion}>{scene.type==='REAL_UI'?'New Compositing Version':'Generate Variant'}</button></div>
  return <div><h2>Versions</h2><p>{scene.versions?Array.from({length:scene.versions},(_,i)=>String.fromCharCode(65+i)).map(v=>'Version '+v).join(' · '):'No versions yet.'}</p><button onClick={onVersion}>Create Version</button></div>
}

type BrandState = {
  name: string; industry: string; audience: string; positioning: string;
  tagline: string; palette: string; fonts: string; immutable: boolean;
  uiFolders: string; preserve: string; adapt: string; never: string;
  logoPath: string; iconPath: string; targetMarket: string; messaging: string; prohibitedMessaging: string;
}

const FLEETPILOT_BRAND: BrandState = {
  name: 'FleetPilot', industry: 'Fleet Management SaaS / Logistics Operating System',
  audience: 'Philippine trucking company owners, managers, dispatchers, operators',
  positioning: 'One operating system for fleet visibility, dispatch control, accountability, and profitability.',
  tagline: 'Track. Dispatch. Control. Grow.', palette: '#0F1514, #56E0B0, #F5F7F6',
  fonts: 'Inter', immutable: true, uiFolders: '', logoPath: '', iconPath: '',
  targetMarket: 'Philippines', messaging: 'operational visibility, trip profitability, fleet control, accountability',
  prohibitedMessaging: 'Unsubstantiated performance or savings claims',
  preserve: 'Approved FleetPilot UI screenshots and screen recordings',
  adapt: 'Crop, scale, pan, zoom, callouts, cursor motion',
  never: 'Generative repainting, text recreation, layout regeneration',
}

function BrandBrain() {
  const [brand, setBrand] = useState<BrandState>(() => {
    const saved = localStorage.getItem('creativeos.brand.fleetpilot')
    return saved ? JSON.parse(saved) as BrandState : FLEETPILOT_BRAND
  })
  const [saved, setSaved] = useState(false)
  const update = (key: keyof BrandState, value: string | boolean) => setBrand(prev => ({...prev, [key]: value}))
  const save = () => { localStorage.setItem('creativeos.brand.fleetpilot', JSON.stringify(brand)); setSaved(true) }
  const createNew = () => { setBrand({...FLEETPILOT_BRAND, name:'', industry:'', audience:'', positioning:'', tagline:'', messaging:'', prohibitedMessaging:'', immutable:true}); setSaved(false) }
  return <section className="page brand-brain-grid">
    <div className="brand-main"><div className="eyebrow">BRAND BRAIN</div><h1>Keep every campaign unmistakably on brand.</h1>
      <div className="two-col"><div className="panel"><label>Brand identity</label><input aria-label="Brand name" value={brand.name} onChange={e=>update('name',e.target.value)} /><input aria-label="Industry" value={brand.industry} onChange={e=>update('industry',e.target.value)} /><input aria-label="Logo path" placeholder="C:\\...\logo.png" value={brand.logoPath} onChange={e=>update('logoPath',e.target.value)} /><input aria-label="Icon path" placeholder="C:\\...\icon.png" value={brand.iconPath} onChange={e=>update('iconPath',e.target.value)} /></div><div className="panel"><label>Audience</label><textarea aria-label="Audience" value={brand.audience} onChange={e=>update('audience',e.target.value)} /><input aria-label="Target market" value={brand.targetMarket} onChange={e=>update('targetMarket',e.target.value)} /></div></div>
      <div className="panel"><label>Positioning</label><textarea aria-label="Positioning" value={brand.positioning} onChange={e=>update('positioning',e.target.value)} /><input aria-label="Tagline" value={brand.tagline} onChange={e=>update('tagline',e.target.value)} /></div>
      <div className="two-col"><div className="panel"><label>Approved messaging</label><textarea aria-label="Approved messaging" value={brand.messaging} onChange={e=>update('messaging',e.target.value)} /></div><div className="panel"><label>Prohibited messaging</label><textarea aria-label="Prohibited messaging" value={brand.prohibitedMessaging} onChange={e=>update('prohibitedMessaging',e.target.value)} /></div></div>
      <div className="two-col"><div className="panel"><label>Visual system</label><input aria-label="Colors" value={brand.palette} onChange={e=>update('palette',e.target.value)} /><input aria-label="Typography" value={brand.fonts} onChange={e=>update('fonts',e.target.value)} /></div><div className="panel"><label>Approved UI folder</label><input aria-label="Approved UI folder" placeholder="C:\\..." value={brand.uiFolders} onChange={e=>update('uiFolders',e.target.value)} /><span className="path-status">{brand.uiFolders ? 'Path reference set' : 'No folder configured'}</span></div></div>
      <div className="panel protection-card"><div><label>Product UI Protection</label><h2>Preserve approved product truth</h2><p>Approved SaaS UI inherits immutable protection by default.</p></div><button aria-pressed={brand.immutable} className={brand.immutable?'toggle on':'toggle'} onClick={()=>update('immutable',!brand.immutable)}>{brand.immutable?'LOCKED':'OFF'}</button></div>
      <div className="rule-grid"><div className="panel"><label>Must preserve</label><textarea value={brand.preserve} onChange={e=>update('preserve',e.target.value)} /></div><div className="panel"><label>May adapt</label><textarea value={brand.adapt} onChange={e=>update('adapt',e.target.value)} /></div><div className="panel"><label>Never do</label><textarea value={brand.never} onChange={e=>update('never',e.target.value)} /></div></div>
    </div>
    <aside className="intel-panel"><div className="ai-status">● BRAND MEMORY READY</div><h2>{brand.name}</h2><div className="strategy-block"><small>COMPLETENESS</small><b>Core identity configured</b></div><div className="strategy-block"><small>PROTECTION</small><p>{brand.immutable?'Approved UI defaults to immutable.':'UI protection is disabled.'}</p></div><div className="strategy-block"><small>APPROVED ASSETS</small><p>{brand.uiFolders?'Local folder reference configured.':'Add a local approved UI folder.'}</p></div><button className="ghost wide" onClick={createNew}>New Brand</button><button className="primary wide" onClick={save}>Save Brand Brain</button>{saved && <p className="save-confirm">Saved locally</p>}</aside>
  </section>
}

export default App
