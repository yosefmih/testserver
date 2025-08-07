#include "wav_writer.h"
#include <stdlib.h>
#include <string.h>

int create_wav_file(const int16_t *pcm_data, size_t sample_count, 
                   uint32_t sample_rate, uint16_t num_channels,
                   uint8_t **wav_data_out, size_t *wav_size_out) {
    
    if (!pcm_data || !wav_data_out || !wav_size_out || sample_count == 0) {
        return -1;
    }
    
    // Calculate sizes
    size_t pcm_data_size = sample_count * num_channels * sizeof(int16_t);
    size_t wav_file_size = sizeof(wav_header_t) + sizeof(wav_fmt_chunk_t) + 
                          sizeof(wav_data_chunk_t) + pcm_data_size;
    
    // Allocate memory for WAV file
    uint8_t *wav_data = malloc(wav_file_size);
    if (!wav_data) {
        return -1;
    }
    
    uint8_t *ptr = wav_data;
    
    // WAV header
    wav_header_t header = {0};
    memcpy(header.chunk_id, "RIFF", 4);
    header.chunk_size = (uint32_t)(wav_file_size - 8);
    memcpy(header.format, "WAVE", 4);
    memcpy(ptr, &header, sizeof(header));
    ptr += sizeof(header);
    
    // Format chunk
    wav_fmt_chunk_t fmt_chunk = {0};
    memcpy(fmt_chunk.subchunk1_id, "fmt ", 4);
    fmt_chunk.subchunk1_size = 16; // PCM
    fmt_chunk.audio_format = 1;    // PCM
    fmt_chunk.num_channels = num_channels;
    fmt_chunk.sample_rate = sample_rate;
    fmt_chunk.bits_per_sample = 16;
    fmt_chunk.byte_rate = sample_rate * num_channels * (fmt_chunk.bits_per_sample / 8);
    fmt_chunk.block_align = num_channels * (fmt_chunk.bits_per_sample / 8);
    memcpy(ptr, &fmt_chunk, sizeof(fmt_chunk));
    ptr += sizeof(fmt_chunk);
    
    // Data chunk header
    wav_data_chunk_t data_chunk = {0};
    memcpy(data_chunk.subchunk2_id, "data", 4);
    data_chunk.subchunk2_size = (uint32_t)pcm_data_size;
    memcpy(ptr, &data_chunk, sizeof(data_chunk));
    ptr += sizeof(data_chunk);
    
    // PCM data
    memcpy(ptr, pcm_data, pcm_data_size);
    
    *wav_data_out = wav_data;
    *wav_size_out = wav_file_size;
    
    return 0;
}