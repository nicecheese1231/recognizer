// frontend/src/main.tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'

import App from './App'
import Analysis from './pages/Analysis'
import AnalysisList from './pages/AnalysisList'   // ✅ 다시 추가
import './index.css'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        {/* 메인 캘린더 */}
        <Route path="/" element={<App />} />

        {/* 평균/실행결과 페이지 */}
        <Route path="/analysis" element={<Analysis />} />

        {/* ✅ 실행별 상세 페이지 */}
        <Route path="/analysis/:runId" element={<AnalysisList />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
)
