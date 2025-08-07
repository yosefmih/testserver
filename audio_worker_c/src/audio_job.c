#define _GNU_SOURCE
#include "audio_processing.h"
#include "redis_client.h"
#include "base64.h"
#include "wav_writer.h"
#include <json-c/json.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <time.h>
#include <unistd.h>

static int parse_effects_from_json(const char *metadata_json, audio_job_t *job) {
    if (!metadata_json || !job) return -1;
    
    // Set default effects
    job->effects_mask = EFFECT_REVERB | EFFECT_LOW_PASS;
    
    // Set default parameters
    job->low_pass.cutoff_freq = 2000.0f;
    job->low_pass.order = 4;
    
    job->high_pass.cutoff_freq = 300.0f;
    job->high_pass.order = 4;
    
    job->reverb.room_size = 0.7f;
    job->reverb.damping = 0.5f;
    job->reverb.wet_level = 0.3f;
    
    job->echo.delay_ms = 300.0f;
    job->echo.decay = 0.5f;
    job->echo.num_echoes = 3;
    
    job->pitch.semitones = 3.0f;
    
    job->distortion.gain = 2.5f;
    job->distortion.threshold = 0.7f;
    
    // Parse JSON metadata
    json_object *root = json_tokener_parse(metadata_json);
    if (!root) return 0; // Use defaults if parsing fails
    
    json_object *effects_array;
    if (json_object_object_get_ex(root, "effects", &effects_array) && 
        json_object_is_type(effects_array, json_type_array)) {
        
        job->effects_mask = 0; // Clear defaults if effects are specified
        
        int array_len = json_object_array_length(effects_array);
        for (int i = 0; i < array_len; i++) {
            json_object *effect_obj = json_object_array_get_idx(effects_array, i);
            const char *effect_name = json_object_get_string(effect_obj);
            
            if (strcmp(effect_name, "low_pass") == 0) {
                job->effects_mask |= EFFECT_LOW_PASS;
            } else if (strcmp(effect_name, "high_pass") == 0) {
                job->effects_mask |= EFFECT_HIGH_PASS;
            } else if (strcmp(effect_name, "reverb") == 0) {
                job->effects_mask |= EFFECT_REVERB;
            } else if (strcmp(effect_name, "echo") == 0) {
                job->effects_mask |= EFFECT_ECHO;
            } else if (strcmp(effect_name, "pitch_shift") == 0) {
                job->effects_mask |= EFFECT_PITCH_SHIFT;
            } else if (strcmp(effect_name, "distortion") == 0) {
                job->effects_mask |= EFFECT_DISTORTION;
            }
        }
    }
    
    json_object_put(root);
    return 0;
}

static char* create_updated_metadata(const char *original_metadata, const char *job_id, 
                                   double processing_time_ms) {
    json_object *root;
    
    // Parse original metadata or create new object
    if (original_metadata) {
        root = json_tokener_parse(original_metadata);
        if (!root) {
            root = json_object_new_object();
        }
    } else {
        root = json_object_new_object();
    }
    
    // Add processing information
    time_t now = time(NULL);
    struct tm *utc_tm = gmtime(&now);
    char iso_time[32];
    strftime(iso_time, sizeof(iso_time), "%Y-%m-%dT%H:%M:%S", utc_tm);
    
    json_object_object_add(root, "processed_at", json_object_new_string(iso_time));
    json_object_object_add(root, "processing_time_ms", json_object_new_int((int)processing_time_ms));
    
    // Get hostname
    char hostname[256];
    if (gethostname(hostname, sizeof(hostname)) == 0) {
        json_object_object_add(root, "hostname", json_object_new_string(hostname));
    }
    
    // Convert back to string
    const char *json_string = json_object_to_json_string(root);
    char *result = strdup(json_string);
    
    json_object_put(root);
    return result;
}

