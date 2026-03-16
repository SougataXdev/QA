/**
 * Job poller — polls /jobs/{id} until COMPLETE or FAILED.
 * Never crashes the UI on network errors — logs and retries.
 */

'use client'

import { useEffect } from 'react'
import { pollJob } from '@/lib/api'
import { useQAStore } from '@/store/useQAStore'

export function useJobPoller(jobId: string | null) {
  const setJobResponse = useQAStore((s) => s.setJobResponse)

  useEffect(() => {
    if (!jobId) return

    let active = true

    const poll = async () => {
      try {
        const response = await pollJob(jobId)
        if (!active) return
        setJobResponse(response)

        if (
          response.status === 'COMPLETE' ||
          response.status === 'FAILED'
        ) {
          clearInterval(intervalId)
        }
      } catch (err) {
        // Network error — do NOT crash, retry on next interval
        console.warn('Poll failed, retrying:', err)
      }
    }

    poll() // Immediate first poll
    const intervalId = setInterval(poll, 1500)

    return () => {
      active = false
      clearInterval(intervalId)
    }
  }, [jobId, setJobResponse])
}
