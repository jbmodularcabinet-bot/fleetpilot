import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import App from './App'

afterEach(() => cleanup())

describe('CreativeOS Batch 1 shell', () => {
  it('renders Campaign Home', () => {
    render(<App />)
    expect(screen.getByRole('heading', { name: /Create something/i })).toBeInTheDocument()
  })

  it('opens Creative Director from campaign command', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: /Direct Campaign/i }))
    expect(screen.getByRole('heading', { name: /Turn the brief/i })).toBeInTheDocument()
  })

  it('moves from Director to Storyboard', () => {
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Creative Director' }))
    fireEvent.click(screen.getByRole('button', { name: /Generate Strategy/i }))
    fireEvent.click(screen.getByRole('button', { name: /Approve Plan/i }))
    fireEvent.click(screen.getByRole('button', { name: /Send to Storyboard/i }))
    expect(screen.getByRole('heading', { name: 'FleetPilot Explainer' })).toBeInTheDocument()
  })
})


describe('CreativeOS Batch 3 Brand Brain', () => {
  it('renders the FleetPilot Brand Brain fixture', () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Brand Brain' }))
    expect(screen.getByRole('heading', { name: /Keep every campaign/i })).toBeInTheDocument()
    expect(screen.getByDisplayValue('FleetPilot')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'LOCKED' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('edits and saves core brand fields locally', () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Brand Brain' }))
    const name = screen.getByLabelText('Brand name')
    fireEvent.change(name, { target: { value: 'FleetPilot Pro' } })
    fireEvent.click(screen.getByRole('button', { name: /Save Brand Brain/i }))
    expect(screen.getAllByText('Saved locally').length).toBeGreaterThan(0)
    expect(JSON.parse(localStorage.getItem('creativeos.brand.fleetpilot') || '{}').name).toBe('FleetPilot Pro')
  })
})


describe('CreativeOS Batch 3 Brand creation', () => {
  it('can start a new local brand profile without losing protection defaults', () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Brand Brain' }))
    fireEvent.click(screen.getByRole('button', { name: 'New Brand' }))
    expect(screen.getByLabelText('Brand name')).toHaveValue('')
    expect(screen.getByRole('button', { name: 'LOCKED' })).toHaveAttribute('aria-pressed', 'true')
  })
})


describe('CreativeOS Batch 4 Creative Director', () => {
  it('edits brief fields, generates MOCK strategy, and shows Director tabs', () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Creative Director' }))
    fireEvent.change(screen.getByLabelText('Campaign objective'), { target: { value: 'Explain FleetPilot clearly' } })
    expect(screen.getByLabelText('Campaign objective')).toHaveValue('Explain FleetPilot clearly')
    expect(screen.getByText(/MOCK DIRECTOR/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Generate Strategy/i }))
    expect(screen.getByText(/Profit leaks start/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Script' }))
    expect(screen.getByRole('heading', { name: /Scene-linked script/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Asset Needs' }))
    expect(screen.getByRole('heading', { name: /Asset needs/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Budget' }))
    expect(screen.getAllByText(/ESTIMATE/i).length).toBeGreaterThan(0)
  })

  it('preserves approved proposal when regenerating and unlocks storyboard after approval', () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Creative Director' }))
    fireEvent.click(screen.getByRole('button', { name: /Generate Strategy/i }))
    fireEvent.click(screen.getByRole('button', { name: /Approve Plan/i }))
    expect(screen.getByText(/APPROVED · V1/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Regenerate Strategy/i }))
    expect(screen.getByText(/DRAFT · V2/i)).toBeInTheDocument()
    const stored = JSON.parse(localStorage.getItem('creativeos.director.fleetpilot') || '[]')
    expect(stored[0].status).toBe('APPROVED')
    expect(stored[1].status).toBe('DRAFT')
  })
})

describe('CreativeOS Batch 5 Storyboard production workflow', () => {
  it('renders production rollups, tabs, and REAL_UI protection', () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Storyboard' }))
    expect(screen.getAllByText(/ESTIMATE/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /Command Center/ }))
    expect(screen.getByText(/LOCKED · COMPOSITING ONLY/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Script' }))
    expect(screen.getByRole('heading', { name: /Script & timing/i })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Generation' }))
    expect(screen.getByText(/COMPOSITING_ONLY/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    expect(screen.getByRole('heading', { name: 'Versions' })).toBeInTheDocument()
  })

  it('supports lock, approve, duplicate, reorder, and local scene versioning', () => {
    localStorage.clear()
    render(<App />)
    fireEvent.click(screen.getByRole('button', { name: 'Storyboard' }))
    fireEvent.click(screen.getByRole('button', { name: 'Lock' }))
    expect(screen.getByText('LOCKED', { selector: 'b' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    expect(screen.getByText('APPROVED', { selector: 'b' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Duplicate' }))
    expect(screen.getAllByText(/Command Center Copy/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Move Right' }))
    fireEvent.click(screen.getByRole('button', { name: 'Versions' }))
    fireEvent.click(screen.getByRole('button', { name: 'Create Version' }))
    expect(screen.getByText(/Version A/)).toBeInTheDocument()
    expect(localStorage.getItem('creativeos.storyboard.fleetpilot')).toBeTruthy()
  })
})
