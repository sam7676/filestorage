import { vi } from 'vitest';
import fetchWithRefresh from '../../app/utils/fetchwithrefresh';
import { redirect } from 'next/navigation';

vi.mock('next/navigation', () => ({
  redirect: vi.fn(),
  RedirectType: { push: 'push' },
}));

const makeResponse = (status: number) => ({ status }) as Response;

describe('fetchWithRefresh', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let originalRequest: typeof Request;

  beforeEach(() => {
    vi.resetAllMocks();
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    originalRequest = globalThis.Request;
    globalThis.Request = class DummyRequest {
      input: RequestInfo;
      init?: RequestInit;
      constructor(input: RequestInfo, init?: RequestInit) {
        this.input = input;
        this.init = init;
      }
    } as unknown as typeof Request;
  });

  afterEach(() => {
    globalThis.Request = originalRequest;
  });

  it('returns the response on a successful request', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse(200));

    const res = await fetchWithRefresh('/api/example', { method: 'GET' });

    expect(res.status).toBe(200);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(redirect).not.toHaveBeenCalled();
  });

  it('refreshes the token and retries on 401/403', async () => {
    fetchMock
      .mockResolvedValueOnce(makeResponse(401))
      .mockResolvedValueOnce(makeResponse(200))
      .mockResolvedValueOnce(makeResponse(200));

    const res = await fetchWithRefresh('/api/example', { method: 'GET' });

    expect(res.status).toBe(200);
    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    expect(redirect).not.toHaveBeenCalled();
  });

  it('redirects to login if refresh and retry fail', async () => {
    fetchMock
      .mockResolvedValueOnce(makeResponse(403))
      .mockResolvedValueOnce(makeResponse(200))
      .mockResolvedValueOnce(makeResponse(403));

    await fetchWithRefresh('/api/example', { method: 'GET' });

    expect(globalThis.fetch).toHaveBeenCalledTimes(3);
    expect(redirect).toHaveBeenCalledTimes(1);
  });
});
