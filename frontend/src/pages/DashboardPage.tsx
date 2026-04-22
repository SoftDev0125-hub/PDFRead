import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteUploadedFile,
  downloadFileUrl,
  downloadResultUrl,
  extract,
  listFiles,
  uploadPdf,
  type ExtractionResult,
  type ExtractedAuthorizationV2,
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
      <div className="col-span-5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="col-span-7 text-sm text-slate-900">{value ?? '—'}</div>
    </div>
  )
}

function EvidenceBlock({ v2, field }: { v2: ExtractedAuthorizationV2; field: keyof ExtractedAuthorizationV2 }) {
  const item = v2[field] as unknown as { evidence?: { page: number | null; snippet: string | null } }
  const ev = item?.evidence
  if (!ev?.snippet) return null
  return (
    <div className="mt-1 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
      <div className="flex items-center justify-between gap-3">
        <div className="font-semibold text-slate-700">
        Evidence{typeof ev.page === 'number' ? ` (page ${ev.page + 1})` : ''}
      </div>
        <div className="text-[11px] text-slate-500">matched snippet</div>
      </div>
      <div className="mt-2 whitespace-pre-wrap rounded-lg bg-white/60 p-2 leading-relaxed text-slate-800">
        {ev.snippet}
      </div>
    </div>
  )
}

function statusPill(status: string | null | undefined): { text: string; className: string } {
  const s = (status ?? 'unknown').toLowerCase()
  if (s === 'optimal') return { text: 'OPTIMAL', className: 'bg-emerald-100 text-emerald-900' }
  if (s === 'normal') return { text: 'NORMAL', className: 'bg-slate-100 text-slate-900' }
  if (s === 'out_of_range') return { text: 'OUT OF RANGE', className: 'bg-rose-100 text-rose-900' }
  return { text: 'UNKNOWN', className: 'bg-amber-100 text-amber-900' }
}

