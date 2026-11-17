// A sourced field points at its document with "line 12" or "rows 2-41". The Files tab highlights it.
export interface Span {
  from: number
  to: number
}

export function parseLocator(locator: string | null | undefined): Span | null {
  if (!locator) return null
  const line = /^line (\d+)$/.exec(locator.trim())
  if (line) return { from: +line[1], to: +line[1] }
  const rows = /^rows (\d+)-(\d+)$/.exec(locator.trim())
  if (rows) return { from: +rows[1], to: +rows[2] }
  return null
}

export const inSpan = (span: Span | null, line: number) =>
  span !== null && line >= span.from && line <= span.to
