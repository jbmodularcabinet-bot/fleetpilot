import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CreativeIntelligence from './CreativeIntelligence'

afterEach(()=>cleanup())
const session={user:{id:'u',username:'owner',platform_admin:false},organizations:[{id:'o',name:'Org',classification:'EXTERNAL',role:'OWNER'}],scope:{organization_id:'o',brand_profile_id:'b'},version:4,csrf:'csrf'}
const base={market_intelligence:[],hypotheses:[],reference_patterns:[],experiments:[],assets:[{id:'a1',asset_kind:'ASSET',label:'Approved render',truth_level:'REAL_PROJECT',reference_fidelity_required:true}],provider_capabilities:[]}
const json=(value:unknown)=>new Response(JSON.stringify(value),{status:200})

describe('Creative Intelligence critical path',()=>{
  it('creates a scoped hypothesis without predictive conversion claims',async()=>{
    const fetcher=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{
      const path=String(input)
      if(path==='/api/intelligence'&&!init?.body)return json(base)
      if(path==='/api/intelligence/hypotheses')return json({id:'h1',...JSON.parse(String(init?.body))})
      throw Error('Unexpected '+path)
    })
    render(<CreativeIntelligence session={session} canWrite fetcher={fetcher}/>)
    expect(await screen.findByRole('heading',{name:'Evidence before generation.'})).toBeInTheDocument()
    expect(screen.getByRole('option',{name:/Approved render.*REAL PROJECT.*FIDELITY REQUIRED/i})).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Hypothesis objective'),{target:{value:'Increase qualified renovation inquiries'}})
    fireEvent.change(screen.getByLabelText('Hypothesis hook'),{target:{value:'Design before you build'}})
    fireEvent.click(screen.getByRole('button',{name:'Create hypothesis'}))
    await waitFor(()=>expect(fetcher.mock.calls.some(call=>String(call[0])==='/api/intelligence/hypotheses'&&!!call[1]?.body)).toBe(true))
    const write=fetcher.mock.calls.find(call=>String(call[0])==='/api/intelligence/hypotheses'&&call[1]?.body)
    expect(JSON.parse(String(write?.[1]?.body))).toMatchObject({objective:'Increase qualified renovation inquiries',hook:'Design before you build',evidence_state:'INSUFFICIENT'})
    expect(write?.[1]?.headers).toMatchObject({'X-Scope-Version':'4','X-CSRF-Token':'csrf'})
    expect(screen.getByText(/No predictive conversion score/i)).toBeInTheDocument()
    expect(screen.queryByText(/likely to convert/i)).not.toBeInTheDocument()
  })
})
