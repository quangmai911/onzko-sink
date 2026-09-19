import { timingSafeEqual } from 'node:crypto'
import { env as workerEnv } from 'cloudflare:workers'

export default eventHandler(async (event) => {
  if (!event.path.startsWith('/api/'))
    return

  const token = getHeader(event, 'Authorization')?.replace(/^Bearer\s+/, '')
  const runtimeConfig = useRuntimeConfig(event)
  const bindings = workerEnv as unknown as Record<string, unknown>
  const siteToken = getSecretBinding(bindings, 'NUXT_SITE_TOKEN') || runtimeConfig.siteToken
  const apiToken = getSecretBinding(bindings, 'NUXT_API_TOKEN') || runtimeConfig.apiToken
  const hostname = getRequestURL(event).hostname

  if (await verifyToken(token, siteToken)) {
    event.context.authMethod = 'site-token'
    event.context.userID = 'root'
    event.context.userEmail = `root@${hostname}`
    return
  }

  if (await verifyToken(token, apiToken)) {
    event.context.authMethod = 'api-token'
    event.context.userID = 'machine'
    event.context.userEmail = `machine@${hostname}`
    return
  }

  const accessIdentity = await verifyCloudflareAccess(event)
  if (accessIdentity) {
    if (isCloudflareAccessRequestAllowed(event)) {
      Object.assign(
        event.context,
        mapCloudflareAccessIdentity(accessIdentity, hostname),
      )
      return
    }

    throw createError({
      status: 403,
      statusText: 'Forbidden',
    })
  }

  if (token && token.length < 8) {
    throw createError({
      status: 401,
      statusText: 'Token is too short',
    })
  }

  throw createError({
    status: 401,
    statusText: 'Unauthorized',
  })
})

function getSecretBinding(env: Record<string, unknown>, name: string): string {
  const value = env[name]
  return typeof value === 'string' ? value : ''
}

async function verifyToken(provided: string | undefined, expected: string): Promise<boolean> {
  if (!provided || !expected)
    return false

  const encoder = new TextEncoder()
  const [providedHash, expectedHash] = await Promise.all([
    crypto.subtle.digest('SHA-256', encoder.encode(provided)),
    crypto.subtle.digest('SHA-256', encoder.encode(expected)),
  ])

  return timingSafeEqual(
    new Uint8Array(providedHash),
    new Uint8Array(expectedHash),
  )
}
