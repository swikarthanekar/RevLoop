export interface AccessTokenProvider {
  getAccessToken(): Promise<string | null>;
}

export class NullAccessTokenProvider implements AccessTokenProvider {
  async getAccessToken(): Promise<string | null> {
    return null;
  }
}