int process_audio_job(audio_job_t *job) {
    if (!job || !job->input_buffer || !job->output_buffer) return -1;
    
    // Copy input to output buffer
    if (audio_buffer_copy(job->input_buffer, job->output_buffer) != 0) {
        return -1;
    }
    
    // Apply effects based on mask
    if (job->effects_mask & EFFECT_LOW_PASS) {
        if (apply_low_pass_filter(job->output_buffer, &job->low_pass) != 0) {
            return -1;
        }
    }
    
    if (job->effects_mask & EFFECT_HIGH_PASS) {
        if (apply_high_pass_filter(job->output_buffer, &job->high_pass) != 0) {
            return -1;
        }
    }
    
    if (job->effects_mask & EFFECT_REVERB) {
        if (apply_reverb(job->output_buffer, &job->reverb) != 0) {
            return -1;
        }
    }
    
    if (job->effects_mask & EFFECT_ECHO) {
        if (apply_echo(job->output_buffer, &job->echo) != 0) {
            return -1;
        }
    }
    
    if (job->effects_mask & EFFECT_PITCH_SHIFT) {
        if (apply_pitch_shift(job->output_buffer, &job->pitch) != 0) {
            return -1;
        }
    }
    
    if (job->effects_mask & EFFECT_DISTORTION) {
        if (apply_distortion(job->output_buffer, &job->distortion) != 0) {
            return -1;
        }
    }
    
    // Always normalize at the end
    normalize_audio(job->output_buffer);
    
    return 0;
}

