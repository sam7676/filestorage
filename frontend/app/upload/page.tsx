'use client';

import InputFileUpload from '../../react-mui/fileuploadbutton';
import React, { useState, useEffect } from 'react';
import fetchWithRefresh from '../utils/fetchwithrefresh';
import { redirect, RedirectType } from 'next/navigation';
import isAuthenticated from '../utils/checkauthenticated';


export default function MultiImageUpload() {

    // Creates an array of file objects, updated with setImages
    type ImageItem = {
        file: File;
        type: string;
        previewUrl: string;
        status: string;
    };

    const [imageQueue, setImageQueue] = useState<ImageItem[]>([]);

    type StatusButtonProps = {
        label: string;
        i: number;
    };
    
    try {
        document.body.style.backgroundColor = "#1F1F1F";
    } catch (e) { }
    
    function StatusButton({ label, i }: StatusButtonProps) {
        return (
            <button
                onClick={() => {
                    const newQueue = [...imageQueue];
                    newQueue.splice(i, 1);
                    setImageQueue(newQueue);
                }}
                style={{
                    backgroundColor: '#444',
                    color: 'white',
                    border: 'none',
                    padding: '0.4rem 0.8rem',
                    borderRadius: '6px',
                    cursor: 'pointer'
                }}
            >
                {label}
            </button >
        );
    }


    // Handles upload being populated
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const files = Array.from(e.target.files || []);
        const newItems = files.map(file => ({
            file,
            type: file.type.split('/')[0],
            previewUrl: URL.createObjectURL(file),
            status: 'unprocessed',
        }));

        setImageQueue(prev => [...prev, ...newItems]);
    };

    // auto-process queue as it updates
    useEffect(() => {
        const unprocessed = imageQueue.filter(item => item.status == 'unprocessed');
        if (unprocessed.length === 0) return;

        const processNext = async () => {

            // count pending and ignore if 5 are already pending

            const pendingCount = imageQueue.filter(item => item.status == 'pending').length
            if (pendingCount > 5) return;

            const next = unprocessed[0];
            try {
                const formData = new FormData();
                formData.append(next.type, next.file);

                // Updating the status of the image queue

                setImageQueue(prev =>
                    prev.map(item =>
                        item.previewUrl === next.previewUrl
                            ? { ...item, status: 'pending' }
                            : item
                    )
                );

                try {
                    const res = await fetchWithRefresh('/api/upload', {
                        method: 'POST',
                        body: formData,
                        credentials: 'include',
                    });

                    if (!res.ok) {

                        setImageQueue(prev =>
                            prev.map(item =>
                                item.previewUrl === next.previewUrl
                                    ? { ...item, status: 'failed' }
                                    : item
                            )
                        );
                        throw new Error('Upload failed')

                    };
                }
                catch (err) {
                    setImageQueue(prev =>
                        prev.map(item =>
                            item.previewUrl === next.previewUrl
                                ? { ...item, status: 'failed' }
                                : item
                        ));
                    throw err;
                }


                setImageQueue(prev =>
                    prev.map(item =>
                        item.previewUrl === next.previewUrl
                            ? { ...item, status: 'processed' }
                            : item
                    )
                );

                setImageQueue(prev =>
                    prev.filter(item => item.status != 'processed')
                );


            } catch (err) {
                console.error('Error processing image:', err);
            }
        };

        processNext();
    }, [imageQueue]); // Runs every time imageQueue updates


    return (
        <div className="min-h-screen bg-gray-100 p-8 flex items-center justify-center"
            style={{
                maxWidth: 'fit-content',
                marginLeft: 'auto',
                marginRight: 'auto',
            }}>

            <button type="button" onClick={() => redirect('/upload', RedirectType.push)} style={{ width: `69px` }}>Upload</button>
            <button type="button" onClick={() => redirect('/view', RedirectType.push)} style={{ width: `68px` }}>View</button>
            <br></br>
            {InputFileUpload(handleChange)}

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem' }}>
                {imageQueue.map((item, i) => (
                    <div key={i} style={{ textAlign: 'center' }}>
                        <img
                            src={item.previewUrl}
                            alt={`preview-${i}`}
                            width={100}
                            style={{ borderRadius: '8px' }}
                        />

                        <p style={{ marginTop: '0.5rem' }}>

                            {item.file.name.substring(0, item.file.name.lastIndexOf('.')) || item.file.name}

                        </p>

                        <p style={{ marginTop: '0.5rem' }}>

                            {(() => {
                                switch (item.status) {
                                    case 'processed':
                                        return < StatusButton
                                            label='✅ Processed'
                                            i={i}
                                        />
                                    case 'pending':
                                        return < StatusButton
                                            label='⏳ Pending'
                                            i={i}
                                        />
                                    case 'unprocessed':
                                        return < StatusButton
                                            label='📭 Unprocessed'
                                            i={i}
                                        />
                                    case 'failed':
                                        return < StatusButton
                                            label='❌ Failed'
                                            i={i}
                                        />

                                    default:
                                        return < StatusButton
                                            label='❔ Unknown status'
                                            i={i}
                                        />
                                }
                            })()}
                        </p>
                    </div>
                ))}
            </div>
        </div>
    );

}




