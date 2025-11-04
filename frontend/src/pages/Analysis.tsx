// frontend/src/pages/Analysis.tsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

type LatestRow = { ts: string; score: string; ear: string; gaze_h: string; gaze_v: string }
type LatestResp =
  | { status: 'ok'; data: LatestRow | null; message?: string }
  | { status: 'error'; message: string }

type RunMeta = {
  id: string
  title?: string
  start?: string
  isOnline?: boolean
  created_at?: string
}

const API = 'http://127.0.0.1:8000'

const UI = {
  maxWidth: '100%',
  gap: 20,
  cardPad: 18,
  gauge: { R: 95, stroke: 18, label: 22, value: 40, size: 220 },
}

export default function Analysis() {
  // 🔹 실행 목록
  const [runs, setRuns] = useState<RunMeta[]>([])
  const [listError, setListError] = useState<string | null>(null)

  // 🔹 라이브에서 가져온 최근 점수들 (최대 10개)
  const [history, setHistory] = useState<number[]>([])
  const lastTsRef = useRef<string | null>(null)

  // 숫자 파서
  const n = (v: any, d = 0) => {
    if (v === null || v === undefined) return d
    const s = String(v).trim().toLowerCase()
    if (s === '' || s === 'null' || s === 'nan') return d
    const p = parseFloat(String(v))
    return Number.isFinite(p) ? p : d
  }

  // 🔹 평균 점수 (최근 10개 샘플 기준)
  const avgScore = useMemo(() => {
    if (!history.length) return 0
    const sum = history.reduce((a, b) => a + b, 0)
    return sum / history.length
  }, [history])

  // 🔹 게이지용 값
  const GAUGE_R = UI.gauge.R
  const GAUGE_C = 2 * Math.PI * GAUGE_R
  const strokeDash = `${(avgScore / 100) * GAUGE_C} ${GAUGE_C}`

  // 🔹 실행 목록 불러오기 (/logs)
  useEffect(() => {
    async function loadRuns() {
      try {
        setListError(null)
        const res = await fetch(`${API}/logs`)
        if (!res.ok) throw new Error('실행 목록을 불러오지 못했어요.')
        const json = await res.json()
        const list: RunMeta[] = Array.isArray(json.data) ? json.data : []
        setRuns(list)
      } catch (e: any) {
        setListError(e?.message ?? '목록 로드 오류')
      }
    }
    loadRuns()
  }, [])

  // 🔹 라이브 점수 폴링 (/logs/latest → 최근 10개 평균)
  useEffect(() => {
    async function tick() {
      try {
        const res = await fetch(`${API}/logs/latest`)
        if (!res.ok) return
        const json = (await res.json()) as LatestResp
        if (json.status !== 'ok' || !json.data) return

        const d = json.data
        // 같은 ts면 중복으로 안 넣고, 그래도 그래프는 유지
        if (lastTsRef.current !== d.ts) {
          const s = n(d.score, 0)
          setHistory(prev => {
            const next = [...prev, s]
            if (next.length > 10) next.shift() // 🔟개까지만 유지
            return next
          })
          lastTsRef.current = d.ts
        }
      } catch {
        // 에러면 그냥 조용히 무시, 다음 tick에서 다시 시도
      }
    }

    tick()
    const id = window.setInterval(tick, 1200) // 1.2초마다 폴링
    return () => window.clearInterval(id)
  }, [])

  return (
    <div
      style={{
        maxWidth: UI.maxWidth,
        margin: '32px auto',
        padding: '0 16px',
        fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto',
      }}
    >
      {/* 상단 헤더 */}
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: UI.gap,
        }}
      >
        <h1 style={{ fontSize: 26, fontWeight: 800 }}>분석 결과 & 실행 목록</h1>
        <Link
          to="/"
          style={{
            textDecoration: 'none',
            background: '#111827',
            color: 'white',
            padding: '8px 14px',
            borderRadius: 10,
          }}
        >
          ← 캘린더로 돌아가기
        </Link>
      </header>

      <section
        style={{
          display: 'grid',
          gridTemplateColumns: '1.6fr 1fr',
          gap: UI.gap,
        }}
      >
        {/* 🔸 왼쪽: 평균 게이지 (최근 10개 샘플 기준) */}
        <div
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: 16,
            padding: UI.cardPad,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <svg
            width={UI.gauge.size}
            height={UI.gauge.size}
            viewBox={`0 0 ${UI.gauge.size} ${UI.gauge.size}`}
          >
            {/* 배경 원 */}
            <circle
              cx={UI.gauge.size / 2}
              cy={UI.gauge.size / 2}
              r={GAUGE_R}
              stroke="#e5e7eb"
              strokeWidth={UI.gauge.stroke}
              fill="none"
            />
            {/* 값 원 (위에서 시작하도록 회전) */}
            <g
              transform={`rotate(-90, ${UI.gauge.size / 2}, ${
                UI.gauge.size / 2
              })`}
            >
              <circle
                cx={UI.gauge.size / 2}
                cy={UI.gauge.size / 2}
                r={GAUGE_R}
                stroke="#60a5fa"
                strokeWidth={UI.gauge.stroke}
                strokeLinecap="round"
                fill="none"
                strokeDasharray={strokeDash}
              />
            </g>
            {/* 라벨 */}
            <text
              x={UI.gauge.size / 2}
              y={UI.gauge.size / 2 - 6}
              textAnchor="middle"
              fontSize={UI.gauge.label}
              fontWeight={700}
              fill="#111827"
            >
              최근 10개 평균
            </text>
            <text
              x={UI.gauge.size / 2}
              y={UI.gauge.size / 2 + 24}
              textAnchor="middle"
              fontSize={UI.gauge.value}
              fontWeight={800}
              fill="#111827"
            >
              {avgScore.toFixed(1)}
            </text>
          </svg>

          <div style={{ fontSize: 14, color: '#6b7280' }}>
            <div>웹캠 분석에서 들어오는</div>
            <div>최근 10개 집중도 점수의 평균입니다.</div>
            <div style={{ marginTop: 8, fontSize: 12 }}>
              * 분석 버튼을 눌러 attention_mvp를 실행한 뒤 <br />
              &nbsp;&nbsp;조작창에서 START를 누르면 값이 쌓여요.
            </div>
          </div>
        </div>

        {/* 🔸 오른쪽: 실행 목록 (버튼: 상세) */}
        <aside
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: 16,
            padding: UI.cardPad,
            alignSelf: 'start',
          }}
        >
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 10,
            }}
          >
            <div style={{ fontWeight: 800 }}>실행별 결과</div>
          </div>

          {listError && (
            <div style={{ color: 'red', marginBottom: 10 }}>{listError}</div>
          )}

          {runs.length === 0 ? (
            <div style={{ color: '#6b7280' }}>아직 실행된 기록이 없습니다.</div>
          ) : (
            <ul
              style={{
                listStyle: 'none',
                padding: 0,
                margin: 0,
                display: 'grid',
                gap: 10,
              }}
            >
              {runs.map(r => (
                <li
                  key={r.id}
                  style={{
                    border: '1px solid #eef',
                    borderRadius: 10,
                    padding: 10,
                    display: 'grid',
                    gap: 6,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <div style={{ fontWeight: 700 }}>
                      {r.title || r.id}
                      {r.isOnline && (
                        <span style={{ color: '#3b82f6', fontSize: 12 }}>
                          {' '}
                          (온라인)
                        </span>
                      )}
                    </div>
                    <Link
                      to={`/analysis/${encodeURIComponent(r.id)}`}
                      style={{
                        border: '1px solid #eee',
                        background: '#fff',
                        borderRadius: 8,
                        padding: '4px 8px',
                        textDecoration: 'none',
                        color: '#0369a1',
                        fontSize: 13,
                      }}
                    >
                      상세
                    </Link>
                  </div>
                  <div style={{ fontSize: 12, color: '#6b7280' }}>
                    시작: {r.start ?? '-'} · 생성: {r.created_at ?? '-'}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </section>
    </div>
  )
}
