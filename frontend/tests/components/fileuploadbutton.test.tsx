import React from 'react';
import { fireEvent, render } from '@testing-library/react';
import { vi } from 'vitest';
import InputFileUpload from '../../react-mui/fileuploadbutton';

describe('InputFileUpload', () => {
  it('renders a file input and forwards change events', () => {
    const onChange = vi.fn();
    const { container, getByText } = render(InputFileUpload(onChange));

    expect(getByText('Upload files')).toBeInTheDocument();

    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();

    const file = new File(['hello'], 'sample.png', { type: 'image/png' });
    fireEvent.change(input as HTMLInputElement, { target: { files: [file] } });

    expect(onChange).toHaveBeenCalledTimes(1);
  });
});
