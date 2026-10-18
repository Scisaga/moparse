import { curlExample, pythonExample } from './apiExample'
import { DEFAULT_OPTIONS } from '../hooks/usePersistedOptions'

describe('API examples', () => {
  it('uses the asynchronous endpoint and current URL parameters', () => {
    const example = curlExample(
      { kind: 'url', file: null, url: 'https://example.com/a.pdf' },
      { ...DEFAULT_OPTIONS, scanPolicy: 'auto', unitRange: '1-2' },
      'http://localhost:12303',
    )
    expect(example).toContain('/v1/content/jobs')
    expect(example).toContain('/v1/content/jobs/$JOB_ID/result')
    expect(example).toContain('Accept: text/markdown')
    expect(example).toContain('result.md')
    expect(example).toContain('source_url=https://example.com/a.pdf')
    expect(example).toContain('unit_range=1-2')
    expect(example).toContain('scan_policy=auto')
    expect(example).toContain('${MOPARSE_API_KEY:-${MOSAICPARSE_API_KEY:-}}')
    expect(example).not.toContain('profile=')
    expect(example).not.toContain('mode=')
  })

  it('omits the parser timeout in default examples while retaining an HTTP request timeout', () => {
    const source = { kind: 'url' as const, file: null, url: 'https://example.com/a.pdf' }
    expect(curlExample(source, DEFAULT_OPTIONS)).not.toContain('timeout_seconds')
    const python = pythonExample(source, DEFAULT_OPTIONS)
    expect(python).not.toContain('timeout_seconds')
    expect(python).toContain('timeout=300')
  })

  it.each([300, 7200, 86400])('preserves explicit parser timeout %i in examples', (timeoutSeconds) => {
    const source = { kind: 'url' as const, file: null, url: 'https://example.com/a.pdf' }
    const options = { ...DEFAULT_OPTIONS, timeoutSeconds }
    expect(curlExample(source, options)).toContain(`timeout_seconds=${timeoutSeconds}`)
    expect(pythonExample(source, options)).toContain(`"timeout_seconds": "${timeoutSeconds}"`)
  })

  it('produces a usable asynchronous Python file upload example', () => {
    const example = pythonExample(
      { kind: 'file', file: new File(['x'], 'report.pdf'), url: '' },
      DEFAULT_OPTIONS,
      'http://localhost:12303',
    )
    expect(example).toContain('/v1/content/jobs')
    expect(example).toContain("/v1/content/jobs/{job['id']}/result")
    expect(example).toContain('"Accept": "text/markdown"')
    expect(example).toContain('files={"file"')
    expect(example).toContain('report.pdf')
    expect(example).toContain('os.getenv("MOPARSE_API_KEY", os.getenv("MOSAICPARSE_API_KEY", ""))')
  })
})
