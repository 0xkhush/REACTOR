'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, ArrowDown, Check, ChevronRight, ChevronLeft, CircleDot, Pause, Play, RotateCcw,
  Terminal, X, Zap, Volume2, VolumeX, Layers, Database, Cpu, GitBranch,
  ShieldCheck, BookOpen, Clock, FileAudio, Sparkles, Filter, Workflow, ArrowRight,
  ArrowLeft, SkipBack, SkipForward
} from 'lucide-react'
import scenariosRaw from '@/public/data/scenarios.json'

type Route = 'engine' | 'kitchen' | 'benchmarks' | 'metrics' | 'architecture'
type DemoPhase = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7

type Timer = {
  name: string
  seconds: number
  total: number
  state: 'RUNNING' | 'PAUSED' | 'CANCELLED'
  op: string
  rev: number
}

interface Scenario {
  index: number
  code: string
  id: string
  folder: string
  domain: string
  title: string
  difficulty: string
  dialogue: { user: string; user_annotated?: string; ai: string }[]
  acting_notes: string
  disfluencies: string[]
  has_rollback: boolean
  rollback_details: { original_param?: Record<string, unknown>; corrected_param?: Record<string, unknown> } | null
  expected_tools: { function: string; args: Record<string, unknown> }[]
  actual_tools: { function: string; args: Record<string, unknown>; timestamp_start?: number; timestamp_end?: number }[]
  status: string
  elapsed_seconds: number
  passed: boolean
  tool_selection_passed: boolean
  exact_arguments_passed: boolean
  failure_reason: string
  input_peaks: number[]
  output_peaks: number[]
}

const scenarios: Scenario[] = scenariosRaw as Scenario[]

const featuredFolders = [
  'ecommerce_09_695bd157114f0d2317f88617',
  'travel_01_62a885d5b6af18b3d4579e1b',
  'travel_10_5f4a4da1575d605c43bef871',
  'travel_19_695bd157114f0d2317f88617',
  'finance_12_65e8cf8f4c7424fa062e54a3',
  'housing_09_695bd157114f0d2317f88617',
  'ecommerce_19_66f59c766e7e22e1f90d08f6',
]

function getAudioSrc(folder: string, stream: 'input' | 'output') {
  if (featuredFolders.includes(folder)) {
    return `/audio/${folder}_${stream}.mp3`
  }
  return `/api/audio?folder=${folder}&stream=${stream}`
}

const navItems: { id: Route; label: string }[] = [
  { id: 'engine', label: 'ENGINE' },
  { id: 'kitchen', label: 'KITCHEN' },
  { id: 'benchmarks', label: 'BENCHMARKS' },
  { id: 'metrics', label: 'METRICS' },
  { id: 'architecture', label: 'ARCHITECTURE & TRAINING' },
]

const traceLines = [
  ['00:00.000', 'session.created', 'req_001'],
  ['00:01.120', 'intent.proposed', 'op-01 search_flights(Mumbai)'],
  ['00:02.321', 'intent.revised', 'revision=2 destination=Delhi'],
  ['00:02.322', 'op.cancelled', 'cancelled_before_dispatch'],
  ['00:02.450', 'op.proposed', 'op-02 search_flights(Delhi)'],
  ['00:02.781', 'op.launched', 'write_gate=open'],
  ['00:03.601', 'op.succeeded', 'latency=820ms'],
]

const archStages = [
  {
    num: '01',
    name: 'MICROPHONE / WEBRTC',
    label: 'AUDIO INGESTION',
    desc: 'LiveKit Agents 1.3 WebRTC room transport. Handles full-duplex 16kHz PCM audio streaming, participant session management, and low-latency speech interruption barge-in detection.',
    file: 'src/reactor/voice/agent.py',
    metric: '16kHz Full-Duplex PCM · <150ms Barge-In',
    tag: 'WebRTC / Transport',
  },
  {
    num: '02',
    name: 'GEMINI LIVE',
    label: 'REALTIME INTELLIGENCE',
    desc: 'gemini-2.5-flash-native-audio-preview-12-2025. Multimodal speech-to-speech intelligence. Generates typed tool proposals with strict schema validation rejecting extraneous fields.',
    file: 'src/reactor/voice/agent.py:272',
    metric: 'Realtime Speech-to-Speech API',
    tag: 'Gemini Live Multimodal',
  },
  {
    num: '03',
    name: 'TURN BRIDGE',
    label: 'INTENT RECONCILER',
    desc: 'reactor.voice.turns. Intercepts streaming user transcripts and function proposals. Distinguishes self-corrections ("actually...", "no wait") from continuations, creating monotonic RequestID and Revision frames.',
    file: 'src/reactor/voice/turns.py',
    metric: 'Action Identity Hash Coalescing',
    tag: 'Turn Bridge',
  },
  {
    num: '04',
    name: 'INTENT REVISION',
    label: 'STATE LEDGER',
    desc: 'reactor.state.SessionState. Versioned slot storage. Retains validated historical slots (e.g. date, passenger_name) while cleanly mutating superseded slots (destination).',
    file: 'src/reactor/state.py',
    metric: 'Zero Slot Clobbering Guarantee',
    tag: 'Session State Machine',
  },
  {
    num: '05',
    name: 'EXECUTION CONTROLLER',
    label: 'ADMISSION GATE & DAG',
    desc: 'Central admission gate. Directs non-blocking concurrent reads and protects state-altering writes behind an async write-serialization mutex. Instantly cancels superseded proposals pre-dispatch.',
    file: 'src/reactor/controller.py',
    metric: '<1ms Overhead · Write-Gate Serialized',
    tag: 'Execution Controller',
  },
  {
    num: '06',
    name: 'TOOL REGISTRY',
    label: 'SCHEMA VALIDATOR',
    desc: 'Validates complete provider arguments against tool schemas with widened parameter types and safe defaults to prevent JSONSchema validation crashes on edge cases.',
    file: 'src/reactor/tools/base.py',
    metric: '12 Mock Tools + Timer Service',
    tag: 'Schema Tolerance',
  },
  {
    num: '07',
    name: 'BACKEND SERVICES',
    label: 'MOCK BACKENDS & LOG',
    desc: 'Executes pinned NTU Full-Duplex-Bench mock APIs across Travel, Finance, Housing, and E-Commerce. Records room-keyed, secret-redacted JSONL telemetry compliant with FDB-v3 logs.',
    file: 'src/reactor/tools/benchmark.py',
    metric: '92/100 Exact · 98/100 Tool Selection',
    tag: 'FDB-v3 Ecosystem',
  },
]

function Panel({
  title,
  eyebrow,
  children,
  className = '',
}: {
  title: string
  eyebrow?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <div>
          <span className="micro">{eyebrow ?? 'REACTOR / TELEMETRY'}</span>
          <h2>{title}</h2>
        </div>
        <span className="panel-mark">◈</span>
      </div>
      {children}
    </section>
  )
}

