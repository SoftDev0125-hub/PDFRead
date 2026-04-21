export type UploadedFile = {
  id: string
  originalName: string
  storedName: string
  sizeBytes: number
  uploadedAt: string
  contentType?: string | null
}

export type FilesResponse = {
  files: UploadedFile[]
}

export type ExtractedAuthorization = {
  student_name: string | null
  student_id: string | null
  district: string | null
  service_type: string | null
  authorized_minutes: number | null
  start_date: string | null
  end_date: string | null
  authorization_number: string | null
  case_manager_name: string | null
  subject_areas: string[] | null
  notes: string | null
  warnings: string[]
}

export type ExtractionResult = {
  fileId: string
  originalName: string
  extractedAt: string
  extracted: ExtractedAuthorization
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const txt = await res.text().catch(() => '')
    throw new Error(txt || `Request failed: ${res.status}`)
  }
  return (await res.json()) as T
}

export async function listFiles(): Promise<FilesResponse> {
  return api<FilesResponse>('/api/files')
}

export async function uploadPdf(file: File): Promise<{ ok: true; file: UploadedFile }> {
  const form = new FormData()
  form.append('file', file)
  return api('/api/files', { method: 'POST', body: form })
}

export async function extract(fileId: string): Promise<ExtractionResult> {
  return api<ExtractionResult>(`/api/extract/${fileId}`, { method: 'POST' })
}

export function downloadFileUrl(fileId: string): string {
  return `/api/files/${fileId}/download`
}

export function downloadResultUrl(fileId: string): string {
  return `/api/results/${fileId}.json`
}

