'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import styles from './AdvancedAudioPlayer.module.css';
import WaveformVisualizer from './WaveformVisualizer';

const AdvancedAudioPlayer = ({ src, title = "Audio Track", onError }) => {
  // State management
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [isMuted, setIsMuted] = useState(false);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [buffered, setBuffered] = useState([]);
  const [showControls, setShowControls] = useState(true);
  const [isLooping, setIsLooping] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);

  // Refs
  const audioRef = useRef(null);
  const progressBarRef = useRef(null);
  const volumeBarRef = useRef(null);
  const canvasRef = useRef(null);

  // Audio event handlers
  const handleLoadedMetadata = useCallback(() => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration);
      setIsLoading(false);
      setError(null);
    }
  }, []);

  const handleTimeUpdate = useCallback(() => {
    if (audioRef.current && !isDragging) {
      setCurrentTime(audioRef.current.currentTime);
      
      // Update buffered ranges
      const bufferedRanges = [];
      const audio = audioRef.current;
      for (let i = 0; i < audio.buffered.length; i++) {
        bufferedRanges.push({
          start: audio.buffered.start(i),
          end: audio.buffered.end(i)
        });
      }
      setBuffered(bufferedRanges);
    }
  }, [isDragging]);

  const handleLoadStart = useCallback(() => {
    setIsLoading(true);
    setError(null);
  }, []);

  const handleCanPlay = useCallback(() => {
    setIsLoading(false);
  }, []);

  const handleError = useCallback((e) => {
    setError('Failed to load audio file');
    setIsLoading(false);
    if (onError) onError(e);
  }, [onError]);

  const handleEnded = useCallback(() => {
    setIsPlaying(false);
    setCurrentTime(0);
  }, []);

  // Playback controls
  const togglePlayPause = useCallback(() => {
    if (!audioRef.current || isLoading) return;
    
    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      audioRef.current.play().catch(err => {
        setError('Failed to play audio');
        console.error('Play error:', err);
      });
      setIsPlaying(true);
    }
  }, [isPlaying, isLoading]);

  const seek = useCallback((time) => {
    if (!audioRef.current || !duration) return;
    const newTime = Math.max(0, Math.min(time, duration));
    console.log(`Seeking to: ${newTime}s`);
    try {
      audioRef.current.currentTime = newTime;
      setCurrentTime(newTime);
    } catch (error) {
      console.error('Seek error:', error);
    }
  }, [duration]);

  const skip = useCallback((seconds) => {
    if (!audioRef.current || !duration) return;
    const newTime = Math.max(0, Math.min(currentTime + seconds, duration));
    console.log(`Skipping ${seconds}s: ${currentTime} -> ${newTime}`);
    audioRef.current.currentTime = newTime;
    setCurrentTime(newTime);
  }, [currentTime, duration]);

  const handleVolumeChange = useCallback((newVolume) => {
    const vol = Math.max(0, Math.min(1, newVolume));
    setVolume(vol);
    if (audioRef.current) {
      audioRef.current.volume = vol;
      if (vol === 0 && !isMuted) {
        setIsMuted(true);
      } else if (vol > 0 && isMuted) {
        setIsMuted(false);
      }
    }
  }, [isMuted]);

  const toggleMute = useCallback(() => {
    if (!audioRef.current) return;
    
    if (isMuted) {
      setIsMuted(false);
      audioRef.current.volume = volume;
    } else {
      setIsMuted(true);
      audioRef.current.volume = 0;
    }
  }, [isMuted, volume]);

  const changePlaybackRate = useCallback((rate) => {
    if (!audioRef.current) return;
    const newRate = Math.max(0.25, Math.min(3, rate));
    setPlaybackRate(newRate);
    audioRef.current.playbackRate = newRate;
  }, []);

  const toggleLoop = useCallback(() => {
    if (!audioRef.current) return;
    const newLooping = !isLooping;
    setIsLooping(newLooping);
    audioRef.current.loop = newLooping;
  }, [isLooping]);

  // Progress bar handling
  const handleProgressClick = useCallback((e) => {
    if (!progressBarRef.current || !duration) return;
    
    const rect = progressBarRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const progress = clickX / rect.width;
    const newTime = progress * duration;
    seek(newTime);
  }, [duration, seek]);

  const handleProgressDrag = useCallback((e) => {
    if (!isDragging || !progressBarRef.current || !duration) return;
    
    const rect = progressBarRef.current.getBoundingClientRect();
    const dragX = e.clientX - rect.left;
    const progress = Math.max(0, Math.min(1, dragX / rect.width));
    const newTime = progress * duration;
    setCurrentTime(newTime);
  }, [isDragging, duration]);

  const handleProgressMouseDown = useCallback((e) => {
    setIsDragging(true);
    handleProgressClick(e);
  }, [handleProgressClick]);

  const handleProgressMouseUp = useCallback(() => {
    if (isDragging) {
      seek(currentTime);
      setIsDragging(false);
    }
  }, [isDragging, currentTime, seek]);

  // Volume bar handling
  const handleVolumeClick = useCallback((e) => {
    if (!volumeBarRef.current) return;
    
    const rect = volumeBarRef.current.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const newVolume = clickX / rect.width;
    handleVolumeChange(newVolume);
  }, [handleVolumeChange]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
      
      switch (e.code) {
        case 'Space':
          e.preventDefault();
          togglePlayPause();
          break;
        case 'ArrowLeft':
          e.preventDefault();
          skip(-10);
          break;
        case 'ArrowRight':
          e.preventDefault();
          skip(10);
          break;
        case 'ArrowUp':
          e.preventDefault();
          handleVolumeChange(volume + 0.1);
          break;
        case 'ArrowDown':
          e.preventDefault();
          handleVolumeChange(volume - 0.1);
          break;
        case 'KeyM':
          e.preventDefault();
          toggleMute();
          break;
        case 'KeyL':
          e.preventDefault();
          toggleLoop();
          break;
        case 'KeyH':
          e.preventDefault();
          setShowShortcuts(!showShortcuts);
          break;
        default:
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [togglePlayPause, skip, handleVolumeChange, volume, toggleMute, toggleLoop, showShortcuts]);

  // Mouse event cleanup
  useEffect(() => {
    if (isDragging) {
      const handleMouseMove = (e) => handleProgressDrag(e);
      const handleMouseUp = () => handleProgressMouseUp();
      
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [isDragging, handleProgressDrag, handleProgressMouseUp]);

  // Utility functions
  const formatTime = (time) => {
    if (!time || !isFinite(time)) return '0:00';
    const minutes = Math.floor(time / 60);
    const seconds = Math.floor(time % 60);
    return `${minutes}:${seconds.toString().padStart(2, '0')}`;
  };

  const getProgressPercentage = () => {
    if (!duration) return 0;
    return (currentTime / duration) * 100;
  };

  const getVolumePercentage = () => {
    return isMuted ? 0 : volume * 100;
  };

  if (error) {
    return (
      <div className={styles.player}>
        <div className={styles.error}>
          ❌ {error}
        </div>
      </div>
    );
  }

  return (
    <div className={`${styles.player} ${!showControls ? styles.minimal : ''}`}>
      {/* Hidden audio element */}
      <audio
        ref={audioRef}
        src={src}
        onLoadedMetadata={handleLoadedMetadata}
        onTimeUpdate={handleTimeUpdate}
        onLoadStart={handleLoadStart}
        onCanPlay={handleCanPlay}
        onError={handleError}
        onEnded={handleEnded}
        preload="metadata"
      />

      {/* Player Header */}
      <div className={styles.header}>
        <div className={styles.trackInfo}>
          <span className={styles.trackTitle}>{title}</span>
          {isLoading && <span className={styles.loading}>Loading...</span>}
        </div>
        <button 
          className={styles.toggleControls}
          onClick={() => setShowControls(!showControls)}
          title="Toggle controls"
        >
          {showControls ? '⬇️' : '⬆️'}
        </button>
      </div>

      {/* Progress Bar */}
      <div className={styles.progressContainer}>
        <span className={styles.timeDisplay}>{formatTime(currentTime)}</span>
        <div 
          className={styles.progressBar}
          ref={progressBarRef}
          onClick={handleProgressClick}
          onMouseDown={handleProgressMouseDown}
        >
          <div className={styles.progressTrack}>
            {/* Buffered ranges */}
            {buffered.map((range, index) => (
              <div
                key={index}
                className={styles.buffered}
                style={{
                  left: `${(range.start / duration) * 100}%`,
                  width: `${((range.end - range.start) / duration) * 100}%`
                }}
              />
            ))}
            {/* Current progress */}
            <div 
              className={styles.progress}
              style={{ width: `${getProgressPercentage()}%` }}
            />
          </div>
          <div 
            className={styles.progressHandle}
            style={{ left: `${getProgressPercentage()}%` }}
          />
        </div>
        <span className={styles.timeDisplay}>{formatTime(duration)}</span>
      </div>

      {/* Waveform Visualizer */}
      {showControls && (
        <WaveformVisualizer
          audioRef={audioRef}
          currentTime={currentTime}
          duration={duration}
          isPlaying={isPlaying}
          onSeek={seek}
          height={60}
          className={styles.waveform}
        />
      )}

      {/* Main Controls */}
      {showControls && (
        <div className={styles.controls}>
          <div className={styles.playbackControls}>
            <button 
              className={styles.skipButton}
              onClick={() => skip(-30)}
              title="Skip back 30s"
            >
              ⏪ 30s
            </button>
            <button 
              className={styles.skipButton}
              onClick={() => skip(-10)}
              title="Skip back 10s"
            >
              ⏮️ 10s
            </button>
            <button 
              className={`${styles.playButton} ${isPlaying ? styles.playing : ''}`}
              onClick={togglePlayPause}
              disabled={isLoading}
              title={isPlaying ? 'Pause' : 'Play'}
            >
              {isLoading ? '⏳' : (isPlaying ? '⏸️' : '▶️')}
            </button>
            <button 
              className={styles.skipButton}
              onClick={() => skip(10)}
              title="Skip forward 10s"
            >
              10s ⏭️
            </button>
            <button 
              className={styles.skipButton}
              onClick={() => skip(30)}
              title="Skip forward 30s"
            >
              30s ⏩
            </button>
            <button 
              className={`${styles.loopButton} ${isLooping ? styles.active : ''}`}
              onClick={toggleLoop}
              title="Toggle loop mode"
            >
              🔁
            </button>
          </div>

          <div className={styles.volumeControls}>
            <button 
              className={styles.muteButton}
              onClick={toggleMute}
              title={isMuted ? 'Unmute' : 'Mute'}
            >
              {isMuted ? '🔇' : (volume > 0.5 ? '🔊' : volume > 0 ? '🔉' : '🔈')}
            </button>
            <div 
              className={styles.volumeBar}
              ref={volumeBarRef}
              onClick={handleVolumeClick}
            >
              <div className={styles.volumeTrack}>
                <div 
                  className={styles.volumeProgress}
                  style={{ width: `${getVolumePercentage()}%` }}
                />
              </div>
            </div>
            <span className={styles.volumeDisplay}>
              {Math.round(getVolumePercentage())}%
            </span>
          </div>

          <div className={styles.speedControls}>
            <label className={styles.speedLabel}>Speed:</label>
            <select 
              className={styles.speedSelect}
              value={playbackRate}
              onChange={(e) => changePlaybackRate(parseFloat(e.target.value))}
            >
              <option value={0.25}>0.25x</option>
              <option value={0.5}>0.5x</option>
              <option value={0.75}>0.75x</option>
              <option value={1}>1x</option>
              <option value={1.25}>1.25x</option>
              <option value={1.5}>1.5x</option>
              <option value={1.75}>1.75x</option>
              <option value={2}>2x</option>
              <option value={3}>3x</option>
            </select>
          </div>
        </div>
      )}

      {/* Keyboard Shortcuts Help */}
      <div className={styles.shortcuts}>
        <button
          className={styles.shortcutsToggle}
          onClick={() => setShowShortcuts(!showShortcuts)}
        >
          ⌨️ {showShortcuts ? 'Hide' : 'Show'} Keyboard Shortcuts
        </button>
        
        {showShortcuts && (
          <div className={styles.shortcutsList}>
            <div className={styles.shortcutGroup}>
              <strong>Playback</strong>
              <span>Space: Play/Pause</span>
              <span>L: Toggle Loop</span>
            </div>
            <div className={styles.shortcutGroup}>
              <strong>Navigation</strong>
              <span>← →: Skip 10s</span>
            </div>
            <div className={styles.shortcutGroup}>
              <strong>Audio</strong>
              <span>↑ ↓: Volume</span>
              <span>M: Mute/Unmute</span>
            </div>
            <div className={styles.shortcutGroup}>
              <strong>Interface</strong>
              <span>H: Toggle shortcuts</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AdvancedAudioPlayer;