export const runtime = 'nodejs'

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function isConnReset(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false
  const anyErr = err as { code?: unknown; cause?: { code?: unknown } }
  return anyErr.code === 'ECONNRESET' || anyErr.cause?.code === 'ECONNRESET'
}

function copyHeaders(src: Headers): Headers {
  const dst = new Headers()
  src.forEach((value, key) => {
    // Drop hop-by-hop headers.
    if (key.toLowerCase() === 'connection') return
    if (key.toLowerCase() === 'transfer-encoding') return
    if (key.toLowerCase() === 'keep-alive') return
    if (key.toLowerCase() === 'proxy-authenticate') return
    if (key.toLowerCase() === 'proxy-authorization') return
    if (key.toLowerCase() === 'te') return
    if (key.toLowerCase() === 'trailer') return
    if (key.toLowerCase() === 'upgrade') return
    dst.set(key, value)
  })
  return dst
}

export async function POST(
  request: Request,
  ctx: { params: Promise<{ fileId: string }> },
): Promise<Response> {
  const { fileId } = await ctx.params

  const backendBase = process.env.BACKEND_BASE_URL ?? 'http://127.0.0.1:8012'
  const reqUrl = new URL(request.url)
  const targetUrl = new URL(`/api/extract/${encodeURIComponent(fileId)}`, backendBase)
  targetUrl.search = reqUrl.search

  let lastErr: unknown
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const upstream = await fetch(targetUrl, {
        method: 'POST',
        // The backend uses the path/query only; no body is required.
        headers: {
          accept: 'application/json',
        },
        cache: 'no-store',
      })

      const buf = await upstream.arrayBuffer()
      const headers = copyHeaders(upstream.headers)
      headers.set('x-proxied-by', 'next-route-handler')
      return new Response(buf, {
        status: upstream.status,
        headers,
      })
    } catch (err) {
      lastErr = err
      if (isConnReset(err) && attempt === 0) {
        // In dev, Uvicorn --reload can reset in-flight connections; retry once.
        await sleep(350)
        continue
      }
      break
    }
  }

  return new Response(
    JSON.stringify({
      error: 'Upstream request failed',
      code: isConnReset(lastErr) ? 'ECONNRESET' : 'UPSTREAM_ERROR',
    }),
    { status: 502, headers: { 'content-type': 'application/json' } },
  )
}

