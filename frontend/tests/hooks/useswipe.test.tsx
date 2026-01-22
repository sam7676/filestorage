import React from 'react';
import { fireEvent, render } from '@testing-library/react';
import { vi } from 'vitest';
import useSwipe from '../../app/utils/useswipe';

function SwipeTarget({ onLeft, onRight }: { onLeft: () => void; onRight: () => void }) {
  const handlers = useSwipe({ onSwipedLeft: onLeft, onSwipedRight: onRight });
  return <div data-testid="target" {...handlers} />;
}

describe('useSwipe', () => {
  it('fires onSwipedLeft when swiped left', () => {
    const onLeft = vi.fn();
    const onRight = vi.fn();
    const { getByTestId } = render(<SwipeTarget onLeft={onLeft} onRight={onRight} />);

    const target = getByTestId('target');
    fireEvent.touchStart(target, { targetTouches: [{ clientX: 200 }] });
    fireEvent.touchMove(target, { targetTouches: [{ clientX: 100 }] });
    fireEvent.touchEnd(target);

    expect(onLeft).toHaveBeenCalledTimes(1);
    expect(onRight).not.toHaveBeenCalled();
  });

  it('fires onSwipedRight when swiped right', () => {
    const onLeft = vi.fn();
    const onRight = vi.fn();
    const { getByTestId } = render(<SwipeTarget onLeft={onLeft} onRight={onRight} />);

    const target = getByTestId('target');
    fireEvent.touchStart(target, { targetTouches: [{ clientX: 100 }] });
    fireEvent.touchMove(target, { targetTouches: [{ clientX: 200 }] });
    fireEvent.touchEnd(target);

    expect(onRight).toHaveBeenCalledTimes(1);
    expect(onLeft).not.toHaveBeenCalled();
  });
});
