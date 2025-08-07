#ifndef AUDIO_TYPES_H
#define AUDIO_TYPES_H

#include <stdint.h>
#include <stddef.h>

// Audio sample types
typedef int16_t sample_t;
typedef float float_sample_t;

// Audio buffer structure
typedef struct {
    sample_t *data;
    size_t length;
    size_t capacity;
    uint32_t sample_rate;
    uint16_t channels;
} audio_buffer_t;

// Effect parameters
typedef struct {
    float cutoff_freq;
    int order;
} filter_params_t;

typedef struct {
    float room_size;
    float damping;
    float wet_level;
} reverb_params_t;

typedef struct {
    float delay_ms;
    float decay;
    int num_echoes;
} echo_params_t;

typedef struct {
    float semitones;
} pitch_params_t;

typedef struct {
    float gain;
    float threshold;
} distortion_params_t;

// Effect types
typedef enum {
    EFFECT_LOW_PASS = 1,
    EFFECT_HIGH_PASS = 2,
    EFFECT_REVERB = 4,
    EFFECT_ECHO = 8,
    EFFECT_PITCH_SHIFT = 16,
    EFFECT_DISTORTION = 32
} effect_type_t;

// Job structure
typedef struct {
    char *job_id;
    audio_buffer_t *input_buffer;
    audio_buffer_t *output_buffer;
    uint32_t effects_mask;
    filter_params_t low_pass;
    filter_params_t high_pass;
    reverb_params_t reverb;
    echo_params_t echo;
    pitch_params_t pitch;
    distortion_params_t distortion;
} audio_job_t;

#endif // AUDIO_TYPES_H