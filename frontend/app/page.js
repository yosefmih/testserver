'use client';

import { useState, useEffect, useRef } from 'react';
import styles from './page.module.css';
import { apiClient } from '../lib/api'; // Import the new API client
import AdvancedAudioPlayer from '../components/AdvancedAudioPlayer';

// Helper function to convert ArrayBuffer to Base64
function arrayBufferToBase64(buffer) {
  let binary = '';
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}

const AVAILABLE_EFFECTS = [
  { id: 'low_pass', name: 'Low-pass Filter' },
  { id: 'high_pass', name: 'High-pass Filter' },
  { id: 'reverb', name: 'Reverb' },
  { id: 'echo', name: 'Echo' },
  { id: 'pitch_shift', name: 'Pitch Shift' },
  { id: 'distortion', name: 'Distortion' },
];

export default function AudioProcessorPage() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedEffects, setSelectedEffects] = useState(['reverb', 'low_pass']); // Default effects
  const [jobId, setJobId] = useState('');
  const [jobStatus, setJobStatus] = useState('');
  const [jobError, setJobError] = useState('');
  const [processingResultUrl, setProcessingResultUrl] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [statusPollInterval, setStatusPollInterval] = useState(null);

  console.log('[page.js] NEXT_PUBLIC_TEST_VAR:', process.env.NEXT_PUBLIC_TEST_VAR);

  useEffect(() => {
    console.log('[page.js useEffect] NEXT_PUBLIC_TEST_VAR:', process.env.NEXT_PUBLIC_TEST_VAR);
    return () => {
      if (statusPollInterval) {
        clearInterval(statusPollInterval);
      }
    };
  }, [statusPollInterval]);

  const handleFileChange = (event) => {
    setSelectedFile(event.target.files[0]);
    setJobId('');
    setJobStatus('');
    setJobError('');
    setProcessingResultUrl('');
    if (statusPollInterval) {
      clearInterval(statusPollInterval);
      setStatusPollInterval(null);
    }
  };

  const handleEffectChange = (effectId) => {
    setSelectedEffects(prevEffects => 
      prevEffects.includes(effectId) 
        ? prevEffects.filter(e => e !== effectId) 
        : [...prevEffects, effectId]
    );
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!selectedFile) {
      alert('Please select an audio file first.');
      return;
    }
    if (selectedEffects.length === 0) {
      alert('Please select at least one effect to apply.');
      return;
    }
    setIsLoading(true);
    setJobStatus('Uploading...');
    setJobError('');
    setProcessingResultUrl('');

    try {
      const reader = new FileReader();
      reader.onload = async (e) => {
        const audioBuffer = e.target.result;
        const base64AudioData = arrayBufferToBase64(audioBuffer);
        const payload = {
          audio_data: base64AudioData,
          effects: selectedEffects,
        };

        try {
          // Use the apiClient for uploading
          const result = await apiClient.uploadAudio(payload);
          setJobId(result.job_id);
          setJobStatus(result.status || 'queued');
          setIsLoading(false);
          pollJobStatus(result.job_id);
        } catch (uploadError) {
          setJobError(`Upload error: ${uploadError.message}`);
          setJobStatus('Error');
          setIsLoading(false);
        }
      };
      reader.onerror = () => {
        setJobError('Failed to read file.');
        setJobStatus('Error');
        setIsLoading(false);
      };
      reader.readAsArrayBuffer(selectedFile);
    } catch (error) {
      setJobError(`Submission error: ${error.message}`);
      setJobStatus('Error');
      setIsLoading(false);
    }
  };

  const pollJobStatus = (currentJobId) => {
    if (statusPollInterval) clearInterval(statusPollInterval);
    const intervalId = setInterval(async () => {
      try {
        // Use the apiClient for getting status
        const data = await apiClient.getJobStatus(currentJobId);
        setJobStatus(data.status);
        if (data.error) setJobError(data.error);
        if (data.status === 'completed') {
          // Use apiClient to construct the result URL
          setProcessingResultUrl(apiClient.getJobResultUrl(currentJobId));
          clearInterval(intervalId);
          setStatusPollInterval(null);
        } else if (data.status === 'failed') {
          clearInterval(intervalId);
          setStatusPollInterval(null);
        }
      } catch (error) {
         // apiClient.getJobStatus will throw an error with a message for non-OK responses
        setJobError(error.message || 'Polling error. Stopping updates.');
        setJobStatus('Error');
        clearInterval(intervalId);
        setStatusPollInterval(null);
      }
    }, 3000);
    setStatusPollInterval(intervalId);
  };

  const manuallyCheckStatus = () => {
    if (jobId) pollJobStatus(jobId);
    else alert("No Job ID to check status for.");
  };

  // Audio error handler for advanced player
  const onAudioError = (event) => {
    console.error('Audio player error:', event);
    setJobError('Audio playback failed');
  };

  return (
    <div className={styles.container}>
      <main className={styles.main}>
        <h1 className={styles.title}>Audio Processing Service</h1>

        <section className={styles.formSection}>
          <h2>1. Upload Audio & Select Effects</h2>
          <form onSubmit={handleSubmit}>
            <div className={styles.fileInputContainer}>
              <label htmlFor="audioFile" className={styles.fileLabel}>Choose an audio file (WAV preferred):</label>
              <input
                type="file"
                id="audioFile"
                onChange={handleFileChange}
                accept="audio/*"
                className={styles.fileInput}
              />
            </div>

            <div className={styles.effectsSelectionContainer}>
              <label className={styles.effectsLabel}>Select effects to apply:</label>
              <div className={styles.effectsCheckboxes}>
                {AVAILABLE_EFFECTS.map(effect => (
                  <div key={effect.id} className={styles.effectCheckboxItem}>
                    <input 
                      type="checkbox" 
                      id={`effect-${effect.id}`} 
                      value={effect.id} 
                      checked={selectedEffects.includes(effect.id)}
                      onChange={() => handleEffectChange(effect.id)}
                      className={styles.effectCheckbox}
                    />
                    <label htmlFor={`effect-${effect.id}`} className={styles.effectCheckboxLabel}>
                      {effect.name}
                    </label>
                  </div>
                ))}
              </div>
            </div>

            <button 
              type="submit" 
              disabled={isLoading || !selectedFile || selectedEffects.length === 0} 
              className={styles.submitButton}
            >
              {isLoading && jobStatus === 'Uploading...' ? 'Uploading...' : (isLoading ? 'Processing...' : 'Upload and Process')}
            </button>
          </form>
        </section>

        {jobId && (
          <section className={styles.statusSection}>
            <h2>2. Job Status</h2>
            <div className={styles.statusInfo}>
              <p><strong>Job ID:</strong> {jobId}</p>
              <p>
                <strong>Status:</strong> 
                <span className={`${styles.statusText} ${styles[jobStatus?.toLowerCase()] || styles.unknown}`}>
                  {jobStatus || 'N/A'}
                </span>
              </p>
              {jobError && <p className={styles.errorText}>{jobError}</p>}
              {jobStatus && !['completed', 'failed', 'Error'].includes(jobStatus) && (
                 <button onClick={manuallyCheckStatus} disabled={isLoading} className={styles.checkStatusButton}>
                    Refresh Status
                 </button>
              )}
            </div>
          </section>
        )}

        {processingResultUrl && jobStatus === 'completed' && (
          <section className={`${styles.resultSectionWrapper} ${styles.resultDisplay}`}> {/* Combined for simplicity */}
            <h2>3. Job Result</h2>
            <h3>Processing Complete!</h3>
            <a href={processingResultUrl} download={`processed_${jobId}.wav`} className={styles.downloadLink}>
              Download Processed Audio
            </a>
            <AdvancedAudioPlayer 
              src={processingResultUrl}
              title={`Processed Audio - ${jobId}`}
              onError={onAudioError}
            />
          </section>
        )}
      </main>
    </div>
  );
} 