function Header({
  route,
  setRoute,
}: {
  route: Route
  setRoute: (route: Route) => void
}) {
  const go = (next: Route) => {
    setRoute(next)
    window.history.pushState({}, '', `/${next}`)
  }
  return (
    <header className="topbar">
      <button className="brand" onClick={() => go('engine')} aria-label="Go to engine">
        <span className="brand-mark">◈</span>
        <span>
          <strong>REACTOR</strong>
          <small>LOCAL EXECUTION RUNTIME</small>
        </span>
      </button>
      <nav>
        {navItems.map((item) => (
          <button
            key={item.id}
            className={route === item.id ? 'active' : ''}
            onClick={() => go(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <div className="top-meta">
        <span>
          <i className="status-dot" /> LOCAL
        </span>
        <span>v0.1.0</span>
        <button onClick={() => window.location.reload()}>RESET</button>
      </div>
    </header>
  )
}

interface DemoScenarioConfig {
  id: string
  name: string
  shortLabel: string
  badge: string
  audioSrc: string
  dialogue: { time: string; text: string; speaker: 'user' | 'agent'; phaseThreshold: number }[]
  revOld: { id: string; intent: string; params: [string, string][] }
  revNew: { id: string; intent: string; params: [string, string][] }
  slotRows: [string, string, string, string][]
  op1: { id: string; call: string; cancelledText: string }
  op2: { id: string; call: string; successText: string }
  phaseTimes: [number, number, number, number, number, number]
  duration: number
  trace: [string, string, string][]
  steps?: { num: string; title: string; desc: string }[]
}

function Stepper({ phase, scenario }: { phase: DemoPhase; scenario: DemoScenarioConfig }) {
  const steps = scenario.steps || [
    { num: '01', title: 'SPEECH BEGINS', desc: 'Audio VAD hold opened' },
    { num: '02', title: 'MODEL PROPOSES', desc: `${scenario.op1.id} proposed` },
    { num: '03', title: 'SELF-CORRECTION', desc: 'Verbal rollback detected' },
    { num: '04', title: 'REVISION CREATED', desc: `${scenario.revNew.id}` },
    { num: '05', title: 'CANCEL STALE', desc: `${scenario.op1.id} aborted pre-dispatch` },
    { num: '06', title: 'EXECUTE VALID', desc: `${scenario.op2.id} admitted to write gate` },
  ]
  return (
    <div className="stepper-hero">
      <div className="stepper-hero-head">
        <span className="micro">EXECUTION LIFECYCLE STEPS</span>
        <span className="stepper-phase-badge">PHASE {phase} / 6</span>
      </div>
      <div className="stepper-cards">
        {steps.map((step, i) => {
          const stepNum = i + 1
          const isDone = phase >= Math.min(stepNum + 1, 7)
          const isCurrent = phase === stepNum
          return (
            <div
              key={step.num}
              className={`step-card ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''}`}
            >
              <div className="step-card-top">
                <span className="step-card-num">{step.num}</span>
                <span className={`step-card-dot ${isCurrent ? 'pulse' : ''}`} />
              </div>
              <strong className="step-card-title">{step.title}</strong>
              <small className="step-card-desc">{step.desc}</small>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Waveform({
  active,
  frequencies = [],
}: {
  active: boolean
  frequencies?: number[]
}) {
  return (
    <div className={`waveform ${active ? 'wave-active' : ''}`} aria-label="Voice waveform">
      {Array.from({ length: 42 }).map((_, i) => {
        const freqVal = frequencies.length > 0 ? (frequencies[i % frequencies.length] / 255) * 85 : 0
        const staticBase = 12 + ((i * 17) % 32)
        const height = active && frequencies.length > 0 ? Math.min(100, Math.max(14, freqVal)) : staticBase
        return (
          <i
            key={i}
            style={{
              height: `${height}%`,
              transition: 'height 0.06s ease, background 0.15s ease',
              background: active ? (freqVal > 30 ? '#38bdf8' : '#34d399') : undefined,
              boxShadow: active && freqVal > 40 ? '0 0 6px rgba(56,189,248,0.5)' : undefined,
            }}
          />
        )
      })}
    </div>
  )
}

const demoScenarios: DemoScenarioConfig[] = [
  {
    id: 'hero',
    name: 'HERO: FLIGHT SELF-CORRECTION (Mumbai -> Delhi)',
    shortLabel: '01. Hero Flight Demo (Mumbai -> Delhi)',
    badge: 'Real-Time Voice Demo (8.3s)',
    audioSrc: '/audio/demo_engine.mp3',
    phaseTimes: [0.2, 1.2, 2.7, 4.2, 4.9, 5.3],
    duration: 8.32,
    dialogue: [
      { time: '00:00.3', text: '“Book a flight to Mumbai on Friday...”', speaker: 'user', phaseThreshold: 1 },
      { time: '00:02.7', text: '“wait, actually make that Delhi!”', speaker: 'user', phaseThreshold: 3 },
      { time: '00:05.2', text: '“Got it. Searching for flights to Delhi on Friday.”', speaker: 'agent', phaseThreshold: 6 },
    ],
    steps: [
      { num: '01', title: 'SPEECH BEGINS', desc: 'Audio VAD hold opened' },
      { num: '02', title: 'MODEL PROPOSES', desc: 'op-01 (Mumbai) proposed' },
      { num: '03', title: 'SELF-CORRECTION', desc: '"actually make that Delhi"' },
      { num: '04', title: 'REVISION CREATED', desc: 'RequestID 1, Revision 2' },
      { num: '05', title: 'CANCEL STALE', desc: 'op-01 aborted pre-dispatch' },
      { num: '06', title: 'EXECUTE VALID', desc: 'op-02 admitted to write gate' },
    ],
    revOld: {
      id: 'R-001 / REV 01',
      intent: 'search_flights',
      params: [['destination', 'Mumbai'], ['date', 'Friday'], ['passenger_name', 'Alice'], ['travel_class', 'Economy']],
    },
    revNew: {
      id: 'R-001 / REV 02',
      intent: 'search_flights',
      params: [['destination', 'Delhi'], ['date', 'Friday'], ['passenger_name', 'Alice'], ['travel_class', 'Economy']],
    },
    slotRows: [
      ['passenger_name', 'Alice', 'Alice', 'PRESERVED'],
      ['departure_date', 'Friday', 'Friday', 'PRESERVED'],
      ['destination', 'Mumbai', 'Delhi', 'UPDATED'],
      ['travel_class', 'Economy', 'Economy', 'PRESERVED'],
      ['return_date', '--', '--', '--'],
    ],
    op1: { id: 'op-01', call: 'search_flights(Mumbai)', cancelledText: 'CANCELLED_BEFORE_DISPATCH' },
    op2: { id: 'op-02', call: 'search_flights(Delhi)', successText: 'SUCCEEDED (820ms)' },
    trace: [
      ['00:00.000', 'session.created', 'req_001'],
      ['00:01.120', 'intent.proposed', 'op-01 search_flights(Mumbai)'],
      ['00:02.321', 'intent.revised', 'revision=2 destination=Delhi'],
      ['00:02.322', 'op.cancelled', 'cancelled_before_dispatch'],
      ['00:02.450', 'op.proposed', 'op-02 search_flights(Delhi)'],
      ['00:02.781', 'op.launched', 'write_gate=open'],
      ['00:03.601', 'op.succeeded', 'latency=820ms'],
    ],
  },
  {
    id: 'travel_19',
    name: 'FDB-094: TRAVEL DOUBLE CORRECTION (Rome -> Milan, June 1 -> 3)',
    shortLabel: '02. FDB Travel (Rome -> Milan)',
    badge: 'NTU FDB-v3 Grounded Voice Dialogue (22.5s)',
    audioSrc: '/audio/travel_19_seamless.mp3',
    phaseTimes: [1.0, 4.5, 6.0, 11.5, 15.5, 17.5],
    duration: 22.5,
    dialogue: [
      { time: '00:01.0', text: '“Hmm... okay so, I want to look at flights to Rome...”', speaker: 'user', phaseThreshold: 1 },
      { time: '00:05.8', text: '“no wait, I changed my mind, let\'s do Milan instead...”', speaker: 'user', phaseThreshold: 3 },
      { time: '00:11.2', text: '“And I was thinking June 1st, but actually, June 3rd works better for me.”', speaker: 'user', phaseThreshold: 4 },
      { time: '00:18.2', text: '“Sure, I found one flight to Milan on June 3rd for $450.”', speaker: 'agent', phaseThreshold: 6 },
    ],
    steps: [
      { num: '01', title: 'SPEECH BEGINS', desc: 'Audio VAD hold opened' },
      { num: '02', title: 'MODEL PROPOSES', desc: 'op-01 (Rome, June 1) proposed' },
      { num: '03', title: 'SELF-CORRECTION', desc: '"let\'s do Milan instead"' },
      { num: '04', title: 'REVISION CREATED', desc: 'Rev 2 (Milan) -> Rev 3 (June 3)' },
      { num: '05', title: 'CANCEL STALE', desc: 'op-01 aborted pre-dispatch' },
      { num: '06', title: 'EXECUTE VALID', desc: 'op-02 (Milan, June 3) admitted' },
    ],
    revOld: {
      id: 'R-019 / REV 01',
      intent: 'search_flights',
      params: [['destination', 'Rome'], ['date', 'June 1']],
    },
    revNew: {
      id: 'R-019 / REV 03',
      intent: 'search_flights',
      params: [['destination', 'Milan'], ['date', 'June 3']],
    },
    slotRows: [
      ['destination', 'Rome', 'Milan', 'UPDATED'],
      ['date', 'June 1', 'June 3', 'UPDATED'],
      ['passengers', '1', '1', 'PRESERVED'],
      ['cabin', 'Economy', 'Economy', 'PRESERVED'],
      ['return_date', '--', '--', '--'],
    ],
    op1: { id: 'op-01', call: 'search_flights(destination="Rome", date="June 1")', cancelledText: 'CANCELLED_BEFORE_DISPATCH' },
    op2: { id: 'op-02', call: 'search_flights(destination="Milan", date="June 3")', successText: 'SUCCEEDED (790ms)' },
    trace: [
      ['00:00.000', 'session.created', 'req_fdb_094'],
      ['00:01.200', 'intent.proposed', 'op-01 search_flights(Rome, June 1)'],
      ['00:05.800', 'intent.revised', 'revision=2 destination=Milan'],
      ['00:05.802', 'op.cancelled', 'cancelled_before_dispatch'],
      ['00:11.200', 'intent.revised', 'revision=3 date=June 3'],
      ['00:17.200', 'op.proposed', 'op-02 search_flights(Milan, June 3)'],
      ['00:17.350', 'op.launched', 'write_gate=open'],
      ['00:18.140', 'op.succeeded', 'latency=790ms · flight_found=$450'],
      ['00:18.200', 'agent.speech_start', '“Sure, I found one flight to Milan on June 3rd for $450.”'],
    ],
  },
  {
    id: 'ecommerce_09',
    name: 'FDB-010: E-COMMERCE CORRECTION (Running Shoes -> Hiking Boots)',
    shortLabel: '03. FDB E-Commerce (Shoes -> Boots)',
    badge: 'NTU FDB-v3 Grounded Voice Dialogue (16.1s)',
    audioSrc: '/audio/ecommerce_09_seamless.mp3',
    phaseTimes: [0.5, 2.5, 4.5, 7.5, 10.0, 11.5],
    duration: 16.1,
    dialogue: [
      { time: '00:00.5', text: '“Like... well... could you search for running shoes — actually no...”', speaker: 'user', phaseThreshold: 1 },
      { time: '00:04.5', text: '“um, I already have running shoes. Search for hiking boots instead.”', speaker: 'user', phaseThreshold: 3 },
      { time: '00:12.2', text: '“I found hiking boots premium prod one for 99.99.”', speaker: 'agent', phaseThreshold: 6 },
    ],
    steps: [
      { num: '01', title: 'SPEECH BEGINS', desc: 'Audio VAD hold opened' },
      { num: '02', title: 'MODEL PROPOSES', desc: 'op-01 (running shoes) proposed' },
      { num: '03', title: 'SELF-CORRECTION', desc: '"search for hiking boots instead"' },
      { num: '04', title: 'REVISION CREATED', desc: 'R-009, Revision 2' },
      { num: '05', title: 'CANCEL STALE', desc: 'op-01 aborted pre-dispatch' },
      { num: '06', title: 'EXECUTE VALID', desc: 'op-02 (hiking boots) admitted' },
    ],
    revOld: {
      id: 'R-009 / REV 01',
      intent: 'search_products',
      params: [['query', 'running shoes']],
    },
    revNew: {
      id: 'R-009 / REV 02',
      intent: 'search_products',
      params: [['query', 'hiking boots']],
    },
    slotRows: [
      ['query', 'running shoes', 'hiking boots', 'UPDATED'],
      ['category', 'Footwear', 'Footwear', 'PRESERVED'],
      ['max_price', '$150', '$150', 'PRESERVED'],
      ['in_stock', 'true', 'true', 'PRESERVED'],
      ['sort', 'relevance', 'relevance', 'PRESERVED'],
    ],
    op1: { id: 'op-01', call: 'search_products(query="running shoes")', cancelledText: 'CANCELLED_BEFORE_DISPATCH' },
    op2: { id: 'op-02', call: 'search_products(query="hiking boots")', successText: 'SUCCEEDED (610ms)' },
    trace: [
      ['00:00.000', 'session.created', 'req_fdb_010'],
      ['00:01.100', 'intent.proposed', 'op-01 search_products(running shoes)'],
      ['00:04.600', 'intent.revised', 'revision=2 query=hiking boots'],
      ['00:04.602', 'op.cancelled', 'cancelled_before_dispatch'],
      ['00:11.200', 'op.proposed', 'op-02 search_products(hiking boots)'],
      ['00:11.350', 'op.launched', 'write_gate=open'],
      ['00:11.960', 'op.succeeded', 'latency=610ms · in_stock=true'],
      ['00:12.200', 'agent.speech_start', '“I found hiking boots premium prod one for 99.99.”'],
    ],
  },
  {
    id: 'housing_09',
    name: 'FDB-042: HOUSING CITY CORRECTION (Boston -> Chicago)',
    shortLabel: '04. FDB Housing (Boston -> Chicago)',
    badge: 'NTU FDB-v3 Grounded Voice Dialogue (20.8s)',
    audioSrc: '/audio/housing_09_seamless.mp3',
    phaseTimes: [0.5, 3.5, 6.5, 10.5, 14.0, 15.6],
    duration: 20.8,
    dialogue: [
      { time: '00:00.5', text: '“Well... well... uh... I\'m interested in a 2-bedroom in Boston...”', speaker: 'user', phaseThreshold: 1 },
      { time: '00:06.5', text: '“wait, actually,... um, I changed my mind. Let\'s look in Chicago instead...”', speaker: 'user', phaseThreshold: 3 },
      { time: '00:10.5', text: '“and keep the max price around 2000 per month.”', speaker: 'user', phaseThreshold: 4 },
      { time: '00:15.6', text: '“I will search for 2-bedroom apartments in Chicago up to $2000.”', speaker: 'agent', phaseThreshold: 6 },
    ],
    steps: [
      { num: '01', title: 'SPEECH BEGINS', desc: 'Audio VAD hold opened' },
      { num: '02', title: 'MODEL PROPOSES', desc: 'op-01 (Boston, 2bd) proposed' },
      { num: '03', title: 'SELF-CORRECTION', desc: '"look in Chicago instead"' },
      { num: '04', title: 'REVISION CREATED', desc: 'R-042, Revision 2 (Chicago, $2k)' },
      { num: '05', title: 'CANCEL STALE', desc: 'op-01 aborted pre-dispatch' },
      { num: '06', title: 'EXECUTE VALID', desc: 'op-02 (Chicago, $2k) admitted' },
    ],
    revOld: {
      id: 'R-042 / REV 01',
      intent: 'search_apartments',
      params: [['city', 'Boston'], ['bedrooms', '2'], ['max_price', '$2,000']],
    },
    revNew: {
      id: 'R-042 / REV 02',
      intent: 'search_apartments',
      params: [['city', 'Chicago'], ['bedrooms', '2'], ['max_price', '$2,000']],
    },
    slotRows: [
      ['bedrooms', '2', '2', 'PRESERVED'],
      ['max_price', '$2,000', '$2,000', 'PRESERVED'],
      ['city', 'Boston', 'Chicago', 'UPDATED'],
      ['pets_allowed', 'None', 'None', 'PRESERVED'],
    ],
    op1: { id: 'op-01', call: 'search_apartments(city="Boston", bedrooms=2, max_price=2000)', cancelledText: 'CANCELLED_BEFORE_DISPATCH' },
    op2: { id: 'op-02', call: 'search_apartments(city="Chicago", bedrooms=2, max_price=2000)', successText: 'SUCCEEDED (640ms)' },
    trace: [
      ['00:00.000', 'session.created', 'req_fdb_042'],
      ['00:01.100', 'intent.proposed', 'op-01 search_apartments(Boston, 2bd, $2k)'],
      ['00:06.500', 'intent.revised', 'revision=2 city=Chicago'],
      ['00:06.502', 'op.cancelled', 'cancelled_before_dispatch'],
      ['00:14.600', 'op.proposed', 'op-02 search_apartments(Chicago, 2bd, $2k)'],
      ['00:14.750', 'op.launched', 'write_gate=open'],
      ['00:15.390', 'op.succeeded', 'latency=640ms · 14 units found'],
      ['00:15.600', 'agent.speech_start', '“I will search for 2-bedroom apartments in Chicago up to $2000.”'],
    ],
  },
  {
    id: 'travel_10',
    name: 'FDB-028: TRAVEL DATE CORRECTION (Miami, Oct 5 -> Oct 7)',
    shortLabel: '05. FDB Travel (Oct 5 -> Oct 7)',
    badge: 'NTU FDB-v3 Grounded Voice Dialogue (23.9s)',
    audioSrc: '/audio/travel_10_seamless.mp3',
    phaseTimes: [2.5, 5.0, 7.5, 12.0, 16.5, 18.0],
    duration: 23.95,
    dialogue: [
      { time: '00:02.6', text: '“Um, so um, I was looking at flights to Miami on October 5th...”', speaker: 'user', phaseThreshold: 1 },
      { time: '00:07.5', text: '“wait, uh, my schedule just changed. My meeting got moved...”', speaker: 'user', phaseThreshold: 3 },
      { time: '00:12.0', text: '“so actually make it October 7th instead.”', speaker: 'user', phaseThreshold: 4 },
      { time: '00:18.0', text: '“Got it, searching for flights to Miami on October 7th.”', speaker: 'agent', phaseThreshold: 6 },
    ],
    steps: [
      { num: '01', title: 'SPEECH BEGINS', desc: 'Audio VAD hold opened' },
      { num: '02', title: 'MODEL PROPOSES', desc: 'op-01 (Miami, Oct 5) proposed' },
      { num: '03', title: 'SELF-CORRECTION', desc: '"make it October 7th instead"' },
      { num: '04', title: 'REVISION CREATED', desc: 'R-028, Revision 2 (Oct 7)' },
      { num: '05', title: 'CANCEL STALE', desc: 'op-01 aborted pre-dispatch' },
      { num: '06', title: 'EXECUTE VALID', desc: 'op-02 (Miami, Oct 7) admitted' },
    ],
    revOld: {
      id: 'R-028 / REV 01',
      intent: 'search_flights',
      params: [['destination', 'Miami'], ['date', 'October 5']],
    },
    revNew: {
      id: 'R-028 / REV 02',
      intent: 'search_flights',
      params: [['destination', 'Miami'], ['date', 'October 7']],
    },
    slotRows: [
      ['destination', 'Miami', 'Miami', 'PRESERVED'],
      ['date', 'October 5', 'October 7', 'UPDATED'],
      ['passengers', '1', '1', 'PRESERVED'],
      ['cabin', 'Economy', 'Economy', 'PRESERVED'],
    ],
    op1: { id: 'op-01', call: 'search_flights(destination="Miami", date="October 5")', cancelledText: 'CANCELLED_BEFORE_DISPATCH' },
    op2: { id: 'op-02', call: 'search_flights(destination="Miami", date="October 7")', successText: 'SUCCEEDED (630ms)' },
    trace: [
      ['00:00.000', 'session.created', 'req_fdb_028'],
      ['00:03.200', 'intent.proposed', 'op-01 search_flights(Miami, Oct 5)'],
      ['00:07.600', 'intent.revised', 'meeting_rescheduled -> pending date'],
      ['00:07.602', 'op.cancelled', 'cancelled_before_dispatch'],
      ['00:12.100', 'intent.revised', 'revision=2 date=October 7'],
      ['00:17.000', 'op.proposed', 'op-02 search_flights(Miami, Oct 7)'],
      ['00:17.150', 'op.launched', 'write_gate=open'],
      ['00:17.780', 'op.succeeded', 'latency=630ms · flights_available=4'],
      ['00:18.000', 'agent.speech_start', '“Got it, searching for flights to Miami on October 7th.”'],
    ],
  },
]

function Engine() {
  const [selectedDemoIdx, setSelectedDemoIdx] = useState(0)
  const [phase, setPhase] = useState<DemoPhase>(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [liveFrequencies, setLiveFrequencies] = useState<number[]>([])
  const [isMuted, setIsMuted] = useState(false)

  const activeDemo = demoScenarios[selectedDemoIdx]

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animFrameRef = useRef<number | null>(null)

  // Switch demo scenario -> reset audio
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    setIsPlaying(false)
    setPhase(0)
    setCurrentTime(0)
    setLiveFrequencies([])
  }, [selectedDemoIdx])

  // Setup Web Audio Analyser for live frequency FFT sampling
  const setupAudio = () => {
    if (!audioRef.current || audioCtxRef.current) return
    try {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      const ctx = new AudioCtx()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 64
      const source = ctx.createMediaElementSource(audioRef.current)
      source.connect(analyser)
      analyser.connect(ctx.destination)
      audioCtxRef.current = ctx
      analyserRef.current = analyser
    } catch (e) {
      console.warn('Web Audio API restricted or active', e)
    }
  }

  // Animation frame loop to read live audio frequencies
  useEffect(() => {
    if (!isPlaying) {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      setLiveFrequencies([])
      return
    }

    const sample = () => {
      if (analyserRef.current) {
        const buffer = new Uint8Array(analyserRef.current.frequencyBinCount)
        analyserRef.current.getByteFrequencyData(buffer)
        setLiveFrequencies(Array.from(buffer.slice(0, 42)))
      }
      animFrameRef.current = requestAnimationFrame(sample)
    }
    sample()

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [isPlaying])

  const run = () => {
    if (!audioRef.current) return
    setupAudio()
    if (audioCtxRef.current && audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume()
    }

    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
    } else {
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch((err) => console.warn('Audio play error:', err))
    }
  }

  const reset = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    setIsPlaying(false)
    setPhase(0)
    setCurrentTime(0)
    setLiveFrequencies([])
  }

  const toggleMute = () => {
    if (!audioRef.current) return
    audioRef.current.muted = !isMuted
    setIsMuted(!isMuted)
  }

  const handleTimeUpdate = () => {
    if (!audioRef.current) return
    const t = audioRef.current.currentTime
    setCurrentTime(t)
    const [p1, p2, p3, p4, p5, p6] = activeDemo.phaseTimes
    if (t < p1) {
      setPhase(0)
    } else if (t < p2) {
      setPhase(1)
    } else if (t < p3) {
      setPhase(2)
    } else if (t < p4) {
      setPhase(3)
    } else if (t < p5) {
      setPhase(4)
    } else if (t < p6) {
      setPhase(5)
    } else {
      setPhase(6)
    }
  }

  const formatSec = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    const ms = Math.floor((sec % 1) * 10)
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms}`
  }

  return (
    <main className="content">
      {/* Hidden real audio element playing authentic scenario */}
      <audio
        ref={audioRef}
        src={activeDemo.audioSrc}
        preload="auto"
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || activeDemo.duration)}
        onEnded={() => {
          setIsPlaying(false)
          setPhase(7)
        }}
      />

      <div className="page-intro">
        <div className="page-intro-left">
          <span className="eyebrow">01 / ENGINE</span>
          <p className="subtitle">
            Correction-Aware Execution Engine for Interruptible Voice Agents
          </p>
          <h1>
            WHEN INTENT CHANGES,
            <br />
            <em>EXECUTION CHANGES WITH IT.</em>
          </h1>
          <p className="lede">
            Track real-time interruptions, intent revisions, cancellation cascades, concurrent
            reads, serialized writes, and action identity with real scenario audio playback.
          </p>

          {/* Scenario Selector Pills */}
          <div className="demo-scenario-strip">
            {demoScenarios.map((sc, i) => (
              <button
                key={sc.id}
                className={`demo-scenario-btn ${selectedDemoIdx === i ? 'active' : ''}`}
                onClick={() => setSelectedDemoIdx(i)}
              >
                <span>{sc.shortLabel}</span>
              </button>
            ))}
          </div>

          <div className="actions">
            <button className="btn primary" onClick={run}>
              {isPlaying ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
              {isPlaying ? 'PAUSE AUDIO' : phase === 7 ? 'PLAY AGAIN' : 'PLAY REAL AUDIO DEMO'}
            </button>
            <button className="btn" onClick={reset}>
              <RotateCcw data-icon="inline-start" /> RESET
            </button>
            <div className="audio-time-badge">
              {formatSec(currentTime)} / {formatSec(duration || activeDemo.duration)}
            </div>
            <button
              className="btn py-1 px-2 text-xs"
              onClick={toggleMute}
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? <VolumeX className="w-3.5 h-3.5 text-[#f87171]" /> : <Volume2 className="w-3.5 h-3.5" />}
            </button>
            <span className={`demo-audio-live-badge ${isPlaying ? '' : 'idle'}`}>
              <i className={`status-dot ${isPlaying ? 'pulse' : ''}`} />
              {isPlaying ? 'REAL AUDIO PLAYING' : 'READY TO PLAY'}
            </span>
          </div>
        </div>
        <Stepper phase={phase} scenario={activeDemo} />
      </div>

      <div className="grid engine-grid">
        <Panel
          title="LIVE CONVERSATION / TRANSCRIPT"
          eyebrow={`VOICE STREAM / ${activeDemo.badge.toUpperCase()}`}
          className="conversation"
        >
          <Waveform active={isPlaying} frequencies={liveFrequencies} />
          <div className="transcript">
            {activeDemo.dialogue.map((turn, tIdx) => {
              const isRevealed = phase >= turn.phaseThreshold
              return (
                <div key={tIdx} className={isRevealed ? 'revealed' : 'dim'}>
                  <time>{turn.time}</time>
                  <p className={turn.speaker === 'agent' ? 'highlight' : ''}>{turn.text}</p>
                </div>
              )
            })}
          </div>
          <div className="panel-foot">
            <span>
              <i className={`status-dot ${isPlaying ? 'pulse' : ''}`} /> {isPlaying ? 'STREAMING REAL AUDIO' : 'IDLE'}
            </span>
            <span>LATENCY 42ms · <strong className="text-[#38bdf8]">{activeDemo.badge}</strong></span>
          </div>
        </Panel>

        <Panel title="INTENT REVISIONS" eyebrow="STATE / REVISION LOG">
          <Revision phase={phase} scenario={activeDemo} />
        </Panel>

        <Panel title="SLOT PRESERVATION" eyebrow={`INSPECTOR / ${activeDemo.revOld.id.split('/')[0].trim()}`}>
          <SlotTable phase={phase} scenario={activeDemo} />
        </Panel>

        <Panel title="CANCELLATION CASCADE" eyebrow="OPERATION GRAPH">
          <Cascade phase={phase} scenario={activeDemo} />
        </Panel>

        <Panel title="LIVE TRACE" eyebrow="JSONL / STREAMING" className="wide">
          <Trace phase={phase} scenario={activeDemo} />
        </Panel>
      </div>
    </main>
  )
}

function Revision({ phase, scenario }: { phase: DemoPhase; scenario: DemoScenarioConfig }) {
  return (
    <div className="revision">
      <div className={phase >= 5 ? 'revision old struck' : 'revision old'}>
        <span className="mono">{scenario.revOld.id}</span>
        <dl>
          <dt>intent</dt>
          <dd>{scenario.revOld.intent}</dd>
          {scenario.revOld.params.map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
      <ArrowDown className="down" />
      <div className={`revision new ${phase >= 4 ? 'revealed' : 'dim'}`}>
        <span className="mono">{scenario.revNew.id}</span>
        <dl>
          <dt>intent</dt>
          <dd>{scenario.revNew.intent}</dd>
          {scenario.revNew.params.map(([k, v]) => (
            <div key={k} style={{ display: 'contents' }}>
              <dt>{k}</dt>
              <dd className={scenario.revOld.params.some(([ok, ov]) => ok === k && ov !== v) ? 'text-[#38bdf8] font-bold' : ''}>
                {v}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  )
}

function SlotTable({ phase, scenario }: { phase: DemoPhase; scenario: DemoScenarioConfig }) {
  return (
    <div className="table">
      <div className="tr th">
        <span>SLOT</span>
        <span>REV 01</span>
        <span>REV 02</span>
        <span>STATE</span>
      </div>
      {scenario.slotRows.map((row) => {
        const isUpdated = row[3] === 'UPDATED'
        const isHighlight = isUpdated && phase >= 4
        return (
          <div className={`tr ${isHighlight ? 'highlight' : ''}`} key={row[0]}>
            <span>{row[0]}</span>
            <span>{row[1]}</span>
            <span>{phase >= 4 ? row[2] : row[1]}</span>
            <span className={isHighlight ? 'text-[#38bdf8] font-bold' : 'state'}>
              {phase >= 4 ? row[3] : 'PRESERVED'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function Cascade({ phase, scenario }: { phase: DemoPhase; scenario: DemoScenarioConfig }) {
  return (
    <div className="cascade">
      <div className={`op muted ${phase >= 5 ? 'cancelled' : ''}`}>
        <b>{scenario.op1.id}</b>
        <strong>{scenario.op1.call}</strong>
        <span>PROPOSED</span>
        <ArrowDown />
        <span>{phase >= 4 ? 'SUPERSEDED' : 'QUEUED'}</span>
        <ArrowDown />
        <span>{phase >= 5 ? scenario.op1.cancelledText : 'PENDING'}</span>
        <small>BACKEND CALLS 0 &nbsp; / &nbsp; WASTED LATENCY 0ms &nbsp; / &nbsp; EXTERNAL COST $0.00</small>
      </div>
      <div className={`op ${phase >= 6 ? 'success' : ''}`}>
        <b>{scenario.op2.id}</b>
        <strong>{scenario.op2.call}</strong>
        <span>PROPOSED</span>
        <ArrowDown />
        <span>{phase >= 6 ? 'LAUNCHED' : 'QUEUED'}</span>
        <ArrowDown />
        <span>{phase >= 7 ? scenario.op2.successText : 'WAITING'}</span>
      </div>
    </div>
  )
}

function Trace({ phase, scenario }: { phase: DemoPhase; scenario: DemoScenarioConfig }) {
  return (
    <div className="trace">
      {scenario.trace.map((line, i) => (
        <div
          className={phase >= i + 1 ? 'trace-line visible' : 'trace-line'}
          key={line[0] + i}
        >
          <time>{line[0]}</time>
          <span>{line[1]}</span>
          <b>{line[2]}</b>
        </div>
      ))}
    </div>
  )
}

interface KitchenPreset {
  num: string
  name: string
  desc: string
  command: string
  slotName: string
  slotDuration: number
  audioSrc: string
  duration: number
  timeline: {
    time: number
    command: string
    intentRev: number
    slotDuration: number
    speaker: 'USER' | 'BARGE-IN' | 'GEMINI'
    text: string
    timers: Timer[]
  }[]
  finalTimers: Timer[]
}

const kitchenPresets: KitchenPreset[] = [
  {
    num: '01',
    name: 'CLASSIC CORRECTION',
    desc: 'Set a 10 minute timer for pasta... actually make that 7 minutes.',
    command: 'set a 7 minute timer for pasta',
    slotName: 'pasta',
    slotDuration: 420,
    audioSrc: '/audio/demo_kitchen_01.mp3',
    duration: 7.0,
    timeline: [
      {
        time: 0.1,
        command: 'set a 10 minute timer for pasta',
        intentRev: 1,
        slotDuration: 600,
        speaker: 'USER',
        text: '“Set a 10 minute timer for pasta...”',
        timers: [
          { name: 'PASTA', seconds: 600, total: 600, state: 'RUNNING', op: 'op-01', rev: 1 },
          { name: 'TEA', seconds: 238, total: 300, state: 'PAUSED', op: 'op-04', rev: 1 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
      {
        time: 2.5,
        command: 'set a 7 minute timer for pasta',
        intentRev: 2,
        slotDuration: 420,
        speaker: 'BARGE-IN',
        text: '“Wait, actually make that 7 minutes!”',
        timers: [
          { name: 'PASTA', seconds: 0, total: 600, state: 'CANCELLED', op: 'op-01', rev: 1 },
          { name: 'TEA', seconds: 238, total: 300, state: 'PAUSED', op: 'op-04', rev: 1 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
      {
        time: 4.8,
        command: 'set a 7 minute timer for pasta',
        intentRev: 2,
        slotDuration: 420,
        speaker: 'GEMINI',
        text: '“Pasta timer set for 7 minutes.”',
        timers: [
          { name: 'PASTA', seconds: 420, total: 420, state: 'RUNNING', op: 'op-02', rev: 2 },
          { name: 'TEA', seconds: 238, total: 300, state: 'PAUSED', op: 'op-04', rev: 1 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
    ],
    finalTimers: [
      { name: 'PASTA', seconds: 420, total: 420, state: 'RUNNING', op: 'op-02', rev: 2 },
      { name: 'TEA', seconds: 238, total: 300, state: 'PAUSED', op: 'op-04', rev: 1 },
      { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
    ],
  },
  {
    num: '02',
    name: 'DUPLICATE COALESCING',
    desc: 'Two identical proposals coalesced to single active execution.',
    command: 'set a 5 minute timer for tea',
    slotName: 'tea',
    slotDuration: 300,
    audioSrc: '/audio/demo_kitchen_02.mp3',
    duration: 10.3,
    timeline: [
      {
        time: 0.1,
        command: 'set a 5 minute timer for tea',
        intentRev: 1,
        slotDuration: 300,
        speaker: 'USER',
        text: '“Set a 5 minute timer for tea.”',
        timers: [
          { name: 'TEA', seconds: 300, total: 300, state: 'RUNNING', op: 'op-05', rev: 1 },
          { name: 'PASTA', seconds: 396, total: 420, state: 'RUNNING', op: 'op-02', rev: 2 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
      {
        time: 3.0,
        command: 'set a 5 minute timer for tea',
        intentRev: 1,
        slotDuration: 300,
        speaker: 'USER',
        text: '“Set a 5 minute timer for tea.” (Duplicate Proposal)',
        timers: [
          { name: 'TEA', seconds: 300, total: 300, state: 'RUNNING', op: 'op-05', rev: 1 },
          { name: 'PASTA', seconds: 396, total: 420, state: 'RUNNING', op: 'op-02', rev: 2 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
      {
        time: 6.0,
        command: 'set a 5 minute timer for tea',
        intentRev: 1,
        slotDuration: 300,
        speaker: 'GEMINI',
        text: '“Tea timer already active for 5 minutes. Coalescing duplicate proposal.”',
        timers: [
          { name: 'TEA', seconds: 300, total: 300, state: 'RUNNING', op: 'op-05', rev: 1 },
          { name: 'PASTA', seconds: 396, total: 420, state: 'RUNNING', op: 'op-02', rev: 2 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
    ],
    finalTimers: [
      { name: 'TEA', seconds: 300, total: 300, state: 'RUNNING', op: 'op-05', rev: 1 },
      { name: 'PASTA', seconds: 396, total: 420, state: 'RUNNING', op: 'op-02', rev: 2 },
      { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
    ],
  },
  {
    num: '03',
    name: 'EXPLICIT CANCELLATION',
    desc: 'Cancel the pasta timer before dispatch completes.',
    command: 'cancel the pasta timer',
    slotName: 'pasta',
    slotDuration: 0,
    audioSrc: '/audio/demo_kitchen_03.mp3',
    duration: 4.8,
    timeline: [
      {
        time: 0.1,
        command: 'cancel the pasta timer',
        intentRev: 3,
        slotDuration: 0,
        speaker: 'USER',
        text: '“Cancel the pasta timer.”',
        timers: [
          { name: 'PASTA', seconds: 0, total: 420, state: 'CANCELLED', op: 'op-02', rev: 3 },
          { name: 'TEA', seconds: 238, total: 300, state: 'RUNNING', op: 'op-04', rev: 1 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
      {
        time: 2.8,
        command: 'cancel the pasta timer',
        intentRev: 3,
        slotDuration: 0,
        speaker: 'GEMINI',
        text: '“Pasta timer cancelled before dispatch.”',
        timers: [
          { name: 'PASTA', seconds: 0, total: 420, state: 'CANCELLED', op: 'op-02', rev: 3 },
          { name: 'TEA', seconds: 238, total: 300, state: 'RUNNING', op: 'op-04', rev: 1 },
          { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
        ],
      },
    ],
    finalTimers: [
      { name: 'PASTA', seconds: 0, total: 420, state: 'CANCELLED', op: 'op-02', rev: 3 },
      { name: 'TEA', seconds: 238, total: 300, state: 'RUNNING', op: 'op-04', rev: 1 },
      { name: 'OVEN', seconds: 844, total: 900, state: 'RUNNING', op: 'op-06', rev: 1 },
    ],
  },
  {
    num: '04',
    name: 'RAPID REVISION',
    desc: 'Multiple quick revisions: pasta to 8m, tea to 4m, oven to 20m.',
    command: 'set a 8 minute timer for pasta',
    slotName: 'pasta',
    slotDuration: 480,
    audioSrc: '/audio/demo_kitchen_04.mp3',
    duration: 11.5,
    timeline: [
      {
        time: 0.1,
        command: 'set pasta 8m, tea 4m, oven 20m',
        intentRev: 4,
        slotDuration: 480,
        speaker: 'USER',
        text: '“Set pasta to 8 minutes, tea to 4 minutes, and oven to 20 minutes.”',
        timers: [
          { name: 'PASTA', seconds: 480, total: 480, state: 'RUNNING', op: 'op-07', rev: 4 },
          { name: 'TEA', seconds: 240, total: 240, state: 'RUNNING', op: 'op-08', rev: 2 },
          { name: 'OVEN', seconds: 1200, total: 1200, state: 'RUNNING', op: 'op-09', rev: 2 },
        ],
      },
      {
        time: 6.0,
        command: 'set pasta 8m, tea 4m, oven 20m',
        intentRev: 4,
        slotDuration: 480,
        speaker: 'GEMINI',
        text: '“All three timers updated: pasta to 8 minutes, tea to 4 minutes, and oven to 20 minutes.”',
        timers: [
          { name: 'PASTA', seconds: 480, total: 480, state: 'RUNNING', op: 'op-07', rev: 4 },
          { name: 'TEA', seconds: 240, total: 240, state: 'RUNNING', op: 'op-08', rev: 2 },
          { name: 'OVEN', seconds: 1200, total: 1200, state: 'RUNNING', op: 'op-09', rev: 2 },
        ],
      },
    ],
    finalTimers: [
      { name: 'PASTA', seconds: 480, total: 480, state: 'RUNNING', op: 'op-07', rev: 4 },
      { name: 'TEA', seconds: 240, total: 240, state: 'RUNNING', op: 'op-08', rev: 2 },
      { name: 'OVEN', seconds: 1200, total: 1200, state: 'RUNNING', op: 'op-09', rev: 2 },
    ],
  },
]

function Kitchen() {
  const [selectedPreset, setSelectedPreset] = useState(0)
  const activePreset = kitchenPresets[selectedPreset]

  const [timers, setTimers] = useState<Timer[]>(kitchenPresets[0].finalTimers)
  const [command, setCommand] = useState(kitchenPresets[0].command)
  const [intentRev, setIntentRev] = useState(2)
  const [slotDuration, setSlotDuration] = useState(kitchenPresets[0].slotDuration)

  // Real audio state
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const [isPlayingAudio, setIsPlayingAudio] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(kitchenPresets[0].duration)
  const [currentSpeech, setCurrentSpeech] = useState<{
    speaker: 'USER' | 'BARGE-IN' | 'GEMINI'
    text: string
  } | null>(null)

  // Natural countdown timer ticker
  useEffect(() => {
    const id = window.setInterval(() => {
      setTimers((ts) =>
        ts.map((t) =>
          t.state === 'RUNNING' && t.seconds > 0 ? { ...t, seconds: t.seconds - 1 } : t
        )
      )
    }, 1000)
    return () => window.clearInterval(id)
  }, [])

  // Switch scenario preset -> reset audio and states
  const selectPreset = (idx: number) => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    setIsPlayingAudio(false)
    setCurrentTime(0)
    setSelectedPreset(idx)
    const p = kitchenPresets[idx]
    setTimers(p.finalTimers)
    setCommand(p.command)
    setIntentRev(idx + 1)
    setSlotDuration(p.slotDuration)
    setCurrentSpeech(null)
  }

  const runAudio = () => {
    if (!audioRef.current) return
    if (isPlayingAudio) {
      audioRef.current.pause()
      setIsPlayingAudio(false)
    } else {
      audioRef.current
        .play()
        .then(() => setIsPlayingAudio(true))
        .catch((err) => console.warn('Audio play error:', err))
    }
  }

  const resetAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
    }
    setIsPlayingAudio(false)
    setCurrentTime(0)
    const p = kitchenPresets[selectedPreset]
    setTimers(p.finalTimers)
    setCommand(p.command)
    setIntentRev(selectedPreset + 1)
    setSlotDuration(p.slotDuration)
    setCurrentSpeech(null)
  }

  const handleTimeUpdate = () => {
    if (!audioRef.current) return
    const t = audioRef.current.currentTime
    setCurrentTime(t)

    // Find active timeline entry for current timestamp
    const entries = activePreset.timeline
    let activeEntry = entries[0]
    for (const e of entries) {
      if (t >= e.time) {
        activeEntry = e
      }
    }

    if (activeEntry) {
      setCommand(activeEntry.command)
      setIntentRev(activeEntry.intentRev)
      setSlotDuration(activeEntry.slotDuration)
      setCurrentSpeech({ speaker: activeEntry.speaker, text: activeEntry.text })
      setTimers(activeEntry.timers)
    }
  }

  const formatSec = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    const ms = Math.floor((sec % 1) * 10)
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms}`
  }

  const toggle = (name: string) =>
    setTimers((ts) =>
      ts.map((t) =>
        t.name === name ? { ...t, state: t.state === 'RUNNING' ? 'PAUSED' : 'RUNNING' } : t
      )
    )

  const cancel = (name: string) =>
    setTimers((ts) => ts.map((t) => (t.name === name ? { ...t, state: 'CANCELLED' } : t)))

  const execute = () => {
    const match = command.match(/(\d+)\s*minute\s*timer\s*for\s*(tea|pasta|oven)/i)
    if (match) {
      setTimers((ts) => [
        {
          name: match[2].toUpperCase(),
          seconds: Number(match[1]) * 60,
          total: Number(match[1]) * 60,
          state: 'RUNNING',
          op: 'op-0' + (ts.length + 2),
          rev: intentRev + 1,
        },
        ...ts.filter((t) => t.name !== match[2].toUpperCase()),
      ])
      setIntentRev((r) => r + 1)
      setSlotDuration(Number(match[1]) * 60)
    }
  }

  const activeCount = timers.filter((t) => t.state === 'RUNNING').length

  return (
    <main className="content">
      {/* Hidden real audio element playing authentic scenario */}
      <audio
        ref={audioRef}
        src={activePreset.audioSrc}
        preload="auto"
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || activePreset.duration)}
        onEnded={() => {
          setIsPlayingAudio(false)
          setTimers(activePreset.finalTimers)
        }}
      />

      <PageHeading
        eyebrow="02 / KITCHEN PLAYGROUND"
        subtitle="Offline sandbox for testing correction-aware execution with real scenario audio."
      />
      <div className="kitchen-layout">
        <Panel title="DEMO SCENARIOS" eyebrow="SCENARIO REGISTRY" className="kitchen-scenario-panel">
          <div className="scenario-list">
            {kitchenPresets.map((s, i) => (
              <button
                key={s.name}
                className={`scenario ${selectedPreset === i ? 'selected' : ''}`}
                onClick={() => selectPreset(i)}
              >
                <span>{s.num}</span>
                <b>{s.name}</b>
                <small>{s.desc}</small>
              </button>
            ))}
          </div>
        </Panel>

        <div className="timer-area">
          <div className="kitchen-controls-bar">
            <div className="flex items-center gap-2">
              <button
                className={`btn ${isPlayingAudio ? 'primary' : ''} text-xs py-1 px-3`}
                onClick={runAudio}
              >
                {isPlayingAudio ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
                {isPlayingAudio ? 'PAUSE VOICE' : 'PLAY VOICE DEMO'}
              </button>
              <button className="btn text-xs py-1 px-2.5" onClick={resetAudio}>
                <RotateCcw data-icon="inline-start" /> RESET
              </button>
              <div className="audio-time-badge text-xs">
                {formatSec(currentTime)} / {formatSec(duration || activePreset.duration)}
              </div>
            </div>
            {isPlayingAudio && (
              <div className="live-audio-pill">
                <Volume2 className="w-3.5 h-3.5 text-[#38bdf8] animate-pulse" />
                <span className="pill-text text-[#38bdf8]">VOICE AUDIO PLAYING</span>
              </div>
            )}
          </div>

          <div className={`kitchen-speech-ticker ${currentSpeech?.speaker === 'BARGE-IN' ? 'bargein' : ''}`}>
            <span
              className={`kitchen-speaker-tag ${
                currentSpeech?.speaker === 'BARGE-IN'
                  ? 'tag-bargein'
                  : currentSpeech?.speaker === 'GEMINI'
                  ? 'tag-gemini'
                  : 'tag-user'
              }`}
            >
              {currentSpeech?.speaker === 'BARGE-IN'
                ? '⚡ BARGE-IN'
                : currentSpeech?.speaker === 'GEMINI'
                ? '🤖 GEMINI LIVE'
                : '🗣️ USER VOICE'}
            </span>
            <span className="kitchen-speech-text">
              {currentSpeech ? currentSpeech.text : `Ready. Click "PLAY VOICE DEMO" to hear audio replay.`}
            </span>
          </div>

          <div className="section-label">
            ACTIVE TIMERS <span>{activeCount} / 8 SLOTS</span>
          </div>

          <div className="timer-grid">
            {timers.map((t) => (
              <TimerCard
                key={t.name}
                timer={t}
                onToggle={() => toggle(t.name)}
                onCancel={() => cancel(t.name)}
              />
            ))}
          </div>

          <Panel title="COMMAND" eyebrow="LOCAL CONTROLLER">
            <div className="command">
              <Terminal />
              <input
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && execute()}
                aria-label="Command input"
              />
              <button className="btn primary" onClick={execute}>
                EXECUTE
              </button>
            </div>
          </Panel>
        </div>

        <Panel title="CONTROLLER STATE" eyebrow="STATE / JSON" className="kitchen-state-panel">
          <pre className="json">
            {JSON.stringify(
              {
                request_id: `req-00${selectedPreset + 1}`,
                intent_revision: intentRev,
                slots: {
                  timer_name: activePreset.slotName,
                  duration: slotDuration,
                },
                operations: timers.map((t) => ({
                  id: t.op,
                  tool: 'create_timer',
                  state: t.state.toLowerCase(),
                })),
              },
              null,
              2
            )}
          </pre>
        </Panel>
      </div>
    </main>
  )
}

function TimerCard({
  timer,
  onToggle,
  onCancel,
}: {
  timer: Timer
  onToggle: () => void
  onCancel: () => void
}) {
  const pct = timer.total > 0 ? timer.seconds / timer.total : 0
  const fmt = `${String(Math.floor(timer.seconds / 60)).padStart(2, '0')}:${String(
    timer.seconds % 60
  ).padStart(2, '0')}`
  return (
    <div className="timer-card">
      <div className="timer-top">
        <span className="micro">TIMER / {timer.op}</span>
        <span className={timer.state === 'CANCELLED' ? 'struck' : ''}>{timer.state}</span>
      </div>
      <div className="ring" style={{ '--progress': `${pct * 360}deg` } as React.CSSProperties}>
        <div>
          <strong>{fmt}</strong>
          <small>{timer.name}</small>
        </div>
      </div>
      <div className="timer-meta">
        <span>REV-{timer.rev}</span>
        <span>QUEUE 02</span>
      </div>
      <div className="timer-actions">
        <button className="btn" onClick={onToggle}>
          {timer.state === 'RUNNING' ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
          {timer.state === 'RUNNING' ? 'PAUSE' : 'RESUME'}
        </button>
        <button className="btn" onClick={onCancel}>
          <X data-icon="inline-start" /> CANCEL
        </button>
      </div>
    </div>
  )
}

function PageHeading({ eyebrow, subtitle }: { eyebrow: string; subtitle: string }) {
  return (
    <div className="page-heading">
      <span className="eyebrow">{eyebrow}</span>
      <p className="subtitle">{subtitle}</p>
    </div>
  )
}

function Benchmarks() {
  // Default to the featured self-correction scenario (ecommerce_09)
  const defaultScenario = scenarios.find((s) => s.id === 'ecommerce_09') || scenarios[0]
  const [selected, setSelected] = useState<Scenario>(defaultScenario)
  const [filter, setFilter] = useState('All')
  const [activeStream, setActiveStream] = useState<'input' | 'output'>('input')

  // Real Audio Playback States
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [speed, setSpeed] = useState(1)
  const [liveFrequencies, setLiveFrequencies] = useState<number[]>([])

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const animFrameRef = useRef<number | null>(null)

  const visible = scenarios.filter((s) => {
    if (filter === 'All') return true
    if (filter === 'Rollback') return s.has_rollback
    return s.domain === filter
  })

  const currentAudioUrl = getAudioSrc(selected.folder, activeStream)

  // Switch scenario or stream -> reset audio
  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.currentTime = 0
      audioRef.current.playbackRate = speed
      setIsPlaying(false)
      setCurrentTime(0)
    }
  }, [selected, activeStream])

  // Setup Web Audio Analyser on first play
  const setupWebAudio = () => {
    if (!audioRef.current || audioCtxRef.current) return
    try {
      const AudioCtx =
        window.AudioContext ||
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
      const ctx = new AudioCtx()
      const analyser = ctx.createAnalyser()
      analyser.fftSize = 64
      const source = ctx.createMediaElementSource(audioRef.current)
      source.connect(analyser)
      analyser.connect(ctx.destination)
      audioCtxRef.current = ctx
      analyserRef.current = analyser
    } catch (e) {
      console.warn('Web Audio API initialized or restricted', e)
    }
  }

  // Animation loop to sample live audio frequencies
  useEffect(() => {
    if (!isPlaying) {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
      setLiveFrequencies([])
      return
    }

    const sample = () => {
      if (analyserRef.current) {
        const buffer = new Uint8Array(analyserRef.current.frequencyBinCount)
        analyserRef.current.getByteFrequencyData(buffer)
        setLiveFrequencies(Array.from(buffer.slice(0, 32)))
      }
      animFrameRef.current = requestAnimationFrame(sample)
    }
    sample()

    return () => {
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current)
    }
  }, [isPlaying])

  const togglePlay = () => {
    if (!audioRef.current) return
    setupWebAudio()

    if (audioCtxRef.current && audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume()
    }

    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
    } else {
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch((err) => console.warn('Audio play error:', err))
    }
  }

  const restartAudio = () => {
    if (!audioRef.current) return
    audioRef.current.currentTime = 0
    setCurrentTime(0)
    if (!isPlaying) {
      audioRef.current.play().then(() => setIsPlaying(true))
    }
  }

  const changeSpeed = (rate: number) => {
    setSpeed(rate)
    if (audioRef.current) {
      audioRef.current.playbackRate = rate
    }
  }

  const scrubWaveform = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!audioRef.current || duration <= 0) return
    const rect = e.currentTarget.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const percent = Math.max(0, Math.min(1, clickX / rect.width))
    const target = percent * duration
    audioRef.current.currentTime = target
    setCurrentTime(target)
  }

  const formatSec = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    const ms = Math.floor((sec % 1) * 10)
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms}`
  }

  const peaks = activeStream === 'input' ? selected.input_peaks : selected.output_peaks
  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <main className="content">
      {/* Hidden audio element bound to real scenario file */}
      <audio
        ref={audioRef}
        src={currentAudioUrl}
        preload="metadata"
        onTimeUpdate={() => setCurrentTime(audioRef.current?.currentTime || 0)}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
        onEnded={() => setIsPlaying(false)}
        onError={() => setIsPlaying(false)}
      />

      <PageHeading
        eyebrow="03 / BENCHMARK STUDIO"
        subtitle="NTU Full-Duplex-Bench (FDB-v3) 100 real scenario recordings & execution verification."
      />

      <div className="metric-strip">
        {[
          ['92 / 100', 'STRICT EXACT PASS (92%)'],
          ['98 / 100', 'TOOL SELECTION (98%)'],
          ['94 / 100', 'SEMANTIC ARG MATCH (94%)'],
          ['365', 'OFFLINE TESTS (100%)'],
        ].map((m) => (
          <div key={m[1]}>
            <strong>{m[0]}</strong>
            <span>{m[1]}</span>
          </div>
        ))}
      </div>

      <div className="bench-layout">
        <Panel title="SCENARIO EXPLORER" eyebrow="FDB-V3 / DATASET" className="bench-explorer-panel">
          <div className="filters">
            {['All', 'E-Commerce', 'Finance', 'Housing', 'Travel', 'Rollback'].map((f) => (
              <button
                key={f}
                className={filter === f ? 'filter-active' : ''}
                onClick={() => setFilter(f)}
              >
                {f}
              </button>
            ))}
          </div>
          <div className="scenario-table">
            {visible.map((s) => (
              <button
                key={s.folder}
                className={selected.folder === s.folder ? 'selected' : ''}
                onClick={() => setSelected(s)}
              >
                <b>{s.code}</b>
                <span>{s.domain}</span>
                <span>{s.difficulty}</span>
                <em className={s.passed ? '' : 'fail'}>{s.passed ? 'PASS' : 'FAIL'}</em>
              </button>
            ))}
          </div>
        </Panel>

        <div className="bench-detail">
          <Panel
            title="REAL AUDIO REPLAY & WAVEFORM"
            eyebrow={`${selected.code} / ${selected.title.toUpperCase()}`}
            className="bench-replay-panel"
          >
            {/* Real Audio Stream Switcher */}
            <div className="stream-switcher">
              <div className="stream-switcher-buttons">
                <button
                  className={`stream-tab-btn ${activeStream === 'input' ? 'active' : ''}`}
                  onClick={() => setActiveStream('input')}
                >
                  <FileAudio className="w-3 h-3" />
                  HUMAN INPUT AUDIO (48kHz)
                </button>
                <button
                  className={`stream-tab-btn ${activeStream === 'output' ? 'active' : ''}`}
                  onClick={() => setActiveStream('output')}
                >
                  <Sparkles className="w-3 h-3" />
                  GEMINI LIVE RESPONSE
                </button>
              </div>
              <div className="flex items-center gap-2">
                {selected.disfluencies.map((df) => (
                  <span key={df} className="disfluency-pill">
                    {df}
                  </span>
                ))}
                {selected.has_rollback && (
                  <span className="disfluency-pill rollback">
                    ROLLBACK TEST
                  </span>
                )}
              </div>
            </div>

            {/* Interactive Real Web Audio Waveform with Scrubber */}
            <div
              className="audio-waveform-container"
              onClick={scrubWaveform}
              title="Click or drag to scrub audio playback"
            >
              <div
                className="waveform-scrubber"
                style={{ left: `${progressPercent}%` }}
              />
              <div className={`waveform-bars ${isPlaying ? 'live-active' : ''}`}>
                {peaks.map((p, i) => {
                  const barProgress = (i / peaks.length) * 100
                  const isPlayed = progressPercent >= barProgress
                  // Dynamic height modulated by live frequency energy during playback
                  const freqBoost =
                    isPlaying && liveFrequencies.length > 0
                      ? (liveFrequencies[i % liveFrequencies.length] / 255) * 35
                      : 0
                  const height = Math.min(100, p + freqBoost)
                  return (
                    <i
                      key={i}
                      className={isPlayed ? 'played' : ''}
                      style={{ height: `${height}%` }}
                    />
                  )
                })}
              </div>
            </div>

            {/* Real Audio Controls */}
            <div className="replay-controls">
              <button className="btn primary" onClick={togglePlay}>
                {isPlaying ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
                {isPlaying ? 'PAUSE' : 'PLAY REAL AUDIO'}
              </button>
              <button className="btn" onClick={restartAudio}>
                <RotateCcw data-icon="inline-start" /> RESTART
              </button>
              <div className="audio-time-badge">
                {formatSec(currentTime)} / {formatSec(duration || selected.elapsed_seconds)}
              </div>
              <div className="flex items-center gap-1 ml-auto">
                <span className="micro mr-1">SPEED:</span>
                {[0.5, 1, 1.25, 1.5, 2].map((s) => (
                  <button
                    key={s}
                    className={`speed-btn ${speed === s ? 'active' : ''}`}
                    onClick={() => changeSpeed(s)}
                  >
                    {s}x
                  </button>
                ))}
              </div>
            </div>

            {/* Real Scenario Transcript */}
            <div className="replay-copy">
              {selected.acting_notes && (
                <div className="acting-note">
                  <strong>Notes:</strong> {selected.acting_notes}
                </div>
              )}
              {selected.dialogue.map((turn, tIdx) => (
                <div key={tIdx} className="mb-2">
                  <p>
                    <strong className="text-white">Human:</strong> “{turn.user}”
                  </p>
                  <p className="highlight">
                    <strong className="text-[#38bdf8]">Gemini Live:</strong> “{turn.ai}”
                  </p>
                </div>
              ))}
              {selected.has_rollback && selected.rollback_details && (
                <div className="mt-2 p-2 rounded bg-black/40 border border-line text-xs font-mono">
                  <span className="text-[#f87171] mr-3">
                    SUPERSEDED: {JSON.stringify(selected.rollback_details.original_param)}
                  </span>
                  <span className="text-[#34d399]">
                    RESOLVED: {JSON.stringify(selected.rollback_details.corrected_param)}
                  </span>
                </div>
              )}
            </div>
          </Panel>

          <Panel
            title="EXECUTION VERIFICATION"
            eyebrow="GROUND TRUTH / REACTOR OUTPUT"
            className="bench-verify-panel"
          >
            <div className="verify-grid">
              <pre>
                {`GROUND TRUTH / EXPECTED\n\n` +
                  JSON.stringify(selected.expected_tools, null, 2)}
              </pre>
              <pre>
                {`REACTOR ACTUAL CALLS\n\n` +
                  (selected.actual_tools.length > 0
                    ? JSON.stringify(selected.actual_tools, null, 2)
                    : '// No tool called')}
              </pre>
            </div>
            <div className={`verified ${selected.passed ? '' : 'verified-fail'}`}>
              {selected.passed ? (
                <>
                  <Check /> {selected.expected_tools.length} / {selected.expected_tools.length}{' '}
                  TOOL ARGUMENTS VERIFIED (STRICT EXACT MATCH)
                </>
              ) : (
                <>
                  <X /> {selected.failure_reason || 'TOOL/ARGUMENT DISCREPANCY DETECTED'}
                </>
              )}
            </div>
          </Panel>
        </div>
      </div>
    </main>
  )
}

function Metrics() {
  const [activeIdx, setActiveIdx] = useState(4)
  const [isAuto, setIsAuto] = useState(true)

  useEffect(() => {
    if (!isAuto) return
    const id = window.setInterval(() => {
      setActiveIdx((prev) => (prev + 1) % archStages.length)
    }, 2400)
    return () => window.clearInterval(id)
  }, [isAuto])

  const activeStage = archStages[activeIdx]

  return (
    <main className="content">
      <PageHeading
        eyebrow="04 / METRICS & ARCHITECTURE"
        subtitle="Evaluation results and execution architecture."
      />
      <div className="metric-strip four">
        {[
          ['92 / 100', 'STRICT EXACT PASS (92%)'],
          ['98 / 100', 'TOOL SELECTION (98%)'],
          ['94 / 100', 'SEMANTIC MATCH (94%)'],
          ['365', 'PASSING TESTS (100%)'],
        ].map((m) => (
          <div key={m[1]}>
            <strong>{m[0]}</strong>
            <span>{m[1]}</span>
          </div>
        ))}
      </div>

      <div className="metrics-layout">
        <Panel title="SYSTEM ARCHITECTURE" eyebrow="RUNTIME / TOPOLOGY" className="metrics-arch-panel">
          <div className="architecture-container">
            <div className="architecture-controls">
              <div className="flex items-center gap-2">
                <span className="signal-dot" />
                <span className="micro">AUTOMATED SIGNAL FLOW</span>
              </div>
              <button
                className="btn py-1 px-2.5 text-xs"
                onClick={() => setIsAuto(!isAuto)}
              >
                {isAuto ? <Pause data-icon="inline-start" /> : <Play data-icon="inline-start" />}
                {isAuto ? 'PAUSE' : 'AUTO CYCLE'}
              </button>
            </div>

            <div className="architecture-flow">
              <div className="arch-flow-nodes">
                {archStages.map((stage, idx) => {
                  const isActive = activeIdx === idx
                  return (
                    <div key={stage.num} className="arch-flow-node-wrap">
                      <button
                        className={`node ${isActive ? 'active' : ''}`}
                        onClick={() => {
                          setActiveIdx(idx)
                          setIsAuto(false)
                        }}
                      >
                        <span className="node-num">{stage.num}</span>
                        <strong className="node-name">{stage.name}</strong>
                      </button>
                      {idx < archStages.length - 1 && (
                        <div className={`arch-connector ${isActive ? 'connector-active' : ''}`}>
                          <ArrowDown className="connector-arrow" />
                          <span className="signal-pulse" />
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              <aside className="arch-inspector">
                <div className="inspector-head">
                  <span className="micro">COMPONENT INSPECTOR</span>
                  <span className="inspector-tag">{activeStage.tag}</span>
                </div>
                <div>
                  <strong className="inspector-title">{activeStage.name}</strong>
                  <p className="inspector-desc">{activeStage.desc}</p>
                </div>
                <div className="inspector-meta-row">
                  <div>
                    <span className="meta-k">FILE:</span>
                    <code className="meta-v">{activeStage.file}</code>
                  </div>
                  <div>
                    <span className="meta-k">INVARIANT / METRIC:</span>
                    <span className="meta-v highlight">{activeStage.metric}</span>
                  </div>
                </div>
              </aside>
            </div>
          </div>
        </Panel>

        <div className="metrics-side">
          <Panel title="EXECUTION LATENCY" eyebrow="WATERFALL / P95">
            <div className="waterfall">
              {[
                ['Perception', '120ms', 24],
                ['Admission', '80ms', 16],
                ['Backend Execution', '820ms', 82],
                ['Synthesis', '110ms', 22],
              ].map((row) => (
                <div key={row[0]}>
                  <span>{row[0]}</span>
                  <i style={{ width: `${row[2]}%` }} />
                  <b>{row[1]}</b>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="TECHNICAL STACK" eyebrow="SYSTEM / DEPENDENCIES">
            <div className="stack">
              <b>FRONTEND</b>
              <span>Next.js · React · TypeScript · Tailwind · Lucide</span>
              <b>BACKEND / RUNTIME</b>
              <span>FastAPI · WebSocket · Python Controller · TimerService · FDB-v3 · JSONL Trace</span>
              <em>
                <i className="status-dot" /> LOCAL RUNTIME VERIFIED (365 TESTS)
              </em>
            </div>
          </Panel>
        </div>
      </div>
    </main>
  )
}

const lifelines = [
  { id: 'user', name: 'USER (VOICE)', role: 'Speaker', badge: '16kHz Audio' },
  { id: 'webrtc', name: 'LIVEKIT WEBRTC', role: 'Transport', badge: 'Room / VAD' },
  { id: 'model', name: 'GEMINI 2.5 LIVE', role: 'Intelligence', badge: 'Native Audio' },
  { id: 'bridge', name: 'TURN BRIDGE', role: 'Reconciler', badge: 'ReqID & Rev' },
  { id: 'ledger', name: 'SESSION LEDGER', role: 'State Machine', badge: 'Slot Preservation' },
  { id: 'gate', name: 'ADMISSION GATE', role: 'Controller', badge: 'Write Mutex' },
  { id: 'tools', name: 'BACKEND TOOLS', role: 'FDB-v3 APIs', badge: 'Execution' },
]

interface SeqStep {
  num: number
  time: string
  timeSec: number
  from: number
  to: number
  label: string
  type: 'normal' | 'superseded' | 'success'
  narrative: string
  invariant: string
  stats: string
}

const sequenceSteps: SeqStep[] = [
  {
    num: 1,
    time: '+000ms',
    timeSec: 0.1,
    from: 0,
    to: 1,
    label: '16kHz Audio Stream: "Book a flight to Mumbai on Friday..."',
    type: 'normal',
    narrative: 'Human voice streams 16kHz PCM audio frames over WebRTC room connection.',
    invariant: 'Full-Duplex VAD Hold',
    stats: 'VAD: ACTIVE · 16kHz PCM',
  },
  {
    num: 2,
    time: '+120ms',
    timeSec: 0.4,
    from: 1,
    to: 2,
    label: 'Audio Frames Dispatch (WebRTC -> Gemini)',
    type: 'normal',
    narrative: 'LiveKit transport pumps real-time audio chunk directly into Gemini 2.5 Live session.',
    invariant: 'Sub-150ms Ingestion',
    stats: 'Latency: 120ms',
  },
  {
    num: 3,
    time: '+450ms',
    timeSec: 1.2,
    from: 2,
    to: 3,
    label: 'Tool Proposal: op-01 search_flights(Mumbai, Friday)',
    type: 'normal',
    narrative: 'Gemini proposes flight search based on initial user utterance before turn completes.',
    invariant: 'Early Proposal Eager Ingestion',
    stats: 'Proposals: 1 active',
  },
  {
    num: 4,
    time: '+452ms',
    timeSec: 1.5,
    from: 3,
    to: 4,
    label: 'Ledger Update: RequestID=1, Rev=1 (destination=Mumbai, date=Friday)',
    type: 'normal',
    narrative: 'Turn bridge writes provisional parameters to versioned session ledger slots.',
    invariant: 'Zero Slot Clobbering Guarantee',
    stats: 'Slots: 2 stored (rev=1)',
  },
  {
    num: 5,
    time: '+1120ms',
    timeSec: 2.7,
    from: 0,
    to: 1,
    label: 'Barge-In Speech: "wait, actually make that Delhi!"',
    type: 'superseded',
    narrative: 'User interrupts with verbal self-correction. Audio VAD immediately registers speech barge-in.',
    invariant: 'Instant Barge-In Invalidation',
    stats: 'Barge-In: DETECTED · VAD Hold',
  },
  {
    num: 6,
    time: '+1125ms',
    timeSec: 2.9,
    from: 1,
    to: 3,
    label: 'Barge-In Event -> Turn Bridge (Rev Bump 1 -> 2)',
    type: 'superseded',
    narrative: 'Turn bridge detects disfluent correction keyword ("actually"), increments Intent Revision to 2.',
    invariant: 'Monotonic Revision Ordering',
    stats: 'RequestID=1 · Rev=2',
  },
  {
    num: 7,
    time: '+1128ms',
    timeSec: 3.1,
    from: 3,
    to: 5,
    label: 'PRE-DISPATCH ABORT: cancel op-01 (rev 1 < rev 2)',
    type: 'superseded',
    narrative: 'Admission gate invalidates op-01 immediately before network dispatch. Zero cost, zero latency wasted.',
    invariant: 'Pre-Dispatch Cancellation Guarantee',
    stats: 'Saved: 1 backend call · 0ms wasted · $0.00 cost',
  },
  {
    num: 8,
    time: '+1260ms',
    timeSec: 3.8,
    from: 2,
    to: 3,
    label: 'Revised Tool Proposal: op-02 search_flights(Delhi, Friday)',
    type: 'normal',
    narrative: 'Model emits corrected tool proposal with destination="Delhi" and preserved date="Friday".',
    invariant: 'Action Identity & Slot Preservation',
    stats: 'Preserved: date="Friday"',
  },
  {
    num: 9,
    time: '+1280ms',
    timeSec: 4.8,
    from: 3,
    to: 5,
    label: 'Admit op-02 -> Acquire Write-Gate Mutex',
    type: 'success',
    narrative: 'Admission Gate checks revision validity (rev=2 matches current). Grants serialized write lock.',
    invariant: 'Write-Gate Serialization Mutex',
    stats: 'Write Mutex: ACQUIRED',
  },
  {
    num: 10,
    time: '+1290ms',
    timeSec: 5.1,
    from: 5,
    to: 6,
    label: 'Dispatch Execution: search_flights(Delhi, Friday)',
    type: 'success',
    narrative: 'Tool dispatched to pinned FDB-v3 Travel mock service with verified schema parameters.',
    invariant: 'Truthful History Invariant',
    stats: 'Dispatched: HTTP Mock 200 OK',
  },
  {
    num: 11,
    time: '+2110ms',
    timeSec: 5.3,
    from: 6,
    to: 2,
    label: 'Backend Result (820ms) -> Grounded Speech Synthesis',
    type: 'success',
    narrative: 'Tool returns 3 flights to Delhi. Gemini Live synthesizes conversational audio confirmation to user.',
    invariant: 'Deterministic Grounded Output',
    stats: 'Total Latency: 990ms · Strict Exact Match: PASS',
  },
]

function AnimatedSequenceGraph() {
  const [currentIdx, setCurrentIdx] = useState(6) // Default at the critical cancellation moment
  const [isPlaying, setIsPlaying] = useState(false)
  const [speed, setSpeed] = useState<number>(1)
  const [currentTime, setCurrentTime] = useState(0)
  const [isMuted, setIsMuted] = useState(false)

  const audioRef = useRef<HTMLAudioElement | null>(null)

  const togglePlay = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
      setIsPlaying(false)
    } else {
      audioRef.current.playbackRate = speed
      audioRef.current
        .play()
        .then(() => setIsPlaying(true))
        .catch((err) => console.warn('Sequence audio play error:', err))
    }
  }

  const handleStepSelect = (idx: number) => {
    setCurrentIdx(idx)
    if (audioRef.current) {
      audioRef.current.currentTime = sequenceSteps[idx].timeSec
      if (!isPlaying) {
        audioRef.current.playbackRate = speed
        audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {})
      }
    }
  }

  const handleRestart = () => {
    if (audioRef.current) {
      audioRef.current.currentTime = 0
      audioRef.current.playbackRate = speed
    }
    setCurrentIdx(0)
    if (!isPlaying && audioRef.current) {
      audioRef.current.play().then(() => setIsPlaying(true)).catch(() => {})
    }
  }

  const handleTimeUpdate = () => {
    if (!audioRef.current) return
    const t = audioRef.current.currentTime
    setCurrentTime(t)
    for (let i = sequenceSteps.length - 1; i >= 0; i--) {
      if (t >= sequenceSteps[i].timeSec) {
        setCurrentIdx(i)
        break
      }
    }
  }

  const changeSpeed = (s: number) => {
    setSpeed(s)
    if (audioRef.current) {
      audioRef.current.playbackRate = s
    }
  }

  const toggleMute = () => {
    if (!audioRef.current) return
    audioRef.current.muted = !isMuted
    setIsMuted(!isMuted)
  }

  const step = sequenceSteps[currentIdx]

  return (
    <div className="seq-wrapper">
      {/* Hidden real audio element playing dialogue in sync with sequence lifelines */}
      <audio
        ref={audioRef}
        src="/audio/demo_engine.mp3"
        preload="auto"
        onTimeUpdate={handleTimeUpdate}
        onEnded={() => setIsPlaying(false)}
      />

      {/* Sequence Controls Toolbar */}
      <div className="seq-toolbar">
        <div className="seq-controls">
          <button
            className={`seq-btn ${isPlaying ? 'primary' : ''}`}
            onClick={togglePlay}
            title={isPlaying ? 'Pause sequence animation & audio' : 'Play sequence animation with real audio'}
          >
            {isPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
            {isPlaying ? 'PAUSE' : 'PLAY SEQUENCE WITH REAL AUDIO'}
          </button>
          <button
            className="seq-btn"
            onClick={() => {
              const prev = currentIdx > 0 ? currentIdx - 1 : sequenceSteps.length - 1
              handleStepSelect(prev)
            }}
            title="Previous step"
          >
            <ChevronLeft className="w-3 h-3" /> STEP
          </button>
          <button
            className="seq-btn"
            onClick={() => {
              const next = (currentIdx + 1) % sequenceSteps.length
              handleStepSelect(next)
            }}
            title="Next step"
          >
            STEP <ChevronRight className="w-3 h-3" />
          </button>
          <button
            className="seq-btn"
            onClick={handleRestart}
            title="Restart from step 1"
          >
            <RotateCcw className="w-3 h-3" /> RESTART
          </button>

          <div className="seq-speed-group">
            <span className="micro mr-1">SPEED:</span>
            {[1, 1.5, 2].map((s) => (
              <button
                key={s}
                className={`speed-btn ${speed === s ? 'active' : ''}`}
                onClick={() => changeSpeed(s)}
              >
                {s}x
              </button>
            ))}
          </div>

          <button
            className="btn py-1 px-1.5 text-xs ml-1"
            onClick={toggleMute}
            title={isMuted ? 'Unmute audio' : 'Mute audio'}
          >
            {isMuted ? <VolumeX className="w-3 h-3 text-[#f87171]" /> : <Volume2 className="w-3 h-3" />}
          </button>
        </div>

        <div className="flex items-center gap-2">
          <span className={`demo-audio-live-badge ${isPlaying ? '' : 'idle'}`}>
            <i className={`status-dot ${isPlaying ? 'pulse' : ''}`} />
            {isPlaying ? 'REAL AUDIO SYNCED' : 'AUDIO READY'}
          </span>
          <span className="text-[#38bdf8] font-bold text-sm">
            STEP {String(currentIdx + 1).padStart(2, '0')} / {String(sequenceSteps.length).padStart(2, '0')}
          </span>
          <span className="audio-time-badge text-xs">{step.time}</span>
        </div>
      </div>

      {/* 7 Lifeline Headers */}
      <div className="seq-lifelines-header">
        {lifelines.map((actor, idx) => {
          const isActorActive = step.from === idx || step.to === idx
          return (
            <div
              key={actor.id}
              className={`seq-lifeline-actor ${isActorActive ? 'active' : ''}`}
            >
              <span className="seq-actor-num">0{idx + 1}</span>
              <strong className="seq-actor-name">{actor.name}</strong>
              <span className="seq-actor-badge">{actor.badge}</span>
            </div>
          )
        })}
      </div>

      {/* Lifeline Timeline Viewport */}
      <div className="seq-timeline-viewport">
        {/* Background Vertical Dashed Guide Lines */}
        <div className="seq-guides-overlay">
          {lifelines.map((actor, idx) => {
            const isActorActive = step.from === idx || step.to === idx
            return (
              <div
                key={actor.id}
                className={`seq-guide-col ${isActorActive ? 'highlighted' : ''}`}
              />
            )
          })}
        </div>

        {/* List of 11 Sequence Step Rows */}
        <div className="seq-steps-list">
          {sequenceSteps.map((s, idx) => {
            const isCurrent = currentIdx === idx
            const leftCol = Math.min(s.from, s.to)
            const rightCol = Math.max(s.from, s.to)
            const startPct = ((leftCol + 0.5) / 7) * 100
            const endPct = ((rightCol + 0.5) / 7) * 100
            const widthPct = Math.max(3, endPct - startPct)
            const isDirLeft = s.from > s.to

            let lineClass = 'seq-arrow-line'
            if (isDirLeft) lineClass += ' dir-left'
            if (s.type === 'superseded') lineClass += ' superseded-line'
            if (s.type === 'success') lineClass += ' success-line'

            let rowClass = 'seq-step-row'
            if (isCurrent) rowClass += ' current'
            if (s.type === 'superseded') rowClass += ' superseded'
            if (s.type === 'success') rowClass += ' success'

            return (
              <div
                key={s.num}
                className={rowClass}
                onClick={() => handleStepSelect(idx)}
              >
                <span className="seq-step-time">{s.time}</span>
                <div className="seq-step-canvas">
                  <div
                    className={lineClass}
                    style={{
                      left: `${startPct}%`,
                      width: `${widthPct}%`,
                    }}
                  >
                    {isCurrent && <span className="seq-pulse" />}
                    {isDirLeft ? (
                      <ArrowLeft className="w-3 h-3 text-current absolute left-0 -top-[5px]" />
                    ) : (
                      <ArrowRight className="w-3 h-3 text-current absolute right-0 -top-[5px]" />
                    )}
                    <span className="seq-arrow-label">{s.label}</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Live Step Narrative Ticker */}
      <div className="seq-narrative-ticker">
        <div className="seq-narrative-left">
          <span className="seq-invariant-tag">{step.invariant}</span>
          <span className="text-white font-bold text-sm">{step.label}</span>
          <span className="text-soft hidden md:inline text-xs">— {step.narrative}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-muted font-mono text-xs">{step.stats}</span>
        </div>
      </div>
    </div>
  )
}

function AnimatedDynamicFlowDiagram() {
  const [selectedNode, setSelectedNode] = useState(4) // Admission gate default
  const [isSimulatingCorrection, setIsSimulatingCorrection] = useState(true)
  const [isAutoCycling, setIsAutoCycling] = useState(false)

  useEffect(() => {
    if (!isAutoCycling) return
    const timer = window.setInterval(() => {
      setSelectedNode((prev) => (prev + 1) % archStages.length)
    }, 2400)
    return () => window.clearInterval(timer)
  }, [isAutoCycling])

  const stage = archStages[selectedNode]

  return (
    <div className="flow-diagram-wrap">
      {/* Flow Toolbar */}
      <div className="flow-toolbar">
        <div className="flex items-center gap-3">
          <button
            className={`flow-sim-toggle ${isSimulatingCorrection ? 'active' : ''}`}
            onClick={() => setIsSimulatingCorrection(!isSimulatingCorrection)}
          >
            <GitBranch className="w-3.5 h-3.5 text-[#f87171]" />
            <span className="font-bold">
              {isSimulatingCorrection
                ? 'SIMULATION: MID-TURN SELF-CORRECTION (ACTIVE)'
                : 'SIMULATION: CLEAN DISPATCH (STANDARD)'}
            </span>
          </button>
          <button
            className="seq-btn"
            onClick={() => setIsAutoCycling(!isAutoCycling)}
          >
            {isAutoCycling ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
            {isAutoCycling ? 'PAUSE CYCLE' : 'AUTO CYCLE'}
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs font-mono font-bold text-muted">
          <span className="signal-dot" />
          <span>REAL-TIME STREAMING SIGNAL RUNNERS</span>
        </div>
      </div>

      {/* 7 Pipeline Cards with Moving Runner Beams */}
      <div className="pipeline-flow-grid">
        {archStages.map((st, idx) => {
          const isActive = selectedNode === idx
          return (
            <div key={st.num} className="flex flex-col">
              <div
                className={`pipeline-card ${isActive ? 'active' : ''}`}
                onClick={() => {
                  setSelectedNode(idx)
                  setIsAutoCycling(false)
                }}
              >
                <div>
                  <span className="num">{st.num}</span>
                  <h4 className="title">{st.name}</h4>
                </div>
                <div>
                  <span className="badge">{st.label}</span>
                </div>
              </div>
              {/* Continuous animated signal runner */}
              <div className="flow-signal-runner" />
            </div>
          )
        })}
      </div>

      {/* Speculative Pre-dispatch Cancellation Branch Box */}
      {isSimulatingCorrection ? (
        <div className="flow-branch-box">
          <div className="branch-card superseded">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold font-mono tracking-wider text-[#f87171]">SUPERSEDED BRANCH (CANCELLED PRE-DISPATCH)</span>
                <span className="text-sm font-mono font-bold text-muted">REV 1</span>
              </div>
              <strong className="text-sm font-bold text-white block mt-0.5">op-01: search_flights(Mumbai)</strong>
              <p className="text-xs text-soft mt-1.5 leading-relaxed">
                Proposed from initial speech chunk: “Book a flight to Mumbai...”. Invalidation fired
                immediately upon hearing “wait, actually make that Delhi!”.
              </p>
              <div className="branch-steps">
                <div className="branch-step text-muted">
                  <span>00:01.120</span>
                  <span>PROPOSED</span>
                </div>
                <div className="branch-step text-[#f87171]">
                  <span>00:02.321</span>
                  <span>SUPERSEDED BY USER REVISION</span>
                </div>
                <div className="branch-step text-[#f87171] font-bold">
                  <span>00:02.322</span>
                  <span>CANCELLED_BEFORE_DISPATCH</span>
                </div>
              </div>
            </div>
            <div className="pt-2 border-t border-line text-xs font-mono text-soft flex items-center justify-between">
              <span>⚡ SAVED: 0 backend calls · 0ms wasted latency</span>
              <span className="text-[#34d399] font-bold">$0.00 COST</span>
            </div>
          </div>

          <div className="branch-card success">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-bold font-mono tracking-wider text-[#34d399]">RESOLVED INTENT (ADMITTED &amp; EXECUTED)</span>
                <span className="text-sm font-mono font-bold text-[#38bdf8]">REV 2</span>
              </div>
              <strong className="text-sm font-bold text-white block mt-0.5">op-02: search_flights(Delhi)</strong>
              <p className="text-xs text-soft mt-1.5 leading-relaxed">
                Corrected intent revision admitted to write-gate mutex. Historical slots (date=&quot;Friday&quot;)
                cleanly preserved without clobbering.
              </p>
              <div className="branch-steps">
                <div className="branch-step text-muted">
                  <span>00:02.450</span>
                  <span>PROPOSED (destination=Delhi)</span>
                </div>
                <div className="branch-step text-[#38bdf8]">
                  <span>00:02.781</span>
                  <span>ADMITTED TO WRITE-GATE MUTEX</span>
                </div>
                <div className="branch-step text-[#34d399] font-bold">
                  <span>00:03.601</span>
                  <span>SUCCEEDED (latency=820ms)</span>
                </div>
              </div>
            </div>
            <div className="pt-2 border-t border-line text-xs font-mono text-[#34d399] flex items-center justify-between">
              <span>✓ PRESERVED: passenger_name=&quot;Alice&quot; · date=&quot;Friday&quot;</span>
              <span className="text-white font-bold">MATCH: 100%</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-3.5 rounded border border-line bg-black/30 flex items-center justify-between text-sm font-mono">
          <div className="flex items-center gap-3">
            <span className="text-[#34d399] font-bold">✓ STANDARD DIRECT EXECUTION PATH:</span>
            <span className="text-soft">
              Non-conflicting read operations execute concurrently; write tools serialize behind async mutex.
            </span>
          </div>
          <span className="text-muted">STATUS: IDLE · READY</span>
        </div>
      )}

      {/* Selected Component Inspector Card */}
      <div className="arch-detail-card">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-xs font-mono font-bold tracking-wider text-[#38bdf8]">COMPONENT INSPECTOR</span>
            <span className="disfluency-pill text-xs">{stage.tag}</span>
          </div>
          <h3 className="text-base font-bold text-white font-mono mb-1.5">
            {stage.num} / {stage.name}
          </h3>
          <p className="text-sm text-soft leading-relaxed">{stage.desc}</p>
        </div>
        <div className="flex flex-col justify-center gap-2.5 bg-black/50 p-3.5 rounded border border-line">
          <div>
            <span className="text-xs font-mono font-bold tracking-wider text-muted block mb-0.5">PROVENANCE FILE</span>
            <code className="text-sm text-white font-mono block">{stage.file}</code>
          </div>
          <div>
            <span className="text-xs font-mono font-bold tracking-wider text-muted block mb-0.5">RUNTIME INVARIANT</span>
            <span className="text-sm text-[#34d399] font-mono font-bold block">
              {stage.metric}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

const methodologyStages = [
  {
    num: '01',
    badge: '100 AUDIO SCENARIOS',
    title: 'DATASET INGESTION',
    sub: 'NTU FDB-v3 Benchmark Corpus',
    desc: 'National Taiwan University FDB-v3 benchmark corpus containing 100 full-duplex human speech recordings across 4 real domains (Travel, Finance, Housing, E-Commerce). Ingests realistic speech disfluencies, acoustic noise, hesitation fillers ("uh", "um"), and spontaneous mid-utterance rollbacks.',
    input: '100 authentic human audio recordings (16kHz / 24kHz PCM)',
    output: 'Multi-turn annotated dialogues & reference ground truth',
    metric: '100 Human Audio Dialogues (Lin et al., arXiv:2604.04847)',
  },
  {
    num: '02',
    badge: 'ZERO WEIGHT TUNING',
    title: 'PROMPT CONDITIONING',
    sub: 'Zero-Shot Framing & Schema Widening',
    desc: 'Rather than brittle weight fine-tuning (which causes catastrophic forgetting across generic function definitions), REACTOR conditions Gemini 2.5 Live via structured prompt framing in src/reactor/voice/prompts.py and widened JSON schemas to prevent premature validation crashes.',
    input: 'Base Gemini 2.5 Live weights + Raw tool function schemas',
    output: 'Correction-aware instruction frame + widened parameter types',
    metric: 'Zero Catastrophic Forgetting · 100% Schema Compliant',
  },
  {
    num: '03',
    badge: '<150ms BARGE-IN',
    title: 'DUPLEX STREAMING',
    sub: 'Bidirectional Audio over WebRTC',
    desc: 'Native speech-to-speech audio streaming over LiveKit WebRTC transport. Full-duplex audio tokens stream in and out simultaneously, enabling sub-150ms barge-in detection and natural turn interruptions without the 800ms–1500ms latency of cascaded ASR → LLM → TTS pipelines.',
    input: 'Continuous 24kHz WebRTC mic stream from user client',
    output: 'Low-latency agent audio + typed tool call proposals',
    metric: 'Sub-150ms Barge-In Latency · 0ms Cascaded Pipeline Overhead',
  },
  {
    num: '04',
    badge: 'STATE MUTEX & LEDGER',
    title: 'RUNTIME CONTROLLER',
    sub: 'Slot Preservation & Cascade Cancel',
    desc: 'REACTOR Turn Bridge & Admission Gate execution engine. Maintains monotonic revision tracking (Rev 1 → Rev 2), strictly preserves unaffected slots (Alice, Friday, Economy), and pre-dispatch cancels stale superseded operations before network calls occur.',
    input: 'Streaming tool proposals + mid-turn parameter corrections',
    output: 'Pre-dispatch cancellation cascade + slot-preserved state ledger',
    metric: '0 Clobbered Slots · 0 Wasted API Latency · 0 Runaway Costs',
  },
  {
    num: '05',
    badge: '92% STRICT / 94% FAIR',
    title: 'TWO-TIER EVALUATION',
    sub: 'Parakeet ASR & Dual Verification',
    desc: 'Tier 1 streams all 100 audio files over WebRTC via batch_infer.py and logs raw JSONL telemetry. Tier 2 runs NVIDIA Parakeet TDT (0.6B) ASR on GPU and validates execution using both multiset Strict Exact Match (92/100) and Fair Semantic Argument Judge (94/100).',
    input: 'Live captured agent audio + execution telemetry logs',
    output: '92/100 Strict Exact Match · 94/100 Semantic Argument Pass',
    metric: '92.0% Strict Pass (98.0% Tool Selection) · 365 Pytests (100%)',
  },
]

function TrainingAndEvaluation() {
  const [activeStage, setActiveStage] = useState(0)
  const [isAutoCycling, setIsAutoCycling] = useState(true)

  useEffect(() => {
    if (!isAutoCycling) return
    const timer = window.setInterval(() => {
      setActiveStage((prev) => (prev + 1) % methodologyStages.length)
    }, 3200)
    return () => window.clearInterval(timer)
  }, [isAutoCycling])

  const stage = methodologyStages[activeStage]

  return (
    <div className="training-layout">
      {/* Animated Methodology Flowchart */}
      <div className="methodology-flowchart-wrap">
        <div className="methodology-toolbar">
          <div className="flex items-center gap-3">
            <span className="text-sm text-[#38bdf8] font-bold font-mono tracking-wider">
              END-TO-END METHODOLOGY &amp; TRAINING PIPELINE
            </span>
            <span className="text-muted font-mono text-xs">
              5-STAGE ZERO-SHOT REALTIME SYSTEM
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="seq-btn"
              onClick={() => {
                setActiveStage((prev) => (prev - 1 + methodologyStages.length) % methodologyStages.length)
                setIsAutoCycling(false)
              }}
              title="Previous Stage"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              className="seq-btn"
              onClick={() => setIsAutoCycling(!isAutoCycling)}
            >
              {isAutoCycling ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
              <span>{isAutoCycling ? 'PAUSE CYCLE' : 'AUTO CYCLE'}</span>
            </button>
            <button
              className="seq-btn"
              onClick={() => {
                setActiveStage((prev) => (prev + 1) % methodologyStages.length)
                setIsAutoCycling(false)
              }}
              title="Next Stage"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <div className="methodology-flow-container">
          <div className="methodology-grid">
            {methodologyStages.map((s, idx) => {
              const isActive = activeStage === idx
              const isPast = activeStage > idx
              return (
                <div key={s.num} className="methodology-step-wrap">
                  <button
                    className={`methodology-card ${isActive ? 'active' : ''}`}
                    onClick={() => {
                      setActiveStage(idx)
                      setIsAutoCycling(false)
                    }}
                  >
                    <div className="methodology-step-top">
                      <span className="methodology-step-num">{s.num}</span>
                      <span className="methodology-badge">{s.badge}</span>
                    </div>
                    <div>
                      <div className="methodology-step-title">{s.title}</div>
                      <div className="methodology-step-sub">{s.sub}</div>
                    </div>
                  </button>
                  <div className={`methodology-connector ${isActive || isPast ? 'conn-active' : ''}`} />
                </div>
              )
            })}
          </div>

          {/* Active Stage Inspector */}
          <div className="methodology-inspector">
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-xs font-mono font-bold tracking-wider text-[#38bdf8]">STAGE {stage.num} INSPECTOR</span>
                <span className="methodology-badge">{stage.badge}</span>
              </div>
              <h3 className="text-base font-bold text-white font-mono mb-1.5">
                {stage.num} / {stage.title} · {stage.sub}
              </h3>
              <p className="methodology-desc">{stage.desc}</p>
            </div>
            <div className="flex flex-col justify-center gap-2.5 bg-black/60 p-3.5 rounded border border-line">
              <div>
                <span className="text-xs font-mono font-bold tracking-wider text-muted block mb-0.5">INPUT ARTIFACT</span>
                <span className="text-sm text-white font-mono block truncate" title={stage.input}>
                  {stage.input}
                </span>
              </div>
              <div>
                <span className="text-xs font-mono font-bold tracking-wider text-muted block mb-0.5">OUTPUT / GUARANTEE</span>
                <span className="text-sm text-[#38bdf8] font-mono block truncate" title={stage.output}>
                  {stage.output}
                </span>
              </div>
              <div>
                <span className="text-xs font-mono font-bold tracking-wider text-muted block mb-0.5">RUNTIME METRIC</span>
                <span className="text-sm text-[#34d399] font-mono font-bold block truncate" title={stage.metric}>
                  {stage.metric}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 3 Deep Dive Methodology Cards */}
      <div className="deepdive-grid">
        <div className="deepdive-card">
          <h3>
            <Sparkles className="w-4 h-4 text-[#38bdf8]" />
            Zero-Shot Prompt Framing &amp; Schema Widening
          </h3>
          <p>
            Rather than fine-tuning weights (which causes catastrophic forgetting on diverse tools),
            REACTOR conditions Gemini Live via structured instructions in <code>src/reactor/voice/prompts.py</code>.
          </p>
          <p>
            Directs the model to listen through hesitation fillers (<em>“uh”</em>, <em>“um”</em>),
            recognize verbal rollbacks (<em>“actually”</em>, <em>“wait”</em>), and emit clean tool calls
            with widened parameter types to prevent schema validation crashes.
          </p>
        </div>

        <div className="deepdive-card">
          <h3>
            <Database className="w-4 h-4 text-[#38bdf8]" />
            NTU Full-Duplex-Bench v3 Dataset
          </h3>
          <p>
            Evaluation uses authentic <strong>FDB-v3 benchmark</strong> recordings (National Taiwan University,
            Lin et al., 2026, arXiv:2604.04847, CC BY-NC 4.0).
          </p>
          <p>
            Contains <strong>100 real audio dialogues</strong> from 12 human speakers across 4 domains
            (Travel, Finance, Housing, E-Commerce), featuring authentic hesitation fillers, acoustic noise,
            and intentional self-corrections.
          </p>
        </div>

        <div className="deepdive-card">
          <h3>
            <ShieldCheck className="w-4 h-4 text-[#38bdf8]" />
            Two-Tier Evaluation Pipeline
          </h3>
          <p>
            <strong>Tier 1 (Mac Capture):</strong> <code>batch_infer.py</code> streams 100 audio files
            over WebRTC into LiveKit, capturing raw agent output audio and JSONL telemetry.
          </p>
          <p>
            <strong>Tier 2 (GPU &amp; Dual Scoring):</strong> Kaggle T4 runs NVIDIA Parakeet TDT (0.6B) ASR.
            Evaluation calculates both <em>Strict Exact Match</em> (multiset tool comparison: 92/100) and
            <em>Semantic Argument Judge</em> (94/100).
          </p>
        </div>
      </div>

      {/* Verifiable CLI Reproduction Command */}
      <div className="p-3.5 rounded border border-line bg-black/40 flex items-center justify-between text-sm font-mono">
        <div>
          <span className="text-muted block text-xs font-bold tracking-wider mb-0.5">VERIFIABLE REPRODUCTION COMMAND</span>
          <span className="text-[#38bdf8] font-bold text-sm">bash scripts/reproduce.sh --check</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-muted text-xs font-mono font-bold">LOCAL PYTEST SUITE:</span>
          <span className="text-[#34d399] font-bold text-sm">✓ 365 TESTS PASSING (0 FAILS) IN 8.35s</span>
        </div>
      </div>
    </div>
  )
}

function FourInvariants() {
  return (
    <div className="invariants-grid">
      <div className="deepdive-card">
        <h3>1. Zero Slot Clobbering Guarantee</h3>
        <p>
          <code>reactor.state.SessionState</code> stores versioned slots with provenance tracking.
          When a user modifies a single slot (e.g. destination), unaffected historical slots (dates,
          passenger names, travel classes) remain strictly preserved in the state ledger.
        </p>
        <div className="deepdive-code">
          slot.revision = current_revision <span className="text-muted">// Untouched slots keep rev 1</span>
        </div>
      </div>

      <div className="deepdive-card">
        <h3>2. Write-Gate Mutex & Action Identity</h3>
        <p>
          Read-only tools (searches) execute concurrently in parallel. State-altering write tools
          (bookings, cart additions, transfers) are serialized behind an asynchronous mutex
          with deterministic action hashing to eliminate race conditions.
        </p>
        <div className="deepdive-code">
          async with self._write_lock: <span className="text-muted">// 1 writer at a time per session</span>
        </div>
      </div>

      <div className="deepdive-card">
        <h3>3. Pre-Dispatch Cancellation Cascade</h3>
        <p>
          When a barge-in interruption or self-correction occurs, pending proposals for older revisions
          are invalidated immediately before hitting the network or mock backend.
        </p>
        <div className="deepdive-code">
          STATUS: CANCELLED_BEFORE_DISPATCH <span className="text-muted">// 0ms wasted overhead</span>
        </div>
      </div>

      <div className="deepdive-card">
        <h3>4. Truthful History Invariant</h3>
        <p>
          If a tool was already dispatched before the user interrupted, REACTOR observes and
          truthfully logs the outcome. It never claims magical external rollback for remote mutations.
        </p>
        <div className="deepdive-code">
          write.completed = True <span className="text-muted">// Bounded realistic engineering</span>
        </div>
      </div>
    </div>
  )
}

function ArchitectureSection() {
  const [subTab, setSubTab] = useState<'sequence' | 'flow' | 'training' | 'invariants'>('sequence')

  return (
    <main className="content">
      <div className="arch-container">
        <PageHeading
          eyebrow="05 / ARCHITECTURE & METHODOLOGY"
          subtitle="Deep dive into full-duplex runtime mechanics, animated sequence lifelines, dynamic flow diagrams, training, and invariants."
        />

        <nav className="arch-nav">
          <button
            className={subTab === 'sequence' ? 'active' : ''}
            onClick={() => setSubTab('sequence')}
          >
            01. SEQUENCE GRAPH (ANIMATED)
          </button>
          <button
            className={subTab === 'flow' ? 'active' : ''}
            onClick={() => setSubTab('flow')}
          >
            02. DYNAMIC FLOW DIAGRAM
          </button>
          <button
            className={subTab === 'training' ? 'active' : ''}
            onClick={() => setSubTab('training')}
          >
            03. HOW TRAINING & EVALUATION HAPPENS
          </button>
          <button
            className={subTab === 'invariants' ? 'active' : ''}
            onClick={() => setSubTab('invariants')}
          >
            04. FOUR IMMUTABLE INVARIANTS
          </button>
        </nav>

        <div className="diagram-canvas">
          {subTab === 'sequence' && <AnimatedSequenceGraph />}
          {subTab === 'flow' && <AnimatedDynamicFlowDiagram />}
          {subTab === 'training' && <TrainingAndEvaluation />}
          {subTab === 'invariants' && <FourInvariants />}
        </div>
      </div>
    </main>
  )
}

export default function Page() {
  const [route, setRoute] = useState<Route>('engine')

  useEffect(() => {
    const path = window.location.pathname.slice(1) as Route
    if (navItems.some((n) => n.id === path)) {
      setRoute(path)
    }
    const onPop = () => {
      const p = window.location.pathname.slice(1) as Route
      if (navItems.some((n) => n.id === p)) setRoute(p)
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  return (
    <div className="reactor-app">
      <Header route={route} setRoute={setRoute} />
      {route === 'engine' && <Engine />}
      {route === 'kitchen' && <Kitchen />}
      {route === 'benchmarks' && <Benchmarks />}
      {route === 'metrics' && <Metrics />}
      {route === 'architecture' && <ArchitectureSection />}
    </div>
  )
}
