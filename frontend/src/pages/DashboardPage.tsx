import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  downloadFileUrl,
  downloadResultUrl,
  extract,
  listFiles,
  uploadPdf,
  type ExtractionResult,
  type UploadedFile,
} from '../lib/api'

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes)) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let b = bytes
  let u = 0
  while (b >= 1024 && u < units.length - 1) {
    b /= 1024
    u++
  }
  return `${b.toFixed(u === 0 ? 0 : 1)} ${units[u]}`
}

function FieldRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="grid grid-cols-12 gap-3 py-2">
      <div className="col-span-5 text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="col-span-7 text-sm text-slate-900">{value ?? '—'}</div>
    </div>
  )
}

export function DashboardPage() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<UploadedFile | null>(null)
  const [lastResult, setLastResult] = useState<ExtractionResult | null>(null)

  const filesQ = useQuery({ queryKey: ['files'], queryFn: listFiles })

  const uploadM = useMutation({
    mutationFn: uploadPdf,
    onSuccess: async (res) => {
      await qc.invalidateQueries({ queryKey: ['files'] })
      setSelected(res.file)
      setLastResult(null)
    },
  })

  const extractM = useMutation({
    mutationFn: extract,
    onSuccess: (res) => {
      setLastResult(res)
    },
  })

  const files = filesQ.data?.files ?? []
  const selectedFromList = useMemo(() => {
    if (!selected) return null
    return files.find((f) => f.id === selected.id) ?? selected
  }, [files, selected])

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
          <div>
            <div className="text-sm font-semibold text-slate-900">Authorization Document Reader</div>
            <div className="text-xs text-slate-500">
              Upload PDFs → extract → download results (JSON)
            </div>
          </div>
          <div className="text-xs text-slate-500">Backend: <code className="rounded bg-slate-100 px-1.5 py-0.5">/api</code></div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl grid-cols-12 gap-6 px-6 py-6">
        <section className="card col-span-12 p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">Core files</div>
              <div className="text-xs text-slate-500">Uploaded authorization PDFs</div>
            </div>
            <label className="btn-secondary cursor-pointer">
              <input
                className="hidden"
                type="file"
                accept="application/pdf"
                onChange={(e) => {
                  const f = e.currentTarget.files?.[0]
                  if (f) uploadM.mutate(f)
                  e.currentTarget.value = ''
                }}
              />
              Upload PDF
            </label>
          </div>

          <div className="mt-4 overflow-hidden rounded-xl border border-slate-200">
            <div className="grid grid-cols-12 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600">
              <div className="col-span-5">File</div>
              <div className="col-span-3">Uploaded</div>
              <div className="col-span-2">Size</div>
              <div className="col-span-2 text-right">Actions</div>
            </div>
            <div className="divide-y divide-slate-200">
              {files.length === 0 && (
                <div className="px-3 py-6 text-center text-sm text-slate-500">
                  No files yet. Upload a PDF to start.
                </div>
              )}
              {files.map((f) => {
                const active = selectedFromList?.id === f.id
                return (
                  <button
                    key={f.id}
                    className={[
                      'grid w-full grid-cols-12 items-center px-3 py-3 text-left text-sm',
                      active ? 'bg-slate-100' : 'bg-white hover:bg-slate-50',
                    ].join(' ')}
                    onClick={() => {
                      setSelected(f)
                      setLastResult(null)
                    }}
                  >
                    <div className="col-span-5 truncate font-medium text-slate-900">{f.originalName}</div>
                    <div className="col-span-3 truncate text-xs text-slate-600">{new Date(f.uploadedAt).toLocaleString()}</div>
                    <div className="col-span-2 text-xs text-slate-600">{formatBytes(f.sizeBytes)}</div>
                    <div className="col-span-2 flex justify-end gap-2">
                      <a
                        className="btn-secondary text-xs"
                        href={downloadFileUrl(f.id)}
                        onClick={(e) => e.stopPropagation()}
                      >
                        PDF
                      </a>
                      <a
                        className="btn-secondary text-xs"
                        href={downloadResultUrl(f.id)}
                        onClick={(e) => e.stopPropagation()}
                      >
                        JSON
                      </a>
                    </div>
                  </button>
                )
              })}
            </div>
          </div>
        </section>

        <section className="card col-span-12 lg:col-span-6 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">Extracted data</div>
              <div className="text-xs text-slate-500">
                Structured fields (missing fields show as warnings)
              </div>
            </div>
            <button
              className="btn-primary"
              disabled={!selectedFromList || extractM.isPending}
              onClick={() => {
                if (!selectedFromList) return
                extractM.mutate(selectedFromList.id)
              }}
            >
              {extractM.isPending ? 'Extracting…' : 'Run extraction'}
            </button>
          </div>

          {!selectedFromList && (
            <div className="mt-6 text-sm text-slate-500">Select a file to extract.</div>
          )}

          {selectedFromList && !lastResult && (
            <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
              Ready to extract fields from <span className="font-medium text-slate-900">{selectedFromList.originalName}</span>.
            </div>
          )}

          {lastResult && (
            <div className="mt-4">
              <div className="rounded-xl border border-slate-200 p-4">
                <FieldRow label="Student name" value={lastResult.extracted.student_name} />
                <FieldRow label="Student ID" value={lastResult.extracted.student_id} />
                <FieldRow label="District" value={lastResult.extracted.district} />
                <FieldRow label="Service type" value={lastResult.extracted.service_type} />
                <FieldRow label="Authorized minutes" value={lastResult.extracted.authorized_minutes} />
                <FieldRow label="Start date" value={lastResult.extracted.start_date} />
                <FieldRow label="End date" value={lastResult.extracted.end_date} />
                <FieldRow label="Authorization #" value={lastResult.extracted.authorization_number} />
                <FieldRow label="Case manager" value={lastResult.extracted.case_manager_name} />
                <FieldRow
                  label="Subject areas"
                  value={lastResult.extracted.subject_areas?.join(', ') ?? null}
                />
                <div className="border-t border-slate-200 pt-3">
                  <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Notes
                  </div>
                  <div className="mt-2 whitespace-pre-wrap text-sm text-slate-900">
                    {lastResult.extracted.notes ?? '—'}
                  </div>
                </div>
              </div>

              {lastResult.extracted.warnings.length > 0 && (
                <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <div className="text-sm font-semibold text-amber-900">Warnings</div>
                  <ul className="mt-2 list-disc pl-5 text-sm text-amber-900">
                    {lastResult.extracted.warnings.map((w) => (
                      <li key={w}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {extractM.isError && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
              {(extractM.error as Error).message}
            </div>
          )}
        </section>

        <section className="card col-span-12 lg:col-span-6 p-5">
          <div className="text-sm font-semibold text-slate-900">Result files</div>
          <div className="mt-1 text-xs text-slate-500">Saved extraction outputs per PDF</div>

          <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">What gets generated</div>
            <div className="mt-2 text-sm text-slate-700">
              Each extraction writes a JSON file on the backend: <code className="rounded bg-slate-100 px-1.5 py-0.5">backend/data/results/&lt;fileId&gt;.json</code>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <a
                className="btn-secondary"
                href={selectedFromList ? downloadResultUrl(selectedFromList.id) : undefined}
                aria-disabled={!selectedFromList}
                onClick={(e) => {
                  if (!selectedFromList) e.preventDefault()
                }}
              >
                Download current JSON
              </a>
              <button
                className="btn-secondary"
                onClick={() => {
                  filesQ.refetch().catch(() => undefined)
                }}
              >
                Refresh file list
              </button>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
            <div className="font-medium text-slate-900">Scalability-minded separation</div>
            <ul className="mt-2 list-disc pl-5">
              <li>Backend: extraction pipeline + storage + future Google Sheets writer</li>
              <li>Frontend: purely a client for APIs, easy to swap UI framework later</li>
              <li>API contract lives in <code className="rounded bg-white px-1.5 py-0.5">frontend/src/lib/api.ts</code></li>
            </ul>
          </div>
        </section>
      </main>
    </div>
  )
}

