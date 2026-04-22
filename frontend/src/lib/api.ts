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
  patient_name: string | null
  age_years: number | null
  sex: string | null
  report_date: string | null
  source: string | null
  biomarkers: Array<{
    name: string | null
    original_name: string | null
    value: number | string | null
    unit: string | null
    reference_range_text: string | null
    status: 'optimal' | 'normal' | 'out_of_range' | 'unknown' | null
    notes: string | null
  }>
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
  patient_name: FieldValue<string>
  age_years: FieldValue<number>
  sex: FieldValue<string>
  report_date: FieldValue<string>
  source: FieldValue<string>
  biomarkers: Array<{
    name: FieldValue<string>
    original_name: FieldValue<string>
    value: FieldValue<number | string>
    unit: FieldValue<string>
    reference_range_text: FieldValue<string>
    status: FieldValue<'optimal' | 'normal' | 'out_of_range' | 'unknown'>
    notes: FieldValue<string>
  }>

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
  llmUsed?: boolean
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

