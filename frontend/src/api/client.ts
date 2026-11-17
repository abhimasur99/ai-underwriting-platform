// Typed API client. The types come from the backend's OpenAPI spec (`make openapi`), so a
// renamed field breaks `npm run typecheck` instead of breaking the demo.
import type { components } from './schema'

type S = components['schemas']
export type QueueRow = S['QueueRow']
export type DealDetail = S['DealDetail']
export type Deal = S['Deal']
export type UnderwritingResult = S['UnderwritingResult']
export type CheckReport = S['CheckReport']
export type Patch = S['Patch']
export type ApiEvent = S['Event']
export type Checklist = S['ChecklistStatus']
export type IntakeStatus = S['IntakeStatus']
export type WorkbookView = S['WorkbookView']
export type ChiefChatResponse = S['ChiefChatResponse']
export type FileRow = S['FileRow']
export type FileText = S['FileText']

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body?.detail) message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* keep the status text */
    }
    throw new ApiError(res.status, message)
  }
  return (await res.json()) as T
}

const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  health: () => request<{ status: string; mode: string }>('/api/health'),
  queue: (includeArchived = false) =>
    request<QueueRow[]>(`/api/deals${includeArchived ? '?include_archived=true' : ''}`),
  archive: (id: string) => request<S['ArchiveResponse']>(`/api/deals/${id}`, { method: 'DELETE' }),
  restore: (id: string) =>
    request<S['ArchiveResponse']>(`/api/deals/${id}/restore`, { method: 'POST' }),
  rename: (id: string, name: string) =>
    request<S['RenameResponse']>(`/api/deals/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
  deal: (id: string) => request<DealDetail>(`/api/deals/${id}`),
  events: (id: string, after = 0) => request<ApiEvent[]>(`/api/deals/${id}/events?after=${after}`),
  fileText: (id: string, fileId: string) => request<FileText>(`/api/deals/${id}/files/${fileId}/text`),
  workbook: (id: string) => request<WorkbookView>(`/api/deals/${id}/workbook`),
  createDeal: () => request<S['CreateDealResponse']>('/api/deals', { method: 'POST' }),
  chat: (id: string, message: string) =>
    request<S['ChatResponse']>(`/api/deals/${id}/chat`, json({ message })),
  upload: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<S['FileResponse_']>(`/api/deals/${id}/files`, { method: 'POST', body: form })
  },
  intakeStatus: (id: string) => request<IntakeStatus>(`/api/deals/${id}/intake-status`),
  chiefChat: (id: string, message: string) =>
    request<ChiefChatResponse>(`/api/deals/${id}/chief-chat`, json({ message })),
  confirmPatch: (id: string, patchId: string) =>
    request<S['StateResponse']>(`/api/deals/${id}/patches/${patchId}/confirm`, { method: 'POST' }),
  cancelPatch: (id: string, patchId: string) =>
    request<S['StateResponse']>(`/api/deals/${id}/patches/${patchId}/cancel`, { method: 'POST' }),
  decide: (id: string, decision: 'approve' | 'send_back' | 'reject' | 'request_info', rationale: string) =>
    request<S['StateResponse']>(`/api/deals/${id}/decision`, json({ decision, rationale })),
}

export const memoUrl = (id: string, bust: number | string) =>
  `/api/deals/${id}/artifacts/memo.pdf?v=${bust}`
export const workbookUrl = (id: string) => `/api/deals/${id}/artifacts/workbook.xlsx`
