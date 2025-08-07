'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import styles from './WaveformVisualizer.module.css';

const WaveformVisualizer = ({ 
  audioRef, 
  currentTime = 0, 
  duration = 0, 
  isPlaying = false,
  onSeek,
  className = '',
  height = 80,
  barWidth = 3,
  barGap = 1
}) => {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const animationRef = useRef(null);
  
  const [audioBuffer, setAudioBuffer] = useState(null);
  const [waveformData, setWaveformData] = useState([]);
  const [canvasWidth, setCanvasWidth] = useState(600);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // Resize observer for responsive canvas
  useEffect(() => {
    const resizeObserver = new ResizeObserver(entries => {
      for (let entry of entries) {
        setCanvasWidth(entry.contentRect.width);
      }
    });

    if (containerRef.current) {
      resizeObserver.observe(containerRef.current);
      setCanvasWidth(containerRef.current.clientWidth);
    }

    return () => resizeObserver.disconnect();
  }, []);

  // Analyze audio and generate waveform data
  const analyzeAudio = useCallback(async (audioElement) => {
    if (!audioElement || !audioElement.src || isAnalyzing) return;

    setIsAnalyzing(true);
    
    try {
      // Create audio context
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      
      // Fetch audio data
      const response = await fetch(audioElement.src);
      const arrayBuffer = await response.arrayBuffer();
      
      // Decode audio data
      const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
      setAudioBuffer(audioBuffer);
      
      // Generate waveform data
      const channelData = audioBuffer.getChannelData(0); // Use first channel
      const sampleRate = audioBuffer.sampleRate;
      const samplesPerBar = Math.floor(channelData.length / Math.floor(canvasWidth / (barWidth + barGap)));
      
      const waveform = [];
      for (let i = 0; i < Math.floor(canvasWidth / (barWidth + barGap)); i++) {
        const start = Math.floor(i * samplesPerBar);
        const end = Math.min(start + samplesPerBar, channelData.length);
        
        let sum = 0;
        let max = 0;
        for (let j = start; j < end; j++) {
          const sample = Math.abs(channelData[j]);
          sum += sample;
          max = Math.max(max, sample);
        }
        
        // Use RMS for smoother visualization
        const rms = Math.sqrt(sum / (end - start));
        waveform.push({
          rms: rms,
          peak: max,
          value: Math.max(rms * 2, max * 0.8) // Balanced visualization
        });
      }
      
      setWaveformData(waveform);
      audioContext.close();
    } catch (error) {
      console.error('Error analyzing audio:', error);
    } finally {
      setIsAnalyzing(false);
    }
  }, [canvasWidth, barWidth, barGap, isAnalyzing]);

  // Analyze audio when audio source changes
  useEffect(() => {
    if (audioRef?.current && audioRef.current.src) {
      analyzeAudio(audioRef.current);
    }
  }, [audioRef?.current?.src, analyzeAudio]);

  // Re-analyze when canvas width changes significantly
  useEffect(() => {
    if (audioRef?.current && audioRef.current.src && waveformData.length > 0) {
      const expectedBars = Math.floor(canvasWidth / (barWidth + barGap));
      if (Math.abs(waveformData.length - expectedBars) > 10) {
        analyzeAudio(audioRef.current);
      }
    }
  }, [canvasWidth, waveformData.length, barWidth, barGap, analyzeAudio, audioRef]);

  // Draw waveform
  const drawWaveform = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || waveformData.length === 0) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    // Clear canvas
    ctx.clearRect(0, 0, width, height);

    // Calculate progress
    const progress = duration > 0 ? currentTime / duration : 0;
    const progressPosition = progress * width;

    // Draw waveform bars
    waveformData.forEach((data, index) => {
      const x = index * (barWidth + barGap);
      const barHeight = Math.max(2, data.value * height * 0.8);
      const y = (height - barHeight) / 2;

      // Determine color based on playback progress
      const isPassed = x < progressPosition;
      const isActive = Math.abs(x - progressPosition) < barWidth + barGap;

      // Set gradient colors
      const gradient = ctx.createLinearGradient(0, y, 0, y + barHeight);
      
      if (isActive) {
        gradient.addColorStop(0, '#ff6b6b');
        gradient.addColorStop(1, '#ee5a52');
      } else if (isPassed) {
        gradient.addColorStop(0, '#4CAF50');
        gradient.addColorStop(1, '#45a049');
      } else {
        gradient.addColorStop(0, 'rgba(255, 255, 255, 0.6)');
        gradient.addColorStop(1, 'rgba(255, 255, 255, 0.3)');
      }

      ctx.fillStyle = gradient;
      ctx.fillRect(x, y, barWidth, barHeight);

      // Add highlight for active bar
      if (isActive) {
        ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.fillRect(x, y, barWidth, Math.max(barHeight * 0.3, 4));
      }
    });

    // Draw progress line
    if (progress > 0) {
      ctx.strokeStyle = '#ff6b6b';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(progressPosition, 0);
      ctx.lineTo(progressPosition, height);
      ctx.stroke();
    }

    // Draw time markers (every 30 seconds or so)
    if (duration > 30) {
      ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
      ctx.font = '10px Arial';
      ctx.textAlign = 'center';
      
      const interval = duration > 300 ? 60 : 30; // 1min for long tracks, 30s for shorter
      for (let time = interval; time < duration; time += interval) {
        const x = (time / duration) * width;
        ctx.fillText(`${Math.floor(time / 60)}:${String(Math.floor(time % 60)).padStart(2, '0')}`, x, height - 4);
        
        // Draw marker line
        ctx.fillStyle = 'rgba(255, 255, 255, 0.2)';
        ctx.fillRect(x - 0.5, 0, 1, height - 15);
        ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
      }
    }
  }, [waveformData, currentTime, duration, barWidth, barGap]);

  // Animation loop
  useEffect(() => {
    const animate = () => {
      drawWaveform();
      if (isPlaying) {
        animationRef.current = requestAnimationFrame(animate);
      }
    };

    if (isPlaying) {
      animationRef.current = requestAnimationFrame(animate);
    } else {
      drawWaveform();
    }

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isPlaying, drawWaveform]);

  // Redraw when data changes
  useEffect(() => {
    drawWaveform();
  }, [drawWaveform]);

  // Handle click to seek
  const handleCanvasClick = useCallback((event) => {
    if (!onSeek || !duration || waveformData.length === 0) return;

    const canvas = canvasRef.current;
    if (!canvas) return;

    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const progress = x / rect.width;
    const seekTime = progress * duration;
    
    onSeek(seekTime);
  }, [onSeek, duration, waveformData.length]);

  // Set canvas size
  useEffect(() => {
    const canvas = canvasRef.current;
    if (canvas) {
      canvas.width = canvasWidth;
      canvas.height = height;
    }
  }, [canvasWidth, height]);

  return (
    <div 
      ref={containerRef}
      className={`${styles.waveformContainer} ${className}`}
    >
      {isAnalyzing && (
        <div className={styles.analyzing}>
          <span>🌊 Analyzing audio...</span>
        </div>
      )}
      
      <canvas
        ref={canvasRef}
        className={styles.waveformCanvas}
        onClick={handleCanvasClick}
        style={{ 
          opacity: isAnalyzing ? 0.3 : 1,
          cursor: onSeek ? 'pointer' : 'default'
        }}
      />
      
      {waveformData.length === 0 && !isAnalyzing && (
        <div className={styles.placeholder}>
          <span>🎵 Waveform will appear here</span>
        </div>
      )}
    </div>
  );
};

export default WaveformVisualizer;