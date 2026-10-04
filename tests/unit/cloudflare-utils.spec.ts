import type { H3Event } from 'h3'
import type { Compilable } from 'kysely'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { writeAccessLog } from '../../server/utils/access-log'
import { getAnalyticsDataset, useWAE } from '../../server/utils/cloudflare'

vi.mock('#shared/utils/flag', () => ({ getFlag: vi.fn() }))

const event = {
  context: {
    cloudflare: { env: {} },
    link: { id: 'link-id' },
  },
} as unknown as H3Event

const query = {} as Compilable

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

describe('writeAccessLog', () => {
  it('silently skips production writes without an Analytics Engine binding', () => {
    vi.stubEnv('NODE_ENV', 'production')

    expect(() => writeAccessLog(event, {})).not.toThrow()
  })
})

describe('analytics runtime bindings', () => {
  it('prefers the Cloudflare Worker dataset binding over the Nuxt fallback', () => {
    const bindingEvent = {
      context: {
        cloudflare: {
          env: {
            NUXT_DATASET: 'onzko_link_stg',
          },
        },
      },
    } as unknown as H3Event

    vi.stubGlobal('useRuntimeConfig', () => ({
      dataset: 'sink',
    }))

    expect(getAnalyticsDataset(bindingEvent)).toBe('onzko_link_stg')
  })

  it('uses Cloudflare Worker Analytics credentials when Nuxt runtime values are empty', async () => {
    const bindingEvent = {
      context: {
        cloudflare: {
          env: {
            NUXT_CF_ACCOUNT_ID: 'worker-account',
            NUXT_CF_API_TOKEN: 'worker-token',
          },
        },
      },
    } as unknown as H3Event

    const fetchMock = vi.fn().mockResolvedValue({ data: [] })

    vi.stubGlobal('useRuntimeConfig', () => ({
      cfAccountId: '',
      cfApiToken: '',
    }))
    vi.stubGlobal('compileAnalyticsQuery', () => 'select * from onzko_link_stg')
    vi.stubGlobal('$fetch', fetchMock)

    await useWAE(bindingEvent, query)

    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.cloudflare.com/client/v4/accounts/worker-account/analytics_engine/sql',
      {
        method: 'POST',
        headers: {
          Authorization: 'Bearer worker-token',
        },
        body: 'select * from onzko_link_stg',
        retry: 1,
        retryDelay: 100,
      },
    )
  })
})

describe('useWAE', () => {
  it.each([
    { cfAccountId: '', cfApiToken: 'token' },
    { cfAccountId: 'account', cfApiToken: '' },
  ])('returns empty data without requesting when credentials are incomplete', (config) => {
    const fetchMock = vi.fn()
    vi.stubGlobal('useRuntimeConfig', () => config)
    vi.stubGlobal('$fetch', fetchMock)

    expect(useWAE(event, query)).toEqual({ data: [] })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('preserves requests and propagates errors when credentials are complete', async () => {
    const error = new Error('forbidden')
    const fetchMock = vi.fn().mockRejectedValue(error)
    vi.stubGlobal('useRuntimeConfig', () => ({
      cfAccountId: 'account',
      cfApiToken: 'token',
    }))
    vi.stubGlobal('compileAnalyticsQuery', () => 'select * from sink')
    vi.stubGlobal('$fetch', fetchMock)

    await expect(useWAE(event, query)).rejects.toBe(error)
    expect(fetchMock).toHaveBeenCalledWith(
      'https://api.cloudflare.com/client/v4/accounts/account/analytics_engine/sql',
      {
        method: 'POST',
        headers: { Authorization: 'Bearer token' },
        body: 'select * from sink',
        retry: 1,
        retryDelay: 100,
      },
    )
  })
})
