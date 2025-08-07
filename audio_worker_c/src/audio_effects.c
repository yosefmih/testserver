#define _USE_MATH_DEFINES
#include "audio_processing.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// Simple IIR filter implementation (Butterworth)
typedef struct {
    float b[3];  // feedforward coefficients
    float a[3];  // feedback coefficients
    float x[3];  // input history
    float y[3];  // output history
} biquad_filter_t;

static void biquad_init(biquad_filter_t *filter) {
    memset(filter->x, 0, sizeof(filter->x));
    memset(filter->y, 0, sizeof(filter->y));
}

static float biquad_process(biquad_filter_t *filter, float input) {
    // Shift history
    filter->x[2] = filter->x[1];
    filter->x[1] = filter->x[0];
    filter->x[0] = input;
    
    filter->y[2] = filter->y[1];
    filter->y[1] = filter->y[0];
    
    // Calculate output
    filter->y[0] = filter->b[0] * filter->x[0] + 
                   filter->b[1] * filter->x[1] + 
                   filter->b[2] * filter->x[2] - 
                   filter->a[1] * filter->y[1] - 
                   filter->a[2] * filter->y[2];
    
    return filter->y[0];
}

static void calculate_lowpass_coefficients(biquad_filter_t *filter, float freq, float sample_rate) {
    float omega = 2.0f * M_PI * freq / sample_rate;
    float sin_omega = sinf(omega);
    float cos_omega = cosf(omega);
    float alpha = sin_omega / (2.0f * 0.707f); // Q = 0.707 for Butterworth
    
    float a0 = 1.0f + alpha;
    filter->b[0] = (1.0f - cos_omega) / (2.0f * a0);
    filter->b[1] = (1.0f - cos_omega) / a0;
    filter->b[2] = (1.0f - cos_omega) / (2.0f * a0);
    filter->a[0] = 1.0f;
    filter->a[1] = (-2.0f * cos_omega) / a0;
    filter->a[2] = (1.0f - alpha) / a0;
}

static void calculate_highpass_coefficients(biquad_filter_t *filter, float freq, float sample_rate) {
    float omega = 2.0f * M_PI * freq / sample_rate;
    float sin_omega = sinf(omega);
    float cos_omega = cosf(omega);
    float alpha = sin_omega / (2.0f * 0.707f); // Q = 0.707 for Butterworth
    
    float a0 = 1.0f + alpha;
    filter->b[0] = (1.0f + cos_omega) / (2.0f * a0);
    filter->b[1] = -(1.0f + cos_omega) / a0;
    filter->b[2] = (1.0f + cos_omega) / (2.0f * a0);
    filter->a[0] = 1.0f;
    filter->a[1] = (-2.0f * cos_omega) / a0;
    filter->a[2] = (1.0f - alpha) / a0;
}

int apply_low_pass_filter(audio_buffer_t *buffer, const filter_params_t *params) {
    if (!buffer || !params || buffer->length == 0) return -1;
    
    // Allocate temporary float buffer
    float_sample_t *float_samples = malloc(buffer->length * sizeof(float_sample_t));
    if (!float_samples) return -1;
    
    // Convert to float
    samples_to_float(buffer->data, float_samples, buffer->length);
    
    // Create and initialize filter
    biquad_filter_t filter;
    calculate_lowpass_coefficients(&filter, params->cutoff_freq, (float)buffer->sample_rate);
    biquad_init(&filter);
    
    // Process samples in-place
    for (size_t i = 0; i < buffer->length; i++) {
        float_samples[i] = biquad_process(&filter, float_samples[i]);
    }
    
    // Convert back to int16
    samples_from_float(float_samples, buffer->data, buffer->length);
    
    free(float_samples);
    return 0;
}

int apply_high_pass_filter(audio_buffer_t *buffer, const filter_params_t *params) {
    if (!buffer || !params || buffer->length == 0) return -1;
    
    // Allocate temporary float buffer
    float_sample_t *float_samples = malloc(buffer->length * sizeof(float_sample_t));
    if (!float_samples) return -1;
    
    // Convert to float
    samples_to_float(buffer->data, float_samples, buffer->length);
    
    // Create and initialize filter
    biquad_filter_t filter;
    calculate_highpass_coefficients(&filter, params->cutoff_freq, (float)buffer->sample_rate);
    biquad_init(&filter);
    
    // Process samples in-place
    for (size_t i = 0; i < buffer->length; i++) {
        float_samples[i] = biquad_process(&filter, float_samples[i]);
    }
    
    // Convert back to int16
    samples_from_float(float_samples, buffer->data, buffer->length);
    
    free(float_samples);
    return 0;
}

