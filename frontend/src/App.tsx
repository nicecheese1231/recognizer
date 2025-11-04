import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom' // ✅ 추가
import FullCalendar from '@fullcalendar/react'
import dayGridPlugin from '@fullcalendar/daygrid'
import interactionPlugin, { type DateClickArg } from '@fullcalendar/interaction'
import type { EventClickArg } from '@fullcalendar/core'
import dayjs from 'dayjs'

function uid() {
  return Math.random().toString(36).slice(2, 10)
}

type CalendarEvent = {
  id: string
  title: string
  start: string
  end?: string
  allDay?: boolean
  color?: string
  done?: boolean
  isOnline?: boolean
}

function useLocalStorage<T>(key: string, initial: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(key)
      return raw ? (JSON.parse(raw) as T) : initial
    } catch {
      return initial
    }
  })
  function update(v: T) {
    setValue(v)
    localStorage.setItem(key, JSON.stringify(v))
  }
  return [value, update] as const
}

function useIsNarrow(breakpoint = 900) {
  const [isNarrow, setIsNarrow] = useState<boolean>(() => window.innerWidth < breakpoint)
  useEffect(() => {
    const onResize = () => setIsNarrow(window.innerWidth < breakpoint)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [breakpoint])
  return isNarrow
}

export default function App() {
  const [events, setEvents] = useLocalStorage<CalendarEvent[]>('events.v1', [
    { id: uid(), title: '온라인 강의', start: dayjs().hour(10).minute(0).second(0).format(), done: false, isOnline: true },
    { id: uid(), title: '복습', start: dayjs().add(1, 'day').hour(18).minute(0).format(), end: dayjs().add(1, 'day').hour(18).minute(30).format(), color: '#7dd3fc', done: false, isOnline: false },
  ])
  const safeEvents = useMemo(() => events.map(e => ({ done: false, isOnline: false, ...e })), [events])

  const [title, setTitle] = useState('')
  const [date, setDate] = useState(dayjs().format('YYYY-MM-DD'))
  const [startTime, setStartTime] = useState('10:00')
  const [endTime, setEndTime] = useState('')
  const [allDay, setAllDay] = useState(false)
  const [color, setColor] = useState('#86efac')
  const [isOnlineForm, setIsOnlineForm] = useState(false)
  const [selectedDate, setSelectedDate] = useState<string>(dayjs().format('YYYY-MM-DD'))

  const calendarRef = useRef<FullCalendar | null>(null)
  const isNarrow = useIsNarrow(900)

  const fcEvents = useMemo(
    () =>
      safeEvents.map(e => {
        const isDone = !!e.done
        const bg = isDone ? '#e5e7eb' : e.color
        const text = isDone ? '#6b7280' : undefined
        return {
          ...e,
          backgroundColor: bg,
          borderColor: bg,
          textColor: text,
        }
      }),
    [safeEvents]
  )

  const selectedDayEvents = useMemo(
    () =>
      safeEvents
        .filter(e => dayjs(e.start).isSame(selectedDate, 'day'))
        .sort((a, b) => dayjs(a.start).valueOf() - dayjs(b.start).valueOf()),
    [safeEvents, selectedDate]
  )

  function fmtRange(e: CalendarEvent) {
    if (e.allDay) return '종일'
    const s = dayjs(e.start).format('HH:mm')
    if (!e.end) return s
    const t = dayjs(e.end).format('HH:mm')
    return `${s} ~ ${t}`
  }

  function addEvent(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return alert('제목을 입력하세요.')

    const startISO = allDay ? dayjs(date).format('YYYY-MM-DD') : dayjs(`${date}T${startTime}`).format()
    const endISO = allDay ? undefined : endTime ? dayjs(`${date}T${endTime}`).format() : undefined

    const newEvent: CalendarEvent = {
      id: uid(),
      title: title.trim(),
      start: startISO,
      end: endISO,
      allDay,
      color,
      done: false,
      isOnline: isOnlineForm,
    }
    setEvents([newEvent, ...safeEvents])
    setTitle('')
    setAllDay(false)
    setEndTime('')
    setIsOnlineForm(false)
  }

  function clearAllEvents() {
    if (confirm('정말 모든 일정을 삭제할까요?')) setEvents([])
  }

  function onDateClick(info: DateClickArg) {
    const d = dayjs(info.date).format('YYYY-MM-DD')
    setDate(d)
    setSelectedDate(d)
    document.getElementById('title-input')?.focus()
  }

  function onEventClick(info: EventClickArg) {
    const id = info.event.id
    const target = safeEvents.find(e => e.id === id)
    if (!target) return
    const action = window.prompt(`수정하려면 새 제목 입력, 삭제하려면 빈 값으로 두세요.\n현재: ${target.title}`, target.title)
    if (action === null) return
    if (action.trim() === '') {
      if (confirm('정말 삭제할까요?')) setEvents(safeEvents.filter(e => e.id !== id))
      return
    }
    setEvents(safeEvents.map(e => (e.id === id ? { ...e, title: action.trim() } : e)))
  }

  function removeById(id: string) {
    setEvents(safeEvents.filter(e => e.id !== id))
  }

  function toggleDone(id: string) {
    setEvents(safeEvents.map(e => (e.id === id ? { ...e, done: !e.done } : e)))
  }

  async function analyzeEvent(id: string) {
    const ev = safeEvents.find(e => e.id === id)
    if (!ev) return
    try {
      const res = await fetch('http://127.0.0.1:8000/run-attention', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: ev.id,
          title: ev.title,
          start: ev.start,
          isOnline: ev.isOnline ?? false,
        }),
      })
      const data = await res.json()
      if (data.status === 'ok') {
        alert('분석 스크립트 실행을 시작했어요! (웹캠 창을 확인하세요)')
      } else {
        alert('분석 실행 실패: ' + (data.message || '알 수 없는 오류'))
      }
    } catch {
      alert('백엔드 연결 실패: FastAPI 서버가 켜져 있는지 확인하세요.')
    }
  }

  return (
    <div
      style={{
        maxWidth: '100%',
        margin: '32px auto',
        padding: isNarrow ? '0 12px' : '0 16px',
        fontFamily: 'system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif',
      }}
    >
      {/* 🔹 상단 타이틀 + 분석결과보기 버튼 추가 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <h1 style={{ fontSize: isNarrow ? 22 : 26, fontWeight: 700 }}>AI 집중도 캘린더</h1>
        <Link
          to="/analysis"
          style={{
            textDecoration: 'none',
            background: '#111827',
            color: 'white',
            padding: '8px 14px',
            borderRadius: 10,
            border: '1px solid #374151',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            fontSize: 14,
          }}
        >
          🔎 분석결과 보기
        </Link>
      </div>

      {/* 입력 폼 */}
      <form
        onSubmit={addEvent}
        style={{
          display: 'grid',
          gridTemplateColumns: isNarrow ? '1fr' : '1.2fr 1fr 0.8fr 0.8fr 0.8fr 0.6fr auto',
          gap: 8,
          marginBottom: 16,
          alignItems: 'end',
        }}
      >
        <div style={{ display: 'grid' }}>
          <label style={{ fontSize: 12 }}>제목</label>
          <input id="title-input" value={title} onChange={e => setTitle(e.target.value)} placeholder="예: 온라인 강의" />
        </div>
        <div style={{ display: 'grid' }}>
          <label style={{ fontSize: 12 }}>날짜</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} />
        </div>
        <div style={{ display: 'grid' }}>
          <label style={{ fontSize: 12 }}>시작</label>
          <input type="time" value={startTime} onChange={e => setStartTime(e.target.value)} disabled={allDay} />
        </div>
        <div style={{ display: 'grid' }}>
          <label style={{ fontSize: 12 }}>종료(선택)</label>
          <input type="time" value={endTime} onChange={e => setEndTime(e.target.value)} disabled={allDay} />
        </div>

        <div style={{ display: 'grid', gap: 6 }}>
          <label style={{ fontSize: 12 }}>옵션</label>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={allDay} onChange={e => setAllDay(e.target.checked)} />
              종일
            </label>
            <label style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <input type="checkbox" checked={isOnlineForm} onChange={e => setIsOnlineForm(e.target.checked)} />
              온라인 강의
            </label>
          </div>
        </div>

        <div style={{ display: 'grid' }}>
          <label style={{ fontSize: 12 }}>색상</label>
          <input type="color" value={color} onChange={e => setColor(e.target.value)} />
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <button type="submit" style={{ borderRadius: 8, border: '1px solid #ccc', background: '#e5ffe5' }}>
            추가
          </button>
          <button
            type="button"
            onClick={clearAllEvents}
            style={{ borderRadius: 8, border: '1px solid #ccc', background: '#ffe5e5', color: '#c00' }}
          >
            전체 삭제
          </button>
        </div>
      </form>

      {/* 캘린더 + 사이드바 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: isNarrow ? '1fr' : '2fr 1fr',
          gap: isNarrow ? 16 : 24,
        }}
      >
        <div>
          <FullCalendar
            ref={calendarRef as any}
            plugins={[dayGridPlugin, interactionPlugin]}
            initialView="dayGridMonth"
            height="auto"
            expandRows
            dayMaxEvents={isNarrow ? 2 : 3}
            events={fcEvents}
            dateClick={onDateClick}
            eventClick={onEventClick}
            headerToolbar={
              isNarrow
                ? { left: 'prev,next', center: 'title', right: 'today' }
                : { left: 'prev,next today', center: 'title', right: 'dayGridMonth' }
            }
          />
        </div>

        <aside>
          <div
            style={{
              border: '1px solid #e5e7eb',
              borderRadius: 12,
              padding: 14,
              boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
            }}
          >
            <div style={{ fontWeight: 700, marginBottom: 8 }}>
              📌 {dayjs(selectedDate).format('YYYY-MM-DD')} 일정
            </div>
            {selectedDayEvents.length === 0 ? (
              <div style={{ color: '#888' }}>이 날짜에는 일정이 없어요.</div>
            ) : (
              <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'grid', gap: 8 }}>
                {selectedDayEvents.map(e => (
                  <li key={e.id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <input type="checkbox" checked={!!e.done} onChange={() => toggleDone(e.id)} />
                    <span
                      style={{
                        width: 10,
                        height: 10,
                        borderRadius: 999,
                        background: e.done ? '#e5e7eb' : e.color || '#86efac',
                      }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, textDecoration: e.done ? 'line-through' : 'none' }}>{e.title}</div>
                      <div style={{ fontSize: 12, color: '#6b7280' }}>{fmtRange(e)}</div>
                    </div>
                    {e.isOnline && (
                      <button
                        onClick={() => analyzeEvent(e.id)}
                        style={{
                          border: '1px solid #cde',
                          background: '#eef6ff',
                          borderRadius: 8,
                          padding: '4px 8px',
                          cursor: 'pointer',
                        }}
                      >
                        분석
                      </button>
                    )}
                    <button
                      onClick={() => removeById(e.id)}
                      style={{
                        border: '1px solid #eee',
                        background: '#fff',
                        borderRadius: 8,
                        padding: '4px 8px',
                        cursor: 'pointer',
                      }}
                    >
                      삭제
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
