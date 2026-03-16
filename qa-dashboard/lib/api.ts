/**
 * API client — all Python microservice communication.
 * Components never call the Python API directly.
 */

import axios from 'axios'
import type { JobCreatedResponse, JobResponse, ProcessRequest } from './types'

const PYTHON_BASE =
  process.env.NEXT_PUBLIC_PYTHON_API_URL || 'http://localhost:8000'

/**
 * Submit a PDF + URL for QA processing.
 * Returns job_id and poll_url.
 */
export async function submitJob(
  pdfFile: File,
  request: ProcessRequest
): Promise<JobCreatedResponse> {
  const formData = new FormData()
  formData.append('file', pdfFile)

  // Build query params (FastAPI uses Query() params, not body fields)
  const params = new URLSearchParams({
    url: request.url,
    crop_top: String(request.crop_top),
    crop_bottom: String(request.crop_bottom),
    crop_left: String(request.crop_left),
    crop_right: String(request.crop_right),
    page_range_start: String(request.page_range_start),
    page_range_end: String(request.page_range_end),
  })

  const response = await axios.post<JobCreatedResponse>(
    `${PYTHON_BASE}/process?${params.toString()}`,
    formData,
    {
      headers: { 'Content-Type': 'multipart/form-data' },
    }
  )
  return response.data
}

/**
 * Poll job status. Returns full response including results when complete.
 */
export async function pollJob(jobId: string): Promise<JobResponse> {
  const response = await axios.get<JobResponse>(
    `${PYTHON_BASE}/jobs/${jobId}`
  )
  return response.data
}

/**
 * Health check.
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await axios.get<{ status: string }>(
    `${PYTHON_BASE}/health`
  )
  return response.data
}
