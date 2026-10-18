import { DEFAULT_OPTIONS, readOptions } from './usePersistedOptions'

describe('persisted workspace options', () => {
  beforeEach(() => localStorage.clear())

  it('uses the server timeout by default when no explicit timeout was saved', () => {
    expect(DEFAULT_OPTIONS.timeoutSeconds).toBe(0)
    expect(readOptions().timeoutSeconds).toBe(0)
    localStorage.setItem('moparse.parse-options.v6', JSON.stringify({ language: 'en' }))
    expect(readOptions().timeoutSeconds).toBe(0)
  })

  it.each(['moparse.parse-options.v6', 'mosaicparse.parse-options.v6', 'mosaicparse.parse-options.v5'])(
    'preserves an explicitly saved timeout from %s', (storageKey) => {
      localStorage.setItem(storageKey, JSON.stringify({ timeoutSeconds: 300 }))
      expect(readOptions().timeoutSeconds).toBe(300)
    },
  )

  it('preserves a saved choice to use the server default', () => {
    localStorage.setItem('moparse.parse-options.v6', JSON.stringify({ timeoutSeconds: 0 }))
    expect(readOptions().timeoutSeconds).toBe(0)
  })

  it('prefers moparse options over settings from the previous project name', () => {
    localStorage.setItem('mosaicparse.parse-options.v6', JSON.stringify({ ...DEFAULT_OPTIONS, language: 'en' }))
    localStorage.setItem('moparse.parse-options.v6', JSON.stringify({ ...DEFAULT_OPTIONS, language: 'zh' }))
    expect(readOptions().language).toBe('zh')
  })

  it('loads only the current Markdown option contract', () => {
    localStorage.setItem('mosaicparse.parse-options.v6', JSON.stringify({
      ...DEFAULT_OPTIONS,
      scanPolicy: 'skip',
      mode: 'ocr',
      vlmPolicy: 'removed-value',
    }))

    expect(readOptions()).toEqual({ ...DEFAULT_OPTIONS, scanPolicy: 'skip' })
  })

  it('migrates all removed profile choices to automatic scan routing', () => {
    localStorage.setItem('mosaicparse.parse-options.v5', JSON.stringify({
      ...DEFAULT_OPTIONS,
      profile: 'fast',
      language: 'zh',
    }))

    expect(readOptions()).toEqual({ ...DEFAULT_OPTIONS, scanPolicy: 'auto', language: 'zh' })
  })
})
