import { buildParseForm, fetchServiceSnapshot, getApiKey, parseJobEvent, setApiKey } from './client'
import { DEFAULT_OPTIONS } from '../hooks/usePersistedOptions'

describe('API request helpers', () => {
  afterEach(() => vi.restoreAllMocks())

  it('keeps the existing API key through the rename and clears both keys on logout', () => {
    sessionStorage.clear()
    sessionStorage.setItem('mosaicparse.api-key', 'previous-key')
    expect(getApiKey()).toBe('previous-key')
    setApiKey(' current-key ')
    expect(getApiKey()).toBe('current-key')
    expect(sessionStorage.getItem('moparse.api-key')).toBe('current-key')
    expect(sessionStorage.getItem('mosaicparse.api-key')).toBeNull()
    setApiKey('')
    expect(getApiKey()).toBe('')
  })

  it('builds the multipart contract for a file without setting Content-Type itself', () => {
    const file = new File(['pdf'], '报告.pdf', { type: 'application/pdf' })
    const form = buildParseForm(
      { kind: 'file', file, url: '' },
      { ...DEFAULT_OPTIONS, scanPolicy: 'skip', unitRange: '2-4' },
    )
    expect(form.get('file')).toBeInstanceOf(File)
    expect((form.get('file') as File).name).toBe('报告.pdf')
    expect(form.get('scan_policy')).toBe('skip')
    expect(form.get('profile')).toBeNull()
    expect(form.get('unit_range')).toBe('2-4')
    expect(form.get('describe_images')).toBe('false')
    expect(form.get('include_renderings')).toBeNull()
    expect(form.get('mode')).toBeNull()
  })

  it('omits the server timeout when the default is selected', () => {
    const source = { kind: 'url' as const, file: null, url: 'https://example.com/a.pdf' }
    expect(buildParseForm(source, DEFAULT_OPTIONS).has('timeout_seconds')).toBe(false)
    expect(buildParseForm(source, { ...DEFAULT_OPTIONS, timeoutSeconds: 0 }).has('timeout_seconds')).toBe(false)
  })

  it.each([1, 300, 7200, 86400])('sends an explicit timeout of %i seconds unchanged', (timeoutSeconds) => {
    const source = { kind: 'url' as const, file: null, url: 'https://example.com/a.pdf' }
    const form = buildParseForm(source, { ...DEFAULT_OPTIONS, timeoutSeconds })
    expect(form.get('timeout_seconds')).toBe(String(timeoutSeconds))
  })

  it('parses SSE JSON and ignores malformed messages', () => {
    const event = new MessageEvent('job.progress', { data: '{"current":3,"total":10}' })
    expect(parseJobEvent(event)).toMatchObject({ type: 'job.progress', current: 3, total: 10 })
    expect(parseJobEvent(new MessageEvent('message', { data: 'nope' }))).toBeNull()
  })

  it('maps real backend state/detail and queue values without treating configuration as readiness', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      const data = url.endsWith('/health')
        ? { status: 'ok' }
        : url.endsWith('/ready')
          ? { status: 'ready', ready: true }
        : {
          backends: [
            { name: 'docling-standard', state: 'ready', enabled: true },
            { name: 'glm-ocr-remote', state: 'unavailable', enabled: true, detail: 'connection refused' },
            { name: 'glm-sdk-remote', state: 'disabled', enabled: false },
          ],
          queue: { active: 1, capacity: 8 },
        }
      return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    const snapshot = await fetchServiceSnapshot()
    expect(snapshot.api).toBe('ready')
    expect(snapshot.backends.find((backend) => backend.id === 'docling')?.status).toBe('ready')
    expect(snapshot.backends.find((backend) => backend.id === 'glm')).toMatchObject({ status: 'unavailable', message: 'connection refused' })
    expect(snapshot.backends.find((backend) => backend.id === 'glm-sdk')?.status).toBe('disabled')
    expect(snapshot.queue).toEqual({ active: 1, capacity: 8 })
  })

  it('does not report API Ready when liveness succeeds but readiness fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      if (url.endsWith('/ready')) {
        return new Response(JSON.stringify({ status: 'not_ready', ready: false }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      const body = url.endsWith('/health')
        ? { status: 'degraded' }
        : { backends: [], queue: { active: 0, capacity: 8 } }
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
    })
    const snapshot = await fetchServiceSnapshot()
    expect(snapshot.api).toBe('unavailable')
    expect(snapshot.ready).toBe(false)
  })

  it('shows the selected MinerU without inventing a Docling backend', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      const data = url.endsWith('/health') ? { status: 'ok' }
        : url.endsWith('/ready') ? { ready: true }
          : { backends: [
            { name: 'mineru-advanced-txt', state: 'ready', detail: 'FP16 GPU VLM, concurrency=2' },
            { name: 'glm-ocr-remote', state: 'ready' },
            { name: 'glm-sdk-remote', state: 'disabled', enabled: false },
          ] }
      return new Response(JSON.stringify(data), { status: 200 })
    })
    const snapshot = await fetchServiceSnapshot()
    expect(snapshot.backends.map((backend) => backend.id)).toEqual(['mineru', 'glm', 'glm-sdk'])
    expect(snapshot.backends.find((backend) => backend.id === 'mineru')).toMatchObject({ label: 'MinerU Advanced＋TXT', status: 'ready' })
    expect(snapshot.backends.find((backend) => backend.id === 'glm-sdk')?.status).toBe('disabled')
    expect(snapshot.backends.some((backend) => backend.id === 'docling')).toBe(false)
  })

  it('keeps disabled backends disabled and preserves unknown backend identities', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      const data = url.endsWith('/health') ? { status: 'ok' }
        : url.endsWith('/ready') ? { ready: true }
          : { backends: [
            { name: 'mineru-advanced-txt', state: 'ready' },
            { name: 'custom-parser', state: 'ready', enabled: false },
            { name: 'custom-evidence', label: '独立证据后端', state: 'unavailable' },
          ] }
      return new Response(JSON.stringify(data), { status: 200 })
    })
    const snapshot = await fetchServiceSnapshot()
    expect(snapshot.backends.find((backend) => backend.id === 'custom-parser')?.status).toBe('disabled')
    expect(snapshot.backends.find((backend) => backend.id === 'custom-evidence')).toMatchObject({ label: '独立证据后端', status: 'unavailable' })
    expect(snapshot.backends.some((backend) => backend.id === 'docling')).toBe(false)
  })

  it('retains legacy object-shaped backend responses', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      const data = url.endsWith('/health') ? { status: 'ok' }
        : url.endsWith('/ready') ? { ready: true }
          : { docling: 'ready', glm: { enabled: false }, glm_sdk: { status: 'disabled' } }
      return new Response(JSON.stringify(data), { status: 200 })
    })
    const snapshot = await fetchServiceSnapshot()
    expect(snapshot.backends.map(({ id, status }) => ({ id, status }))).toEqual([
      { id: 'docling', status: 'ready' }, { id: 'glm', status: 'disabled' }, { id: 'glm-sdk', status: 'disabled' },
    ])
  })
})
