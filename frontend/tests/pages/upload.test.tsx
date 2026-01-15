import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import MultiImageUpload from '../../app/upload/page';
import fetchWithRefresh from '../../app/utils/fetchwithrefresh';

vi.mock('../../app/utils/fetchwithrefresh', () => ({
  default: vi.fn(),
}));

describe('Upload page', () => {
  beforeEach(() => {
    vi.mocked(fetchWithRefresh).mockReset();
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:preview');
  });

  it('uploads selected files', async () => {
    vi.mocked(fetchWithRefresh).mockResolvedValue({ ok: true } as Response);

    const { container } = render(<MultiImageUpload />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['data'], 'sample.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      expect(fetchWithRefresh).toHaveBeenCalled();
    });
  });

  it('shows a failed status when the upload fails', async () => {
    vi.mocked(fetchWithRefresh).mockResolvedValue({ ok: false } as Response);

    const { container, findByText } = render(<MultiImageUpload />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;

    const file = new File(['data'], 'bad.png', { type: 'image/png' });
    fireEvent.change(input, { target: { files: [file] } });

    await expect(findByText(/Failed/)).resolves.toBeInTheDocument();
  });
});
