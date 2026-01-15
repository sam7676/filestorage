import { vi } from 'vitest';
import isAuthenticated from '../../app/utils/checkauthenticated';

describe('isAuthenticated', () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    globalThis.fetch = fetchMock as unknown as typeof fetch;
  });

  it('returns true when the API returns 200', async () => {
    fetchMock.mockResolvedValueOnce({ status: 200 } as Response);

    await expect(isAuthenticated()).resolves.toBe(true);
  });

  it('returns false when the API returns non-200', async () => {
    fetchMock.mockResolvedValueOnce({ status: 403 } as Response);

    await expect(isAuthenticated()).resolves.toBe(false);
  });
});
