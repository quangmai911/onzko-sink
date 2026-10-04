import type { H3Event } from 'h3'
import type { Compilable } from 'kysely'

function getCloudflareEnvString(event: H3Event, name: string): string {
  const env = event.context.cloudflare?.env as unknown as Record<string, unknown> | undefined
  const value = env?.[name]

  return typeof value === 'string' ? value.trim() : ''
}

export function getAnalyticsDataset(event: H3Event): string {
  const { dataset } = useRuntimeConfig(event)

  return getCloudflareEnvString(event, 'NUXT_DATASET') || dataset
}

export function useWAE(event: H3Event, query: Compilable) {
  const runtimeConfig = useRuntimeConfig(event)

  const cfAccountId
    = getCloudflareEnvString(event, 'NUXT_CF_ACCOUNT_ID')
      || runtimeConfig.cfAccountId

  const cfApiToken
    = getCloudflareEnvString(event, 'NUXT_CF_API_TOKEN')
      || runtimeConfig.cfApiToken

  if (!cfAccountId || !cfApiToken)
    return { data: [] }

  const compiledQuery = compileAnalyticsQuery(query)

  if (import.meta.dev)
    console.info('useWAE', compiledQuery)

  return $fetch(`https://api.cloudflare.com/client/v4/accounts/${cfAccountId}/analytics_engine/sql`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${cfApiToken}`,
    },
    body: compiledQuery,
    retry: 1,
    retryDelay: 100, // ms
  })
}
