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

export type Evidence = {
  page: number | null
  snippet: string | null
}

export type FieldValue<T> = {
  value: T | null
  evidence: Evidence
  confidence: number | null
}

export type ExtractedAuthorizationV2 = {
  student_name: FieldValue<string>
  student_id: FieldValue<string>
  district: FieldValue<string>
  service_type: FieldValue<string>
  authorized_minutes: FieldValue<number>
  start_date: FieldValue<string>
  end_date: FieldValue<string>
  authorization_number: FieldValue<string>
  case_manager_name: FieldValue<string>
  subject_areas: FieldValue<string[]>
  notes: FieldValue<string>

  warnings: string[]
  validations: string[]
}

export type PageRouting = {
  page: number
  route: 'text' | 'ocr'
  chars: number
}

export type ExtractionResult = {
  fileId: string
  originalName: string
  extractedAt: string
  extracted: ExtractedAuthorization
  extractedV2?: ExtractedAuthorizationV2
  pageRouting?: PageRouting[]
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

export async function deleteUploadedFile(fileId: string): Promise<{ ok: true; deleted: { upload: boolean; result: boolean } }> {
  return api(`/api/files/${fileId}`, { method: 'DELETE' })
}

export function downloadFileUrl(fileId: string): string {
  return `/api/files/${fileId}/download`
}

export function downloadResultUrl(fileId: string): string {
  return `/api/results/${fileId}.json`
}

