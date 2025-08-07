#ifndef WAV_WRITER_H
#define WAV_WRITER_H

#include <stdint.h>
#include <stddef.h>

// WAV file format structures
typedef struct {
    char chunk_id[4];       // "RIFF"
    uint32_t chunk_size;    // File size - 8
    char format[4];         // "WAVE"
} wav_header_t;

typedef struct {
    char subchunk1_id[4];   // "fmt "
    uint32_t subchunk1_size; // 16 for PCM
    uint16_t audio_format;   // 1 for PCM
    uint16_t num_channels;   // 1 for mono, 2 for stereo
    uint32_t sample_rate;    // Sample rate (e.g., 44100)
    uint32_t byte_rate;      // SampleRate * NumChannels * BitsPerSample/8
    uint16_t block_align;    // NumChannels * BitsPerSample/8
    uint16_t bits_per_sample; // 16 for 16-bit PCM
} wav_fmt_chunk_t;

typedef struct {
    char subchunk2_id[4];    // "data"
    uint32_t subchunk2_size; // NumSamples * NumChannels * BitsPerSample/8
} wav_data_chunk_t;

/**
 * Create WAV file data from PCM samples
 * @param pcm_data Pointer to 16-bit PCM samples
 * @param sample_count Number of samples
 * @param sample_rate Sample rate (e.g., 44100)
 * @param num_channels Number of channels (1 for mono, 2 for stereo)
 * @param wav_data_out Pointer to store allocated WAV data (caller must free)
 * @param wav_size_out Pointer to store WAV data size
 * @return 0 on success, -1 on error
 */
int create_wav_file(const int16_t *pcm_data, size_t sample_count, 
                   uint32_t sample_rate, uint16_t num_channels,
                   uint8_t **wav_data_out, size_t *wav_size_out);

#endif // WAV_WRITER_H