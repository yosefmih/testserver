#ifndef AUDIO_PROCESSING_H
#define AUDIO_PROCESSING_H

#include "audio_types.h"

// Audio buffer management
audio_buffer_t* audio_buffer_create(size_t capacity, uint32_t sample_rate, uint16_t channels);
void audio_buffer_destroy(audio_buffer_t *buffer);
int audio_buffer_resize(audio_buffer_t *buffer, size_t new_capacity);
int audio_buffer_copy(const audio_buffer_t *src, audio_buffer_t *dst);

// Audio format conversion
int samples_to_float(const sample_t *input, float_sample_t *output, size_t length);
int samples_from_float(const float_sample_t *input, sample_t *output, size_t length);

// Audio effects (all process in-place to minimize memory usage)
int apply_low_pass_filter(audio_buffer_t *buffer, const filter_params_t *params);
int apply_high_pass_filter(audio_buffer_t *buffer, const filter_params_t *params);
int apply_reverb(audio_buffer_t *buffer, const reverb_params_t *params);
int apply_echo(audio_buffer_t *buffer, const echo_params_t *params);
int apply_pitch_shift(audio_buffer_t *buffer, const pitch_params_t *params);
int apply_distortion(audio_buffer_t *buffer, const distortion_params_t *params);
int normalize_audio(audio_buffer_t *buffer);

// Job processing
int process_audio_job(audio_job_t *job);

// Utility functions
int16_t clamp_sample(float sample);
float lerp(float a, float b, float t);

#endif // AUDIO_PROCESSING_H