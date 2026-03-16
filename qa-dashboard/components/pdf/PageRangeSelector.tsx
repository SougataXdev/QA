'use client'

import { motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { useQAStore } from '@/store/useQAStore'

export default function PageRangeSelector() {
  const { pageCount, pageRangeStart, pageRangeEnd, setPageRange } = useQAStore()

  if (pageCount === 0) return null

  const effectiveEnd = pageRangeEnd === -1 ? pageCount : pageRangeEnd

  // Local string state lets the user type freely without mid-entry clamping.
  // We only validate + commit to the store on blur.
  const [startStr, setStartStr] = useState(String(pageRangeStart))
  const [endStr, setEndStr] = useState(String(effectiveEnd))

  // Keep local state in sync when the store values change (e.g. new PDF uploaded)
  useEffect(() => { setStartStr(String(pageRangeStart)) }, [pageRangeStart])
  useEffect(() => { setEndStr(String(effectiveEnd)) }, [effectiveEnd])

  const commitStart = (str: string) => {
    const raw = parseInt(str, 10)
    const clamped = isNaN(raw) ? pageRangeStart : Math.max(1, Math.min(raw, effectiveEnd))
    setStartStr(String(clamped))
    setPageRange(clamped, pageRangeEnd)
  }

  const commitEnd = (str: string) => {
    const raw = parseInt(str, 10)
    const clamped = isNaN(raw) ? effectiveEnd : Math.max(pageRangeStart, Math.min(raw, pageCount))
    setEndStr(String(clamped))
    setPageRange(pageRangeStart, clamped)
  }

  const inputClass = `
    w-full rounded-lg border border-white/[0.08] bg-white/[0.03]
    px-3 py-2 text-sm text-white tabular-nums
    outline-none focus:border-blue-500/50 focus:ring-1 focus:ring-blue-500/20
    transition-all
  `

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="overflow-hidden"
    >
      <div className="flex items-center gap-3 pt-3">
        {/* Start page */}
        <div className="flex-1">
          <label
            htmlFor="page-start"
            className="block text-[10px] font-medium text-white/30 uppercase tracking-widest mb-1"
          >
            Start Page
          </label>
          <input
            id="page-start"
            type="number"
            min={1}
            max={effectiveEnd}
            value={startStr}
            onChange={(e) => setStartStr(e.target.value)}
            onBlur={() => commitStart(startStr)}
            onKeyDown={(e) => e.key === 'Enter' && commitStart(startStr)}
            className={inputClass}
          />
        </div>

        <div className="pt-5 text-white/20 text-xs">—</div>

        {/* End page */}
        <div className="flex-1">
          <label
            htmlFor="page-end"
            className="block text-[10px] font-medium text-white/30 uppercase tracking-widest mb-1"
          >
            End Page
          </label>
          <input
            id="page-end"
            type="number"
            min={pageRangeStart}
            max={pageCount}
            value={endStr}
            onChange={(e) => setEndStr(e.target.value)}
            onBlur={() => commitEnd(endStr)}
            onKeyDown={(e) => e.key === 'Enter' && commitEnd(endStr)}
            className={inputClass}
          />
        </div>

        <div className="pt-5 text-white/20 text-[10px] whitespace-nowrap">
          of {pageCount}
        </div>
      </div>
    </motion.div>
  )
}