export function DashboardPage() {
  const qc = useQueryClient()
  const [selected, setSelected] = useState<UploadedFile | null>(null)
  const [lastResult, setLastResult] = useState<ExtractionResult | null>(null)
  const [showEvidence, setShowEvidence] = useState(true)

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

  const deleteM = useMutation({
    mutationFn: deleteUploadedFile,
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['files'] })
      setSelected(null)
      setLastResult(null)
    },
  })

  const files = filesQ.data?.files ?? []
  const selectedFromList = useMemo(() => {
    if (!selected) return null
    return files.find((f) => f.id === selected.id) ?? selected
  }, [files, selected])

  return (
    <div className="app-shell">
      <header className="sticky top-0 z-10 border-b border-slate-200/70 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <div className="min-w-0">
            <div className="truncate text-base font-semibold tracking-tight text-slate-900">
              Authorization Document Reader
            </div>
            <div className="mt-0.5 text-xs text-slate-600">
              Upload PDFs, extract structured fields, and export result files.
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              className="btn-secondary text-xs"
              onClick={() => setShowEvidence((v) => !v)}
              title="Toggle evidence snippets"
            >
              {showEvidence ? 'Hide evidence' : 'Show evidence'}
            </button>
            <div className="hidden text-xs text-slate-500 sm:block">
              API <code className="rounded bg-slate-100 px-1.5 py-0.5">/api</code>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl grid-cols-12 gap-6 px-6 py-8">
        <section className="card-elevated col-span-12 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">Core files</div>
              <div className="mt-1 text-xs text-slate-600">Your uploaded authorization PDFs</div>
            </div>
            <label className="btn-primary cursor-pointer">
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
              Upload
            </label>
          </div>

          <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <div className="grid grid-cols-12 bg-slate-50/70 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
              <div className="col-span-6">File</div>
              <div className="col-span-4">Uploaded</div>
              <div className="col-span-2 text-right">Actions</div>
            </div>
            <div className="divide-y divide-slate-200">
              {files.length === 0 && (
                <div className="px-4 py-10 text-center">
                  <div className="text-sm font-medium text-slate-900">No files yet</div>
                  <div className="mt-1 text-sm text-slate-600">Upload a PDF to start extraction.</div>
                </div>
              )}
              {files.map((f) => {
                const active = selectedFromList?.id === f.id
                return (
                  <div
                    key={f.id}
                    role="button"
                    tabIndex={0}
                    className={[
                      'grid w-full cursor-pointer grid-cols-12 items-center px-3 py-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-slate-400/80 focus-visible:ring-offset-2',
                      active
                        ? 'bg-slate-100/70'
                        : 'bg-white hover:bg-slate-50/70',
                    ].join(' ')}
                    onClick={() => {
                      setSelected(f)
                      setLastResult(null)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        setSelected(f)
                        setLastResult(null)
                      }
                    }}
                  >
                    <div className="col-span-6 min-w-0">
                      <div className="truncate text-sm font-semibold text-slate-900">
                        {f.originalName}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-600">{formatBytes(f.sizeBytes)}</div>
                    </div>
                    <div className="col-span-4 truncate text-xs text-slate-600">
                      {new Date(f.uploadedAt).toLocaleString()}
                    </div>
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
                      <button
                        className="btn-danger px-2 py-2 text-xs"
                        onClick={(e) => {
                          e.stopPropagation()
                          const ok = window.confirm(
                            `Delete "${f.originalName}"? This removes the uploaded PDF and its saved JSON result.`
                          )
                          if (!ok) return
                          deleteM.mutate(f.id)
                        }}
                        disabled={deleteM.isPending}
                        title="Delete uploaded file"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {deleteM.isError && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
              {(deleteM.error as Error).message}
            </div>
          )}

          {uploadM.isError && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">
              {(uploadM.error as Error).message}
            </div>
          )}
        </section>

        <section className="card-elevated col-span-12 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-900">Extracted data</div>
              <div className="mt-1 text-xs text-slate-600">Demographics + biomarkers + evidence</div>
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
            <div className="mt-8 rounded-2xl border border-slate-200 bg-white p-5">
              <div className="text-sm font-semibold text-slate-900">Select a file</div>
              <div className="mt-1 text-sm text-slate-600">
                Choose a PDF from the left to run extraction and inspect evidence.
              </div>
            </div>
          )}

          {selectedFromList && !lastResult && (
            <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5">
              <div className="text-sm font-semibold text-slate-900">Ready</div>
              <div className="mt-1 text-sm text-slate-600">
                Run extraction for <span className="font-medium text-slate-900">{selectedFromList.originalName}</span>.
              </div>
            </div>
          )}

          {lastResult && (
            <div className="mt-4">
              <div className="grid grid-cols-1 gap-4">
                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Page analysis
                  </div>

                  {lastResult.pageRouting?.length ? (
                    <div className="mt-2 overflow-hidden rounded-2xl border border-slate-200">
                      <div className="grid grid-cols-12 bg-slate-50/70 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                        <div className="col-span-3">Page</div>
                        <div className="col-span-5">Route</div>
                        <div className="col-span-4 text-right">Chars</div>
                      </div>
                      <div className="divide-y divide-slate-200">
                        {lastResult.pageRouting.map((p) => (
                          <div key={p.page} className="grid grid-cols-12 items-center px-3 py-2 text-sm">
                            <div className="col-span-3 text-slate-700">{p.page + 1}</div>
                            <div className="col-span-5">
                              <span
                                className={[
                                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                                  p.route === 'ocr'
                                    ? 'bg-amber-100 text-amber-900'
                                    : 'bg-emerald-100 text-emerald-900',
                                ].join(' ')}
                              >
                                {p.route.toUpperCase()}
                              </span>
                            </div>
                            <div className="col-span-4 text-right text-xs text-slate-600">{p.chars}</div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      No page routing data available yet.
                    </div>
                  )}

                  {lastResult.extractedV2?.validations?.length ? (
                    <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="text-sm font-semibold text-slate-900">Validations</div>
                      <ul className="mt-2 list-disc pl-5 text-sm text-slate-700">
                        {lastResult.extractedV2.validations.map((v) => (
                          <li key={v}>{v}</li>
                        ))}
                      </ul>
                    </div>
                  ) : (
                    <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                      No validation issues detected.
                    </div>
                  )}

                  {lastResult.extracted.warnings.length > 0 && (
                    <details className="mt-4 overflow-hidden rounded-2xl border border-amber-200 bg-amber-50">
                      <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-amber-900">
                        Warnings ({lastResult.extracted.warnings.length})
                      </summary>
                      <div className="px-4 pb-4">
                        <ul className="mt-1 list-disc pl-5 text-sm text-amber-900">
                          {lastResult.extracted.warnings.map((w) => (
                            <li key={w}>{w}</li>
                          ))}
                        </ul>
                      </div>
                    </details>
                  )}
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Patient & extracted data
                  </div>
                  <div>
                    <FieldRow label="Patient name" value={lastResult.extracted.patient_name} />
                    {showEvidence && lastResult.extractedV2 && (
                      <EvidenceBlock v2={lastResult.extractedV2} field="patient_name" />
                    )}
                  </div>
                  <div>
                    <FieldRow label="Age (years)" value={lastResult.extracted.age_years} />
                    {showEvidence && lastResult.extractedV2 && (
                      <EvidenceBlock v2={lastResult.extractedV2} field="age_years" />
                    )}
                  </div>
                  <div>
                    <FieldRow label="Sex" value={lastResult.extracted.sex} />
                    {showEvidence && lastResult.extractedV2 && (
                      <EvidenceBlock v2={lastResult.extractedV2} field="sex" />
                    )}
                  </div>
                  <div>
                    <FieldRow label="Report date" value={lastResult.extracted.report_date} />
                    {showEvidence && lastResult.extractedV2 && (
                      <EvidenceBlock v2={lastResult.extractedV2} field="report_date" />
                    )}
                  </div>
                  <div>
                    <FieldRow label="Source" value={lastResult.extracted.source} />
                    {showEvidence && lastResult.extractedV2 && (
                      <EvidenceBlock v2={lastResult.extractedV2} field="source" />
                    )}
                  </div>

                  <div className="mt-4 border-t border-slate-200 pt-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Biomarkers ({lastResult.extracted.biomarkers?.length ?? 0})
                      </div>
                      <div className="text-[11px] text-slate-500">standardized name + unit</div>
                    </div>

                    <div className="mt-2 overflow-hidden rounded-2xl border border-slate-200">
                      {(lastResult.extracted.biomarkers ?? []).length === 0 ? (
                        <div className="px-4 py-6 text-sm text-slate-600">
                          No biomarkers extracted yet (check warnings or enable the OpenAI key for robust extraction).
                        </div>
                      ) : (
                        <table className="w-full border-collapse">
                          <thead className="bg-slate-50/70">
                            <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                              <th className="px-3 py-2">Biomarker</th>
                              <th className="px-3 py-2 text-right">Value</th>
                              <th className="px-3 py-2">Unit</th>
                              <th className="px-3 py-2">Range</th>
                              <th className="px-3 py-2 text-right">Status</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-200">
                            {(lastResult.extracted.biomarkers ?? []).map((b, idx) => {
                              const pill = statusPill(b.status)
                              const label = b.name ?? b.original_name ?? '—'
                              return (
                                <tr key={`${label}-${idx}`} className="text-sm">
                                  <td className="px-3 py-2 align-top">
                                    <div className="min-w-0">
                                      <div className="truncate font-medium text-slate-900">{label}</div>
                                      {b.original_name && b.name && b.original_name !== b.name ? (
                                        <div className="truncate text-xs text-slate-500">{b.original_name}</div>
                                      ) : null}
                                    </div>
                                  </td>
                                  <td className="px-3 py-2 text-right align-top font-medium text-slate-900">
                                    {b.value ?? '—'}
                                  </td>
                                  <td className="px-3 py-2 align-top text-slate-700">{b.unit ?? '—'}</td>
                                  <td className="px-3 py-2 align-top text-xs text-slate-700">
                                    {b.reference_range_text ?? '—'}
                                  </td>
                                  <td className="px-3 py-2 align-top text-right">
                                    <span
                                      className={[
                                        'inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold',
                                        pill.className,
                                      ].join(' ')}
                                    >
                                      {pill.text}
                                    </span>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {extractM.isError && (
            <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">
              {(extractM.error as Error).message}
            </div>
          )}
        </section>
      </main>
    </div>
  )
}

