import React from 'react';
import { act, fireEvent, render, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import View from '../../app/view/page';
import fetchWithRefresh from '../../app/utils/fetchwithrefresh';

vi.mock('../../app/utils/fetchwithrefresh', () => ({
  default: vi.fn(),
}));

const makeHeaders = (values: Record<string, string>) => ({
  get: (key: string) => values[key] ?? null,
});

const makeResponse = (overrides?: Partial<Record<string, string>>) => {
  const headers = makeHeaders({
    'X-Media-Type': 'image',
    'X-Item-ID': '123',
    'X-Label': 'cat',
    'Content-Type': 'image/png',
    'X-Width': '120',
    'X-Height': '80',
    ...overrides,
  });

  return {
    headers,
    blob: async () => new Blob(['data'], { type: 'image/png' }),
  } as unknown as Response;
};

describe('View page', () => {
  beforeEach(() => {
    vi.mocked(fetchWithRefresh).mockReset();
    vi.mocked(fetchWithRefresh).mockResolvedValue(makeResponse());
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:media');
    globalThis.URL.revokeObjectURL = vi.fn();
    globalThis.scrollTo = vi.fn();
    globalThis.alert = vi.fn();
    globalThis.confirm = vi.fn(() => true);
    HTMLCanvasElement.prototype.getContext = vi.fn(() => {
      return {
        fillRect: vi.fn(),
        fillStyle: '',
      } as unknown as CanvasRenderingContext2D;
    });
    HTMLCanvasElement.prototype.toDataURL = vi.fn(() => 'data:image/png;base64,AAA');
  });

  it('loads initial media on mount', async () => {
    const { findByAltText } = render(<View />);

    await expect(findByAltText('Loaded media')).resolves.toBeInTheDocument();
    expect(fetchWithRefresh).toHaveBeenCalled();
  });

  it('calls delete when confirmed', async () => {
    const { findByAltText, getByText } = render(<View />);

    await findByAltText('Loaded media');
    fireEvent.click(getByText('Delete'));

    await waitFor(() => {
      expect(fetchWithRefresh).toHaveBeenCalledWith(
        '/api/delete',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('does not reload media on resize events', async () => {
    window.innerWidth = 1200;
    window.innerHeight = 900;

    const { findByAltText } = render(<View />);
    await findByAltText('Loaded media');

    const initialCalls = vi.mocked(fetchWithRefresh).mock.calls.length;

    window.innerWidth = 800;
    window.innerHeight = 600;
    await act(async () => {
      fireEvent(window, new Event('resize'));
      await new Promise((resolve) => setTimeout(resolve, 250));
    });

    await waitFor(() => {
      expect(vi.mocked(fetchWithRefresh).mock.calls.length).toBe(initialCalls);
    });
  });

  it('recalculates dimensions on resize without replacing media', async () => {
    window.innerWidth = 1200;
    window.innerHeight = 900;

    const { findByAltText } = render(<View />);
    const media = await findByAltText('Loaded media');

    const initialWidth = media.getAttribute('width');
    const initialHeight = media.getAttribute('height');
    expect(initialWidth).toBe('120');
    expect(initialHeight).toBe('80');
    expect(globalThis.URL.createObjectURL).toHaveBeenCalledTimes(1);

    window.innerWidth = 100;
    window.innerHeight = 100;
    await act(async () => {
      fireEvent(window, new Event('resize'));
      await new Promise((resolve) => setTimeout(resolve, 250));
    });

    await waitFor(() => {
      const nextWidth = media.getAttribute('width');
      const nextHeight = media.getAttribute('height');
      expect(nextWidth).not.toBe(initialWidth);
      expect(nextHeight).not.toBe(initialHeight);
      expect(globalThis.URL.createObjectURL).toHaveBeenCalledTimes(1);
    });
  });
});
