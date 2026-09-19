import type { VerifyResponse } from '../../shared/types/auth'
import { describe, expect, it } from 'vitest'
import { fetch, fetchWithAuth } from '../utils'

describe('/api/verify', () => {
  it('returns the expected verification data with valid auth', async () => {
    const response = await fetchWithAuth('/api/verify')
    expect(response.status).toBe(200)
    expect(response.headers.get('Content-Type')).toContain('application/json')

    const data = await response.json() as VerifyResponse
    expect(data).toMatchObject({
      name: 'Sink',
      url: 'https://sink.cool',
      authMethod: 'site-token',
      userID: 'root',
      userEmail: 'root@localhost',
      accessEnabled: false,
    })
  })

  it('accepts a dedicated API token for machine authentication', async () => {
    const apiToken = import.meta.env.NUXT_API_TOKEN

    expect(apiToken).toBeTruthy()
    expect(apiToken).not.toBe(import.meta.env.NUXT_SITE_TOKEN)

    const response = await fetch('/api/verify', {
      headers: {
        Authorization: `Bearer ${apiToken}`,
      },
    })

    expect(response.status).toBe(200)

    const data = await response.json() as VerifyResponse
    expect(data).toMatchObject({
      name: 'Sink',
      url: 'https://sink.cool',
      authMethod: 'api-token',
      userID: 'machine',
      userEmail: 'machine@localhost',
      accessEnabled: false,
    })
  })

  it('returns 401 when accessing without auth', async () => {
    const response = await fetch('/api/verify')
    expect(response.status).toBe(401)
  })

  it('returns 401 with invalid token', async () => {
    const response = await fetch('/api/verify', {
      headers: { Authorization: 'Bearer invalid-token-12345' },
    })
    expect(response.status).toBe(401)
  })

  it('does not trust an Access header when Access is not configured', async () => {
    const response = await fetch('/api/verify', {
      headers: { 'Cf-Access-Jwt-Assertion': 'unsigned-token' },
    })
    expect(response.status).toBe(401)
  })

  it('does not trust an Access cookie when Access is not configured', async () => {
    const response = await fetch('/api/verify', {
      headers: { Cookie: 'CF_Authorization=unsigned-token' },
    })
    expect(response.status).toBe(401)
  })
})