int apply_reverb(audio_buffer_t *buffer, const reverb_params_t *params) {
    if (!buffer || !params || buffer->length == 0) return -1;
    
    // Simple reverb using comb filters and allpass filters
    size_t delay_samples = (size_t)(params->room_size * buffer->sample_rate * 0.1f); // Max 100ms delay
    if (delay_samples >= buffer->length) delay_samples = buffer->length / 4;
    
    // Allocate delay line
    float_sample_t *delay_line = calloc(delay_samples, sizeof(float_sample_t));
    if (!delay_line) return -1;
    
    // Allocate temporary float buffer
    float_sample_t *float_samples = malloc(buffer->length * sizeof(float_sample_t));
    if (!float_samples) {
        free(delay_line);
        return -1;
    }
    
    // Convert to float
    samples_to_float(buffer->data, float_samples, buffer->length);
    
    size_t delay_index = 0;
    float feedback = params->damping * 0.5f;
    
    // Process samples
    for (size_t i = 0; i < buffer->length; i++) {
        float delayed = delay_line[delay_index];
        float input_with_feedback = float_samples[i] + delayed * feedback;
        
        // Update delay line
        delay_line[delay_index] = input_with_feedback;
        delay_index = (delay_index + 1) % delay_samples;
        
        // Mix dry and wet signals
        float_samples[i] = float_samples[i] * (1.0f - params->wet_level) + 
                          delayed * params->wet_level;
    }
    
    // Convert back to int16
    samples_from_float(float_samples, buffer->data, buffer->length);
    
    free(float_samples);
    free(delay_line);
    return 0;
}

int apply_echo(audio_buffer_t *buffer, const echo_params_t *params) {
    if (!buffer || !params || buffer->length == 0) return -1;
    
    size_t delay_samples = (size_t)(params->delay_ms * buffer->sample_rate / 1000.0f);
    if (delay_samples >= buffer->length) return -1;
    
    // Allocate temporary buffer for echo
    sample_t *echo_buffer = calloc(buffer->length, sizeof(sample_t));
    if (!echo_buffer) return -1;
    
    // Generate echo
    for (int echo = 0; echo < params->num_echoes && echo < 5; echo++) {
        size_t current_delay = delay_samples * (echo + 1);
        if (current_delay >= buffer->length) break;
        
        float amplitude = powf(params->decay, echo + 1);
        
        for (size_t i = current_delay; i < buffer->length; i++) {
            float echo_sample = (float)buffer->data[i - current_delay] * amplitude;
            echo_buffer[i] += clamp_sample(echo_sample);
        }
    }
    
    // Mix original with echo
    for (size_t i = 0; i < buffer->length; i++) {
        float mixed = (float)buffer->data[i] + (float)echo_buffer[i] * 0.5f;
        buffer->data[i] = clamp_sample(mixed);
    }
    
    free(echo_buffer);
    return 0;
}

int apply_pitch_shift(audio_buffer_t *buffer, const pitch_params_t *params) {
    if (!buffer || !params || buffer->length == 0) return -1;
    
    float shift_factor = powf(2.0f, params->semitones / 12.0f);
    
    // Allocate temporary buffer
    sample_t *temp_buffer = malloc(buffer->length * sizeof(sample_t));
    if (!temp_buffer) return -1;
    
    // Simple pitch shift using linear interpolation
    for (size_t i = 0; i < buffer->length; i++) {
        float src_pos = (float)i / shift_factor;
        size_t src_index = (size_t)src_pos;
        float frac = src_pos - src_index;
        
        if (src_index + 1 < buffer->length) {
            float sample1 = (float)buffer->data[src_index];
            float sample2 = (float)buffer->data[src_index + 1];
            temp_buffer[i] = clamp_sample(lerp(sample1, sample2, frac));
        } else if (src_index < buffer->length) {
            temp_buffer[i] = buffer->data[src_index];
        } else {
            temp_buffer[i] = 0;
        }
    }
    
    // Copy back to original buffer
    memcpy(buffer->data, temp_buffer, buffer->length * sizeof(sample_t));
    
    free(temp_buffer);
    return 0;
}

int apply_distortion(audio_buffer_t *buffer, const distortion_params_t *params) {
    if (!buffer || !params || buffer->length == 0) return -1;
    
    // Apply soft clipping distortion
    for (size_t i = 0; i < buffer->length; i++) {
        float sample = (float)buffer->data[i] / 32768.0f;
        
        // Apply gain
        sample *= params->gain;
        
        // Soft clipping using tanh
        sample = tanhf(sample * params->threshold) / params->threshold;
        
        buffer->data[i] = clamp_sample(sample * 32767.0f);
    }
    
    return 0;
}

int normalize_audio(audio_buffer_t *buffer) {
    if (!buffer || buffer->length == 0) return -1;
    
    // Find maximum absolute value
    int32_t max_val = 0;
    for (size_t i = 0; i < buffer->length; i++) {
        int32_t abs_val = abs(buffer->data[i]);
        if (abs_val > max_val) {
            max_val = abs_val;
        }
    }
    
    if (max_val == 0) return 0; // Silent audio
    
    // Calculate scale factor (leave some headroom)
    float scale = (32767.0f * 0.95f) / (float)max_val;
    
    if (scale < 1.0f) {
        // Only scale down if needed
        for (size_t i = 0; i < buffer->length; i++) {
            buffer->data[i] = clamp_sample((float)buffer->data[i] * scale);
        }
    }
    
    return 0;
}