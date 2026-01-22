'use client';

import fetchWithRefresh from '../utils/fetchwithrefresh';
import { redirect, RedirectType } from 'next/navigation';

import React, { useState, useEffect } from 'react';
import useSwipe from '../utils/useswipe';

type Tuple = [string, string, string];

const CONDITIONS_OPTIONS = [
  'is',
  'is not',
  'contains',
  'does not contain',
  'is null',
  'is not null',
];
const SPLIT_OPTIONS_MAP = new Map([
  ['i', 'is'],
  ['is', 'is'],
  ['in', 'is not'],
  ['c', 'contains'],
  ['dnc', 'does not contain'],
  ['n', 'is null'],
  ['nn', 'is not null'],
]);

const DEFAULT_QUEUE_SIZE = 2;

export default function View() {
  // State variables
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);
  const [currentType, setCurrentType] = useState<'image' | 'video' | null>(null);
  const [currentLabel, setCurrentLabel] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [currentWidth, setCurrentWidth] = useState<number>(0);
  const [currentHeight, setCurrentHeight] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [playLoading, setPlayLoading] = useState(false);

  const [tuples, setTuples] = useState<Tuple[]>([]);
  const [newFirst, setNewFirst] = useState('');
  const [newSecond, setNewSecond] = useState(CONDITIONS_OPTIONS[0]);
  const [newThird, setNewThird] = useState('');

  const [imageQueue, setImageQueue] = useState<Promise<Response>[]>([]);
  const [videoQueue, setVideoQueue] = useState<Promise<Response>[]>([]);
  const [storedTuples, setStoredTuples] = useState<Tuple[]>([]);

  const [queueSize, setQueueSize] = useState<number>(DEFAULT_QUEUE_SIZE);

  const swipeHandlers = useSwipe({
    onSwipedLeft: () => loadMedia('video'),
    onSwipedRight: () => loadMedia('image'),
  });

  let maxHeight = 676;
  let maxWidth = 400;

  try {
    maxHeight = window.innerHeight - 16 || 676;
    maxWidth = window.innerWidth - 16 || 400;
  } catch (e) {}

  const backgroundColor = '#1F1F1F';
  const loadingColor = '#000000';

  function getHalfWidth(width: number) {
    return Math.max(1, Math.floor(width / 2) - 1);
  }

  function getQuarterWidth(width: number) {
    return Math.max(1, Math.floor(width / 4) - 10);
  }

  function getRemainingHalfHeight(height: number) {
    return Math.max(1, Math.floor((maxHeight - height) / 2));
  }

  function getErrorMessage(error: unknown) {
    if (error instanceof Error) return error.message;
    return String(error);
  }

  const reportError = ({ message }: { message: string }) => {
    if (message == 'Response.blob: Body has already been consumed.') {
    } else if (message == 'Body is disturbed or locked') {
    } else if (message == 'The operation timed out.') {
      alert('The operation timed out.');
      try {
        window.location.reload();
      } catch (e) {}
    } else {
      alert(`Failed to load media. Check console for details. Error: ${message}.`);
    }
  };

  const checkPlayInTuples = async () => {
    if (playLoading) {
      return;
    }

    setPlayLoading(true);

    for (const element of storedTuples) {
      if (element[0] == 'play' && !playLoading) {
        const speed = parseFloat(element[2]);

        await new Promise((r) => setTimeout(r, speed * 1000));
        await loadMedia('image', false);
      }
    }

    setPlayLoading(false);
  };

  function createImage() {
    var pixels = [[loading ? loadingColor : backgroundColor]];
    try {
      var canvas = document.createElement('canvas');
      canvas.width = pixels[0].length;
      canvas.height = pixels.length;
      var context = canvas.getContext('2d');
      if (context)
        for (var r = 0; r < canvas.height; r++) {
          for (var c = 0; c < canvas.width; c++) {
            context.fillStyle = pixels[r][c];
            context.fillRect(c, r, 1, 1);
          }
        }
      return canvas.toDataURL('image/png');
    } catch (e) {
    } finally {
    }
  }

  function updateBuffer() {
    if (tuples != storedTuples) {
      setImageQueue([]);
      setVideoQueue([]);
      setStoredTuples(tuples);
    }

    const types = ['image', 'video'];
    const queues = [imageQueue, videoQueue];

    for (var i = 0; i < queues.length; i++) {
      const type = types[i];
      const queue = queues[i];

      // Setting body with tuples
      const body = {
        tags: tuples.map(([name, condition, value]) => ({
          name,
          condition,
          value,
        })),
        type: type,
      };

      while (queue.length < queueSize) {
        const promise = fetchWithRefresh(`/api/download`, {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          signal: AbortSignal.timeout(300 * 1000),
          body: JSON.stringify(body),
        });

        queue.push(promise);
      }

      while (queue.length > queueSize) {
        queue.pop();
      }
    }
  }

  async function updateQueue(value: number) {
    setQueueSize(Math.max(0, queueSize + value));
    updateBuffer();
  }

  // Main function to fetch and display media
  async function loadMedia(type: 'image' | 'video', scroll: boolean = true) {
    if (loading) {
      return;
    }

    setLoading(true);
    try {
      document.body.style.backgroundColor = loadingColor;
    } catch (e) {}

    try {
      if (queueSize == 0) {
        var queue = loadMediaSingle(type);
      } else {
        // Update our buffer

        updateBuffer();

        // Grab first item based off our type (await)

        var queue = type == 'image' ? imageQueue : videoQueue;
      }

      const response = await queue[0];

      // Get metadata from custom headers
      var returnedType = response.headers.get('X-Media-Type');
      const itemId = response.headers.get('X-Item-ID');
      const returnedLabel = response.headers.get('X-Label');
      const mimeType = response.headers.get('Content-Type');

      // Width-height sizing
      var width = parseInt(response.headers.get('X-Width') || '0');
      var height = parseInt(response.headers.get('X-Height') || '0');

      if (height > maxHeight) {
        width = Math.round((width * maxHeight) / height);
        height = maxHeight;
      }
      if (width > maxWidth) {
        height = Math.round((height * maxWidth) / width);
        width = maxWidth;
      }

      const blob = await response.blob();

      // Clean up old URL if it exists
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
      }

      if (returnedType != 'image' && returnedType != 'video') {
        returnedType = null;
      }

      const newUrl = URL.createObjectURL(blob);
      setCurrentUrl(newUrl);
      setCurrentType(returnedType);
      setCurrentLabel(returnedLabel);
      setCurrentId(itemId);
      setCurrentWidth(width);
      setCurrentHeight(height);

      // Remove element from queue
      queue.shift();

      updateBuffer();

      if (scroll) {
        window.scrollTo({ top: 0, left: 0 });
      }

      checkPlayInTuples();
    } catch (error) {
      reportError({ message: getErrorMessage(error) });
    } finally {
      setLoading(false);
      try {
        document.body.style.backgroundColor = backgroundColor;
      } catch (e) {}
    }
  }

  function loadMediaSingle(type: 'image' | 'video') {
    const body = {
      tags: tuples.map(([name, condition, value]) => ({
        name,
        condition,
        value,
      })),
      type: type,
    };

    const promise = fetchWithRefresh(`/api/download`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(300 * 1000),
    });

    var queue = [promise];

    return queue;
  }

  async function deleteItem() {
    if (confirm('Are you sure you wish to delete?')) {
      await fetchWithRefresh(`/api/delete`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ item_id: currentId }),
      });
      loadMedia(currentType || 'image');
    }
  }

  const addTuple = async () => {
    if (newFirst.trim()) {
      var isInFirst = false;
      const split = newFirst.trim().split(' ');

      // convert to list and take that
      if (split.length == 3 && SPLIT_OPTIONS_MAP.has(split[1].trim())) {
        const first = split[0].trim();
        const second = SPLIT_OPTIONS_MAP.get(split[1].trim()) || 'is';
        const third = split[2].trim();

        const newTuple: Tuple = [first.trim(), second, third.trim()];
        setTuples((prev) => [...prev, newTuple]);
        setNewFirst('');
        setNewSecond(CONDITIONS_OPTIONS[0]);
        setNewThird('');

        isInFirst = true;
      }

      if (!isInFirst && newThird.trim()) {
        const newTuple: Tuple = [newFirst.trim(), newSecond, newThird.trim()];
        setTuples((prev) => [...prev, newTuple]);
        setNewFirst('');
        setNewSecond(CONDITIONS_OPTIONS[0]);
        setNewThird('');
      }
    }
  };

  const addLabelAsTuple = async () => {
    const newTuple: Tuple = ['label', 'is', currentLabel ?? ''];
    setTuples((prev) => [...prev, newTuple]);
    setNewFirst('');
    setNewSecond(CONDITIONS_OPTIONS[0]);
    setNewThird('');
  };

  const deleteTuple = async (index: number) => {
    setTuples((prev) => prev.filter((_, i) => i !== index));
  };

  // Load media when page loads
  useEffect(() => {
    loadMedia('image');
  }, []);

  // Cleanup URL on unmount
  useEffect(() => {
    return () => {
      if (currentUrl) {
        URL.revokeObjectURL(currentUrl);
      }
    };
  }, [currentUrl]);

  useEffect(() => {
    updateBuffer();
  }, [tuples]);

  useEffect(() => {}, [imageQueue]);

  useEffect(() => {}, [videoQueue]);

  useEffect(() => {
    const handleDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') {
        loadMedia('image');
      } else if (e.key === 'ArrowRight') {
        loadMedia('video');
      }
    };
    window.addEventListener('keydown', handleDown);
    return () => window.removeEventListener('keydown', handleDown);
  }, [loadMedia]);

  return (
    <div
      {...swipeHandlers}
      className="min-h-screen bg-gray-100 p-8 flex items-center justify-center"
      style={{
        maxWidth: 'fit-content',
        marginLeft: 'auto',
        marginRight: 'auto',
        color: 'white',
        scrollbarColor: 'black',
        overflow: 'hidden',
      }}
    >
      <div className="w-full">
        <div id="media-container" className="bg-white rounded-lg shadow-lg p-4 justify-center">
          <img
            src={createImage()}
            width={1}
            height={getRemainingHalfHeight(currentHeight)}
            className="max-w-full h-auto"
          />

          {currentUrl && currentType === 'image' && (
            <img
              src={currentUrl}
              width={currentWidth}
              height={currentHeight}
              alt="Loaded media"
              className="max-w-full h-auto"
              onClick={() => loadMedia('image')}
            />
          )}

          {currentUrl && currentType === 'video' && (
            <video
              src={currentUrl}
              width={currentWidth}
              height={currentHeight}
              controls
              loop
              autoPlay
              className="max-w-full h-auto "
            />
          )}

          {(!currentUrl || !currentId) && !loading && (
            <p className="text-gray-500 text-center py-8">No media loaded</p>
          )}

          <img
            src={createImage()}
            width={1}
            height={getRemainingHalfHeight(currentHeight)}
            className="max-w-full h-auto"
          />
        </div>
        <br></br>
        <div className="flex gap-4 mb-6 justify-center">
          <button
            onClick={() => loadMedia('image')}
            disabled={loading}
            className="px-6 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-gray-400"
            style={{
              width: `${getHalfWidth(currentWidth)}px`,
              height: '30px',
              fontSize: '20',
              backgroundColor: loading ? loadingColor : backgroundColor,
            }}
          >
            {loading ? 'Loading...' : 'Image'}
          </button>
          <button
            onClick={() => loadMedia('video')}
            disabled={loading}
            className="px-6 py-2 bg-green-500 text-white rounded hover:bg-green-600 disabled:bg-gray-400"
            style={{
              width: `${getHalfWidth(currentWidth)}px`,
              height: '30px',
              fontSize: '20',
              backgroundColor: loading ? loadingColor : backgroundColor,
            }}
          >
            {loading ? 'Loading...' : 'Video'}
          </button>
        </div>

        <div
          style={{
            maxWidth: 'fit-content',
            marginLeft: 'auto',
            marginRight: 'auto',
            textAlign: 'center',
          }}
        >
          {`${currentLabel} `}
          <button
            onClick={addLabelAsTuple}
            style={{ backgroundColor: loading ? loadingColor : backgroundColor }}
          >
            +
          </button>
          {` ${currentId}`}
          <br></br>

          <button
            onClick={() => updateQueue(-1)}
            style={{
              backgroundColor: loading ? loadingColor : backgroundColor,
              border: loading ? loadingColor : backgroundColor,
            }}
          >
            -
          </button>
          {` Queue size ${queueSize} `}
          <button
            onClick={() => updateQueue(1)}
            style={{
              backgroundColor: loading ? loadingColor : backgroundColor,
              border: loading ? loadingColor : backgroundColor,
            }}
          >
            +
          </button>
          <br></br>

          <button
            type="button"
            onClick={() => redirect('/?upload', RedirectType.push)}
            style={{
              width: `${getHalfWidth(currentWidth)}px`,
              backgroundColor: loading ? loadingColor : backgroundColor,
            }}
          >
            Upload
          </button>
          <button
            type="button"
            onClick={() => redirect('/view', RedirectType.push)}
            style={{
              width: `${getHalfWidth(currentWidth)}px`,
              backgroundColor: loading ? loadingColor : backgroundColor,
            }}
          >
            View
          </button>
          <br></br>
          <button
            onClick={() => deleteItem()}
            disabled={loading}
            style={{
              width: `${currentWidth}px`,
              height: '50px',
              backgroundColor: loading ? loadingColor : backgroundColor,
              display: 'inline-block',
            }}
          >
            {' '}
            Delete
          </button>
        </div>
      </div>

      <div
        className="justify-center"
        style={{
          maxWidth: 'fit-content',
          marginLeft: 'auto',
          marginRight: 'auto',
          textAlign: 'center',
        }}
      >
        <div className="flex justify-center">
          <input
            type="text"
            value={newFirst}
            onChange={(e) => setNewFirst(e.target.value)}
            onKeyDown={(e) => {
              if (e.key == 'Enter') {
                addTuple();
              }
            }}
            placeholder="name"
            style={{
              width: `${getQuarterWidth(currentWidth)}px`,
              backgroundColor: loading ? loadingColor : backgroundColor,
              color: '#FFFFFF',
            }}
          />
          <select
            value={newSecond}
            onChange={(e) => setNewSecond(e.target.value)}
            style={{
              width: `${getQuarterWidth(currentWidth)}px`,
              backgroundColor: loading ? loadingColor : backgroundColor,
              color: '#FFFFFF',
            }}
          >
            {CONDITIONS_OPTIONS.map((op) => (
              <option key={op} value={op}>
                {op}
              </option>
            ))}
          </select>
          <input
            type="text"
            value={newThird}
            onChange={(e) => setNewThird(e.target.value)}
            onKeyDown={(e) => {
              if (e.key == 'Enter') {
                addTuple();
              }
            }}
            placeholder="value"
            style={{
              width: `${getQuarterWidth(currentWidth)}px`,
              backgroundColor: loading ? loadingColor : backgroundColor,
              color: '#FFFFFF',
            }}
          />
          <button
            onClick={addTuple}
            className="ml-auto px-3 text-white disabled:opacity-30"
            disabled={!newFirst.trim()}
            style={{
              width: `${getQuarterWidth(currentWidth)}px`,
              backgroundColor: loading ? loadingColor : backgroundColor,
              color: '#FFFFFF',
            }}
          >
            Add
          </button>
        </div>

        {tuples.map((tuple, index) => (
          <div key={index} className="flex justify-center">
            <span
              style={{
                width: `${getQuarterWidth(currentWidth)}px`,
                display: 'inline-block',
              }}
            >
              {tuple[0]}
            </span>
            <span
              style={{
                width: `${getQuarterWidth(currentWidth)}px`,
                display: 'inline-block',
              }}
            >
              {tuple[1]}
            </span>
            <span
              style={{
                width: `${getQuarterWidth(currentWidth)}px`,
                display: 'inline-block',
              }}
            >
              {tuple[2]}
            </span>
            <button
              onClick={() => deleteTuple(index)}
              className="ml-auto px-3 text-white disabled:opacity-30"
              style={{
                width: `50px`,
              }}
            >
              X
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
