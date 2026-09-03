export interface AccessTokenProvider {
  getAccessToken(): Promise<string | null>;
}

export class NullAccessTokenProvider implements AccessTokenProvider {
  async getAccessToken(): Promise<string | null> {
    return null;
  }
}

/**
 * Supplies the development/demo bearer token the backend's DevAuthBackend
 * expects (`dev-analyst`, `dev-operator`, `dev-admin`).
 *
 * The token comes from `NEXT_PUBLIC_DEV_AUTH_TOKEN` and must be set explicitly.
 * When it is absent — which is the production case — this behaves exactly like
 * NullAccessTokenProvider and no Authorization header is sent, so a missing
 * variable can never silently grant a role.
 */
export class DevAccessTokenProvider implements AccessTokenProvider {
  async getAccessToken(): Promise<string | null> {
    const token = process.env.NEXT_PUBLIC_DEV_AUTH_TOKEN?.trim();
    return token ? token : null;
  }
}

/** The provider the browser application uses for backend requests. */
export function createAccessTokenProvider(): AccessTokenProvider {
  return new DevAccessTokenProvider();
}