int process_redis_job(redis_client_t *redis_client, const char *job_id) {
    if (!redis_client || !job_id) return -1;
    
    printf("Processing job: %s\n", job_id);
    
    clock_t start_time = clock();
    
    // Update status to processing
    if (redis_update_job_status(redis_client, job_id, "processing") != 0) {
        fprintf(stderr, "Failed to update job status to processing\n");
        return -1;
    }
    
    // Get input data
    char *input_data_b64 = NULL;
    if (redis_get_job_input(redis_client, job_id, &input_data_b64) != 0 || !input_data_b64) {
        fprintf(stderr, "Failed to get job input data\n");
        redis_store_job_error(redis_client, job_id, "Input data not found");
        redis_update_job_status(redis_client, job_id, "failed");
        return -1;
    }
    
    // Get metadata
    char *metadata_json = NULL;
    redis_get_job_metadata(redis_client, job_id, &metadata_json);
    
    // Decode base64 input data
    size_t decoded_len;
    size_t max_decoded_len = base64_decoded_size(input_data_b64);
    unsigned char *decoded_data = malloc(max_decoded_len);
    if (!decoded_data) {
        fprintf(stderr, "Failed to allocate memory for decoded data\n");
        free(input_data_b64);
        free(metadata_json);
        redis_store_job_error(redis_client, job_id, "Memory allocation failed");
        redis_update_job_status(redis_client, job_id, "failed");
        return -1;
    }
    
    if (base64_decode(input_data_b64, decoded_data, &decoded_len) != 0) {
        fprintf(stderr, "Failed to decode base64 input data\n");
        free(input_data_b64);
        free(metadata_json);
        free(decoded_data);
        redis_store_job_error(redis_client, job_id, "Failed to decode input data");
        redis_update_job_status(redis_client, job_id, "failed");
        return -1;
    }
    
    // Create audio buffers
    size_t sample_count = decoded_len / sizeof(sample_t);
    audio_buffer_t *input_buffer = audio_buffer_create(sample_count, 44100, 1);
    audio_buffer_t *output_buffer = audio_buffer_create(sample_count, 44100, 1);
    
    if (!input_buffer || !output_buffer) {
        fprintf(stderr, "Failed to create audio buffers\n");
        audio_buffer_destroy(input_buffer);
        audio_buffer_destroy(output_buffer);
        free(input_data_b64);
        free(metadata_json);
        free(decoded_data);
        redis_store_job_error(redis_client, job_id, "Failed to create audio buffers");
        redis_update_job_status(redis_client, job_id, "failed");
        return -1;
    }
    
    // Copy decoded data to input buffer
    memcpy(input_buffer->data, decoded_data, decoded_len);
    input_buffer->length = sample_count;
    
    // Create and configure job
    audio_job_t job = {0};
    job.job_id = (char*)job_id;
    job.input_buffer = input_buffer;
    job.output_buffer = output_buffer;
    
    // Parse effects from metadata
    parse_effects_from_json(metadata_json, &job);
    
    // Process the job
    int result = process_audio_job(&job);
    
    if (result == 0) {
        // Create WAV file from processed PCM data
        uint8_t *wav_data = NULL;
        size_t wav_size = 0;
        
        // Convert float samples back to 16-bit PCM for WAV
        int16_t *pcm_samples = malloc(output_buffer->length * sizeof(int16_t));
        if (!pcm_samples) {
            fprintf(stderr, "Failed to allocate PCM sample buffer\n");
            audio_buffer_destroy(input_buffer);
            audio_buffer_destroy(output_buffer);
            free(input_data_b64);
            free(metadata_json);
            free(decoded_data);
            redis_store_job_error(redis_client, job_id, "Memory allocation failed");
            redis_update_job_status(redis_client, job_id, "failed");
            return -1;
        }
        
        // Convert float samples to 16-bit PCM
        for (size_t i = 0; i < output_buffer->length; i++) {
            float sample = output_buffer->data[i];
            // Clamp to [-1.0, 1.0] and convert to 16-bit
            if (sample > 1.0f) sample = 1.0f;
            if (sample < -1.0f) sample = -1.0f;
            pcm_samples[i] = (int16_t)(sample * 32767.0f);
        }
        
        // Create WAV file
        if (create_wav_file(pcm_samples, output_buffer->length, 44100, 1, &wav_data, &wav_size) != 0) {
            fprintf(stderr, "Failed to create WAV file\n");
            free(pcm_samples);
            audio_buffer_destroy(input_buffer);
            audio_buffer_destroy(output_buffer);
            free(input_data_b64);
            free(metadata_json);
            free(decoded_data);
            redis_store_job_error(redis_client, job_id, "Failed to create WAV file");
            redis_update_job_status(redis_client, job_id, "failed");
            return -1;
        }
        
        free(pcm_samples);
        
        // Encode WAV data to base64
        size_t encoded_size = base64_encoded_size(wav_size);
        char *encoded_output = malloc(encoded_size + 1);
        
        if (encoded_output) {
            base64_encode(wav_data, wav_size, encoded_output);
            encoded_output[encoded_size] = '\0';
            
            // Store result
            redis_store_job_result(redis_client, job_id, encoded_output);
            
            // Calculate processing time
            clock_t end_time = clock();
            double processing_time_ms = ((double)(end_time - start_time) / CLOCKS_PER_SEC) * 1000.0;
            
            // Update metadata
            char *updated_metadata = create_updated_metadata(metadata_json, job_id, processing_time_ms);
            if (updated_metadata) {
                redis_update_job_metadata(redis_client, job_id, updated_metadata);
                free(updated_metadata);
            }
            
            // Update status to completed
            redis_update_job_status(redis_client, job_id, "completed");
            
            printf("Job %s completed successfully in %.2f ms\n", job_id, processing_time_ms);
            
            free(encoded_output);
            free(wav_data);
        } else {
            free(wav_data);
            redis_store_job_error(redis_client, job_id, "Failed to encode output data");
            redis_update_job_status(redis_client, job_id, "failed");
            result = -1;
        }
    } else {
        redis_store_job_error(redis_client, job_id, "Audio processing failed");
        redis_update_job_status(redis_client, job_id, "failed");
    }
    
    // Cleanup
    audio_buffer_destroy(input_buffer);
    audio_buffer_destroy(output_buffer);
    free(input_data_b64);
    free(metadata_json);
    free(decoded_data);
    
    return result;
}