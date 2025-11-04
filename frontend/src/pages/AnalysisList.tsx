import { useParams, Link } from 'react-router-dom'

export default function AnalysisList() {
  const { runId } = useParams<{ runId: string }>()

  return (
    <div
      style={{
        maxWidth: 1000,
        margin: '40px auto',
        padding: '0 16px',
        fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto',
      }}
    >
      <header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 24,
        }}
      >
        <h1 style={{ fontSize: 24, fontWeight: 800 }}>실행 상세 보기</h1>
        <Link
          to="/analysis"
          style={{
            textDecoration: 'none',
            background: '#111827',
            color: 'white',
            padding: '8px 14px',
            borderRadius: 10,
          }}
        >
          ← 분석 결과로 돌아가기
        </Link>
      </header>

      <div
        style={{
          border: '1px solid #e5e7eb',
          borderRadius: 16,
          padding: 20,
          textAlign: 'center',
          background: '#fafafa',
        }}
      >
        <div style={{ fontSize: 16, marginBottom: 8 }}>
          선택된 실행 ID:
        </div>
        <div style={{ fontWeight: 700, fontSize: 20, color: '#2563eb' }}>
          {runId || '(선택된 실행이 없습니다)'}
        </div>
        <div style={{ marginTop: 20, color: '#6b7280' }}>
          📊 추후 이 페이지에서 시간대별 집중도 분석 그래프가 표시될 예정입니다.
        </div>
      </div>
    </div>
  )
}
