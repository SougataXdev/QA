/**
 * Zustand store — single source of truth for all app state.
 */

import { create } from 'zustand'
import type {
  QAFilterOption,
  JobResponse,
  JobStatus,
} from '@/lib/types'

interface QAStore {
  // ─── Upload state ─────────────────────────
  pdfFile: File | null
  pdfUrl: string | null
  targetUrl: string
  pageCount: number
  pageRangeStart: number
  pageRangeEnd: number

  // ─── Crop state ───────────────────────────
  cropTop: number
  cropBottom: number
  cropLeft: number
  cropRight: number
  isCropActive: boolean

  // ─── Job state ────────────────────────────
  jobId: string | null
  jobStatus: JobStatus | null
  progress: number
  progressMessage: string

  // ─── Results state ────────────────────────
  results: JobResponse | null
  activeFilter: QAFilterOption

  // ─── Actions ──────────────────────────────
  setPdf: (file: File) => void
  setTargetUrl: (url: string) => void
  setPageCount: (count: number) => void
  setPageRange: (start: number, end: number) => void
  setCrop: (top: number, bottom: number, left: number, right: number) => void
  toggleCrop: () => void
  setJobId: (id: string) => void
  setJobResponse: (response: JobResponse) => void
  setFilter: (filter: QAFilterOption) => void
  reset: () => void
}

const initialState = {
  pdfFile: null,
  pdfUrl: null,
  targetUrl: '',
  pageCount: 0,
  pageRangeStart: 1,
  pageRangeEnd: -1,
  cropTop: 0.0,
  cropBottom: 1.0,
  cropLeft: 0.0,
  cropRight: 1.0,
  isCropActive: false,
  jobId: null,
  jobStatus: null,
  progress: 0,
  progressMessage: '',
  results: null,
  activeFilter: 'ALL' as QAFilterOption,
}

export const useQAStore = create<QAStore>((set, get) => ({
  ...initialState,

  setPdf: (file: File) => {
    const prev = get().pdfUrl
    if (prev) URL.revokeObjectURL(prev)

    const url = URL.createObjectURL(file)
    set({
      pdfFile: file,
      pdfUrl: url,
      pageCount: 0,
      pageRangeStart: 1,
      pageRangeEnd: -1,
    })
  },

  setTargetUrl: (url: string) => set({ targetUrl: url }),

  setPageCount: (count: number) =>
    set({ pageCount: count, pageRangeEnd: count }),

  setPageRange: (start: number, end: number) =>
    set({ pageRangeStart: start, pageRangeEnd: end }),

  setCrop: (top: number, bottom: number, left: number, right: number) =>
    set({ cropTop: top, cropBottom: bottom, cropLeft: left, cropRight: right }),

  toggleCrop: () => set((s) => ({ isCropActive: !s.isCropActive })),

  setJobId: (id: string) =>
    set({
      jobId: id,
      jobStatus: 'QUEUED',
      progress: 0,
      progressMessage: 'Job queued...',
      results: null,
    }),

  setJobResponse: (response: JobResponse) =>
    set({
      jobStatus: response.status,
      progress: response.progress,
      progressMessage: response.message || '',
      results:
        response.status === 'COMPLETE' || response.status === 'FAILED'
          ? response
          : null,
    }),

  setFilter: (filter: QAFilterOption) => set({ activeFilter: filter }),

  reset: () => {
    const prev = get().pdfUrl
    if (prev) URL.revokeObjectURL(prev)
    set(initialState)
  },
}))
