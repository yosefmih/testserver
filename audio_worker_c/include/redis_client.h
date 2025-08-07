#ifndef REDIS_CLIENT_H
#define REDIS_CLIENT_H

#include <hiredis/hiredis.h>
#include "audio_types.h"

// Redis client structure
typedef struct {
    redisContext *context;
    char *hostname;
    int port;
    char *password;
    int db;
} redis_client_t;

// Job data structure for Redis operations
typedef struct {
    char *job_id;
    char *input_data_b64;
    char *status;
    char *metadata_json;
    char *result_data_b64;
    char *error_message;
} redis_job_data_t;

// Redis client functions
redis_client_t* redis_client_create(const char *hostname, int port, const char *password, int db);
void redis_client_destroy(redis_client_t *client);
int redis_client_connect(redis_client_t *client);
int redis_client_ping(redis_client_t *client);

// Job queue operations
char* redis_pop_job(redis_client_t *client, int timeout_seconds);
int redis_update_job_status(redis_client_t *client, const char *job_id, const char *status);
int redis_get_job_input(redis_client_t *client, const char *job_id, char **input_data_b64);
int redis_get_job_metadata(redis_client_t *client, const char *job_id, char **metadata_json);
int redis_store_job_result(redis_client_t *client, const char *job_id, const char *result_data_b64);
int redis_store_job_error(redis_client_t *client, const char *job_id, const char *error_message);
int redis_update_job_metadata(redis_client_t *client, const char *job_id, const char *metadata_json);

// Utility functions
void redis_job_data_init(redis_job_data_t *job_data);
void redis_job_data_cleanup(redis_job_data_t *job_data);

#endif // REDIS_CLIENT_H