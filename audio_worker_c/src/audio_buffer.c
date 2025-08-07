#include "audio_processing.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

audio_buffer_t* audio_buffer_create(size_t capacity, uint32_t sample_rate, uint16_t channels) {
    audio_buffer_t *buffer = malloc(sizeof(audio_buffer_t));
    if (!buffer) return NULL;
    
    buffer->data = malloc(capacity * sizeof(sample_t));
    if (!buffer->data) {
        free(buffer);
        return NULL;
    }
    
    buffer->length = 0;
    buffer->capacity = capacity;
    buffer->sample_rate = sample_rate;
    buffer->channels = channels;
    
    // Initialize to silence
    memset(buffer->data, 0, capacity * sizeof(sample_t));
    
    return buffer;
}

void audio_buffer_destroy(audio_buffer_t *buffer) {
    if (buffer) {
        free(buffer->data);
        free(buffer);
    }
}

int audio_buffer_resize(audio_buffer_t *buffer, size_t new_capacity) {
    if (!buffer) return -1;
    
    sample_t *new_data = realloc(buffer->data, new_capacity * sizeof(sample_t));
    if (!new_data) return -1;
    
    buffer->data = new_data;
    
    // Initialize new memory to silence if capacity increased
    if (new_capacity > buffer->capacity) {
        memset(buffer->data + buffer->capacity, 0, 
               (new_capacity - buffer->capacity) * sizeof(sample_t));
    }
    
    buffer->capacity = new_capacity;
    if (buffer->length > new_capacity) {
        buffer->length = new_capacity;
    }
    
    return 0;
}

int audio_buffer_copy(const audio_buffer_t *src, audio_buffer_t *dst) {
    if (!src || !dst) return -1;
    
    // Resize destination if needed
    if (dst->capacity < src->length) {
        if (audio_buffer_resize(dst, src->length) != 0) {
            return -1;
        }
    }
    
    memcpy(dst->data, src->data, src->length * sizeof(sample_t));
    dst->length = src->length;
    dst->sample_rate = src->sample_rate;
    dst->channels = src->channels;
    
    return 0;
}

int samples_to_float(const sample_t *input, float_sample_t *output, size_t length) {
    if (!input || !output) return -1;
    
    const float scale = 1.0f / 32768.0f;
    for (size_t i = 0; i < length; i++) {
        output[i] = (float)input[i] * scale;
    }
    
    return 0;
}

int samples_from_float(const float_sample_t *input, sample_t *output, size_t length) {
    if (!input || !output) return -1;
    
    for (size_t i = 0; i < length; i++) {
        output[i] = clamp_sample(input[i] * 32767.0f);
    }
    
    return 0;
}

int16_t clamp_sample(float sample) {
    if (sample > 32767.0f) return 32767;
    if (sample < -32768.0f) return -32768;
    return (int16_t)roundf(sample);
}

float lerp(float a, float b, float t) {
    return a + t * (b - a);
}