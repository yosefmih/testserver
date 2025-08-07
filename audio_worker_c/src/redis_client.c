#define _GNU_SOURCE
#include "redis_client.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

redis_client_t* redis_client_create(const char *hostname, int port, const char *password, int db) {
    redis_client_t *client = malloc(sizeof(redis_client_t));
    if (!client) return NULL;
    
    client->context = NULL;
    client->hostname = strdup(hostname ? hostname : "localhost");
    client->port = port > 0 ? port : 6379;
    client->password = password ? strdup(password) : NULL;
    client->db = db;
    
    if (!client->hostname) {
        redis_client_destroy(client);
        return NULL;
    }
    
    return client;
}

void redis_client_destroy(redis_client_t *client) {
    if (client) {
        if (client->context) {
            redisFree(client->context);
        }
        free(client->hostname);
        free(client->password);
        free(client);
    }
}

int redis_client_connect(redis_client_t *client) {
    if (!client) return -1;
    
    // Connect to Redis
    client->context = redisConnect(client->hostname, client->port);
    if (!client->context || client->context->err) {
        if (client->context) {
            fprintf(stderr, "Redis connection error: %s\n", client->context->errstr);
            redisFree(client->context);
            client->context = NULL;
        }
        return -1;
    }
    
    // Authenticate if password is provided
    if (client->password) {
        redisReply *reply = redisCommand(client->context, "AUTH %s", client->password);
        if (!reply || reply->type == REDIS_REPLY_ERROR) {
            fprintf(stderr, "Redis authentication failed\n");
            if (reply) freeReplyObject(reply);
            return -1;
        }
        freeReplyObject(reply);
    }
    
    // Select database
    if (client->db != 0) {
        redisReply *reply = redisCommand(client->context, "SELECT %d", client->db);
        if (!reply || reply->type == REDIS_REPLY_ERROR) {
            fprintf(stderr, "Redis database selection failed\n");
            if (reply) freeReplyObject(reply);
            return -1;
        }
        freeReplyObject(reply);
    }
    
    return 0;
}

int redis_client_ping(redis_client_t *client) {
    if (!client || !client->context) return -1;
    
    redisReply *reply = redisCommand(client->context, "PING");
    if (!reply || reply->type != REDIS_REPLY_STATUS || 
        strcmp(reply->str, "PONG") != 0) {
        if (reply) freeReplyObject(reply);
        return -1;
    }
    
    freeReplyObject(reply);
    return 0;
}

char* redis_pop_job(redis_client_t *client, int timeout_seconds) {
    if (!client || !client->context) return NULL;
    
    redisReply *reply = redisCommand(client->context, "BRPOP audio:queue %d", timeout_seconds);
    if (!reply || reply->type != REDIS_REPLY_ARRAY || reply->elements != 2) {
        if (reply) freeReplyObject(reply);
        return NULL;
    }
    
    char *job_id = strdup(reply->element[1]->str);
    freeReplyObject(reply);
    
    return job_id;
}

int redis_update_job_status(redis_client_t *client, const char *job_id, const char *status) {
    if (!client || !client->context || !job_id || !status) return -1;
    
    redisReply *reply = redisCommand(client->context, "SET audio:job:%s:status %s EX 3600", 
                                   job_id, status);
    if (!reply || reply->type == REDIS_REPLY_ERROR) {
        if (reply) freeReplyObject(reply);
        return -1;
    }
    
    freeReplyObject(reply);
    return 0;
}

int redis_get_job_input(redis_client_t *client, const char *job_id, char **input_data_b64) {
    if (!client || !client->context || !job_id || !input_data_b64) return -1;
    
    redisReply *reply = redisCommand(client->context, "GET audio:job:%s:input", job_id);
    if (!reply || reply->type != REDIS_REPLY_STRING) {
        if (reply) freeReplyObject(reply);
        return -1;
    }
    
    *input_data_b64 = strdup(reply->str);
    freeReplyObject(reply);
    
    return *input_data_b64 ? 0 : -1;
}

int redis_get_job_metadata(redis_client_t *client, const char *job_id, char **metadata_json) {
    if (!client || !client->context || !job_id || !metadata_json) return -1;
    
    redisReply *reply = redisCommand(client->context, "GET audio:job:%s:metadata", job_id);
    if (!reply) return -1;
    
    if (reply->type == REDIS_REPLY_STRING) {
        *metadata_json = strdup(reply->str);
        freeReplyObject(reply);
        return 0;
    } else if (reply->type == REDIS_REPLY_NIL) {
        *metadata_json = strdup("{}");
        freeReplyObject(reply);
        return 0;
    }
    
    freeReplyObject(reply);
    return -1;
}

int redis_store_job_result(redis_client_t *client, const char *job_id, const char *result_data_b64) {
    if (!client || !client->context || !job_id || !result_data_b64) return -1;
    
    redisReply *reply = redisCommand(client->context, "SET audio:job:%s:result %s EX 3600", 
                                   job_id, result_data_b64);
    if (!reply || reply->type == REDIS_REPLY_ERROR) {
        if (reply) freeReplyObject(reply);
        return -1;
    }
    
    freeReplyObject(reply);
    return 0;
}

int redis_store_job_error(redis_client_t *client, const char *job_id, const char *error_message) {
    if (!client || !client->context || !job_id || !error_message) return -1;
    
    redisReply *reply = redisCommand(client->context, "SET audio:job:%s:error %s EX 3600", 
                                   job_id, error_message);
    if (!reply || reply->type == REDIS_REPLY_ERROR) {
        if (reply) freeReplyObject(reply);
        return -1;
    }
    
    freeReplyObject(reply);
    return 0;
}

int redis_update_job_metadata(redis_client_t *client, const char *job_id, const char *metadata_json) {
    if (!client || !client->context || !job_id || !metadata_json) return -1;
    
    redisReply *reply = redisCommand(client->context, "SET audio:job:%s:metadata %s EX 3600", 
                                   job_id, metadata_json);
    if (!reply || reply->type == REDIS_REPLY_ERROR) {
        if (reply) freeReplyObject(reply);
        return -1;
    }
    
    freeReplyObject(reply);
    return 0;
}

void redis_job_data_init(redis_job_data_t *job_data) {
    if (job_data) {
        memset(job_data, 0, sizeof(redis_job_data_t));
    }
}

void redis_job_data_cleanup(redis_job_data_t *job_data) {
    if (job_data) {
        free(job_data->job_id);
        free(job_data->input_data_b64);
        free(job_data->status);
        free(job_data->metadata_json);
        free(job_data->result_data_b64);
        free(job_data->error_message);
        redis_job_data_init(job_data);
    }
}