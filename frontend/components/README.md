# Advanced Audio Player Components

## Overview

This directory contains professional audio player components with advanced features for the audio processing service frontend.

## Components

### AdvancedAudioPlayer.js
A full-featured audio player with:
- **Playback Controls**: Play/pause, skip forward/backward (10s, 30s)
- **Volume Control**: Volume slider, mute/unmute
- **Speed Control**: Variable playback speed (0.25x to 3x)
- **Seek Control**: Click-to-seek progress bar with buffering visualization
- **Loop Mode**: Toggle loop playback
- **Keyboard Shortcuts**: Full keyboard navigation
- **Responsive Design**: Works on desktop and mobile
- **Real-time Waveform**: Visual audio waveform with click-to-seek

### WaveformVisualizer.js
An audio waveform visualization component featuring:
- **Real-time Analysis**: Analyzes audio data to generate waveform
- **Interactive Seeking**: Click on waveform to seek to specific time
- **Progress Visualization**: Shows current playback position
- **Time Markers**: Displays time markers for longer tracks
- **Responsive Canvas**: Automatically adjusts to container width
- **Performance Optimized**: Uses requestAnimationFrame for smooth animation

## Features

### 🎵 Playback Features
- Professional-grade audio controls
- Variable speed playback (0.25x - 3x)
- Loop mode for repeated listening
- Precise seeking with visual feedback
- Buffer progress indication
- Auto-pause/resume handling

### 🎨 Visual Features
- Beautiful gradient design with glassmorphism effects
- Real-time waveform visualization
- Smooth animations and transitions
- Progress indicators with shimmer effects
- Responsive design for all screen sizes
- Dark theme optimized

### ⌨️ Keyboard Shortcuts
- **Space**: Play/Pause
- **← / →**: Skip 10 seconds backward/forward
- **↑ / ↓**: Volume up/down
- **M**: Mute/Unmute
- **L**: Toggle loop mode
- **H**: Show/hide keyboard shortcuts help

### 📱 Mobile Support
- Touch-friendly controls
- Responsive layout
- Optimized button sizes
- Swipe-friendly progress bars

## Usage

```javascript
import AdvancedAudioPlayer from './components/AdvancedAudioPlayer';

// Basic usage
<AdvancedAudioPlayer 
  src="path/to/audio/file.wav"
  title="My Audio Track"
  onError={(error) => console.error(error)}
/>
```

## Props

### AdvancedAudioPlayer
- `src` (string, required): Audio file URL
- `title` (string): Display title for the track
- `onError` (function): Error callback handler

### WaveformVisualizer  
- `audioRef` (ref): Reference to HTML audio element
- `currentTime` (number): Current playback time in seconds
- `duration` (number): Total duration in seconds
- `isPlaying` (boolean): Playback state
- `onSeek` (function): Seek callback function
- `height` (number): Canvas height in pixels
- `barWidth` (number): Width of each waveform bar
- `barGap` (number): Gap between waveform bars

## Technical Details

### Audio Analysis
- Uses Web Audio API for real-time audio analysis
- Generates waveform data using RMS and peak detection
- Optimizes bar count based on container width
- Supports all HTML5 audio formats

### Performance
- Canvas-based rendering for smooth animations
- Debounced resize handling
- Efficient memory management
- Optimized for 60fps animations

### Browser Compatibility
- Modern browsers with Web Audio API support
- Fallback graceful degradation
- Mobile Safari compatible
- Chrome, Firefox, Edge tested

## Styling

The components use CSS Modules for styling. Key features:
- Glassmorphism design with backdrop filters
- Smooth CSS transitions and animations
- Responsive grid layouts
- Mobile-first design approach
- High contrast accessibility support

## Integration

The advanced audio player is integrated into the main audio processing page and automatically replaces the basic HTML5 audio element when audio processing is complete.

The player provides a professional experience for users to:
1. Preview their processed audio
2. Compare with original audio
3. Fine-tune their listening experience
4. Download processed results

Perfect for audio engineers, content creators, and music enthusiasts who need precise audio control and visualization.