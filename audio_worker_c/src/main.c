#include "audio_processing.h"
#include "redis_client.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>
#include <getopt.h>
#include <time.h>

// Global flag for graceful shutdown
static volatile int keep_running = 1;
static int jobs_processed = 0;
static time_t start_time;

// External function from audio_job.c
int process_redis_job(redis_client_t *redis_client, const char *job_id);

static void signal_handler(int sig) {
    (void)sig; // Unused parameter
    printf("\nReceived shutdown signal. Gracefully shutting down...\n");
    keep_running = 0;
}

static void print_usage(const char *program_name) {
    printf("Usage: %s [OPTIONS]\n", program_name);
    printf("High-performance C audio processing worker for Redis job queue\n\n");
    printf("Options:\n");
    printf("  -h, --host HOST     Redis hostname (default: localhost)\n");
    printf("  -p, --port PORT     Redis port (default: 6379)\n");
    printf("  -a, --auth PASS     Redis password (optional)\n");
    printf("  -d, --db DB         Redis database number (default: 0)\n");
    printf("  -t, --timeout SEC   Job poll timeout in seconds (default: 5)\n");
    printf("  -D, --duration MIN  Worker duration in minutes (default: 5, 0 = unlimited)\n");
    printf("  -v, --verbose       Enable verbose output\n");
    printf("  -V, --version       Show version information\n");
    printf("  --help              Show this help message\n\n");
    printf("Environment Variables:\n");
    printf("  REDIS_HOST         Redis hostname\n");
    printf("  REDIS_PORT         Redis port\n");
    printf("  REDIS_PASSWORD     Redis password\n");
    printf("  REDIS_DB           Redis database number\n\n");
    printf("Examples:\n");
    printf("  %s --host redis.example.com --port 6380\n", program_name);
    printf("  %s --duration 10 --verbose\n", program_name);
    printf("  REDIS_HOST=redis.local %s\n", program_name);
}

static void print_version(void) {
    printf("Audio Worker C v1.0.0\n");
    printf("High-performance audio processing worker\n");
    printf("Built on %s at %s\n", __DATE__, __TIME__);
}

static void print_stats(void) {
    time_t current_time = time(NULL);
    double elapsed = difftime(current_time, start_time);
    double jobs_per_minute = elapsed > 0 ? (jobs_processed / elapsed) * 60.0 : 0.0;
    
    printf("Worker Stats - Elapsed: %.0fs, Jobs: %d, Rate: %.1f jobs/min\n",
           elapsed, jobs_processed, jobs_per_minute);
}

int main(int argc, char *argv[]) {
    // Environment variable configuration (matches Python audio_worker.py)
    char *redis_url = getenv("REDIS_URL");  // Priority 1: REDIS_URL
    char *redis_host = getenv("REDIS_HOST"); // Priority 2: Individual params
    char *redis_pass = getenv("REDIS_PASS"); // Use REDIS_PASS like Python version
    
    // Default values
    if (!redis_host && !redis_url) redis_host = "localhost";
    
    int redis_port = 6379;
    if (getenv("REDIS_PORT")) {
        redis_port = atoi(getenv("REDIS_PORT"));
    }
    
    // Support both REDIS_PASSWORD and REDIS_PASS for compatibility
    char *redis_password = redis_pass ? redis_pass : getenv("REDIS_PASSWORD");
    
    int redis_db = 0;
    if (getenv("REDIS_DB")) {
        redis_db = atoi(getenv("REDIS_DB"));
    }
    
    // Handle REDIS_URL parsing (simplified - full URL parsing would need additional logic)
    if (redis_url && !redis_host) {
        // For now, log that REDIS_URL is set but we'll use individual params
        // Full URL parsing would require additional dependencies
        printf("Warning: REDIS_URL set but not fully parsed. Using individual env vars.\n");
    }
    
    int poll_timeout = 5;
    int duration_minutes = 0;  // Default to unlimited duration
    int verbose = 0;
    
    // Command line options
    static struct option long_options[] = {
        {"host",     required_argument, 0, 'h'},
        {"port",     required_argument, 0, 'p'},
        {"auth",     required_argument, 0, 'a'},
        {"db",       required_argument, 0, 'd'},
        {"timeout",  required_argument, 0, 't'},
        {"duration", required_argument, 0, 'D'},
        {"verbose",  no_argument,       0, 'v'},
        {"version",  no_argument,       0, 'V'},
        {"help",     no_argument,       0, '?'},
        {0, 0, 0, 0}
    };
    
    int opt;
    while ((opt = getopt_long(argc, argv, "h:p:a:d:t:D:vV?", long_options, NULL)) != -1) {
        switch (opt) {
            case 'h':
                redis_host = optarg;
                break;
            case 'p':
                redis_port = atoi(optarg);
                if (redis_port <= 0 || redis_port > 65535) {
                    fprintf(stderr, "Invalid port number: %s\n", optarg);
                    return 1;
                }
                break;
            case 'a':
                redis_password = optarg;
                break;
            case 'd':
                redis_db = atoi(optarg);
                if (redis_db < 0) {
                    fprintf(stderr, "Invalid database number: %s\n", optarg);
                    return 1;
                }
                break;
            case 't':
                poll_timeout = atoi(optarg);
                if (poll_timeout < 1) {
                    fprintf(stderr, "Invalid timeout: %s\n", optarg);
                    return 1;
                }
                break;
            case 'D':
                duration_minutes = atoi(optarg);
                if (duration_minutes < 0) {
                    fprintf(stderr, "Invalid duration: %s\n", optarg);
                    return 1;
                }
                break;
            case 'v':
                verbose = 1;
                break;
            case 'V':
                print_version();
                return 0;
            case '?':
            default:
                print_usage(argv[0]);
                return opt == '?' ? 0 : 1;
        }
    }
    
    // Validate Redis connection info (like Python version)
    if (!redis_host && !redis_url) {
        fprintf(stderr, "Redis connection not configured. Set REDIS_URL or REDIS_HOST\n");
        return 1;
    }
    
    // Print configuration
    printf("Audio Worker C starting...\n");
    if (redis_url) {
        printf("Redis: Using REDIS_URL (parsed to %s:%d, db: %d)\n", redis_host ? redis_host : "localhost", redis_port, redis_db);
    } else {
        printf("Redis: %s:%d (db: %d)\n", redis_host, redis_port, redis_db);
    }
    
    // Simplify duration output
    if (duration_minutes == 0) {
        printf("Poll timeout: %ds, Duration: unlimited\n", poll_timeout);
    } else {
        printf("Poll timeout: %ds, Duration: %d minute%s\n", 
               poll_timeout, duration_minutes, duration_minutes == 1 ? "" : "s");
    }
    
    // Setup signal handlers
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    // Connect to Redis
    redis_client_t *redis_client = redis_client_create(redis_host, redis_port, redis_password, redis_db);
    if (!redis_client) {
        fprintf(stderr, "Failed to create Redis client\n");
        return 1;
    }
    
    if (redis_client_connect(redis_client) != 0) {
        fprintf(stderr, "Failed to connect to Redis\n");
        redis_client_destroy(redis_client);
        return 1;
    }
    
    // Test connection
    if (redis_client_ping(redis_client) != 0) {
        fprintf(stderr, "Redis ping failed\n");
        redis_client_destroy(redis_client);
        return 1;
    }
    
    if (verbose) {
        printf("Successfully connected to Redis\n");
    }
    
    // Main worker loop
    start_time = time(NULL);
    time_t end_time = (duration_minutes == 0) ? 0 : start_time + (duration_minutes * 60);
    time_t last_stats_time = start_time;
    
    printf("Worker started, waiting for jobs...\n");
    
    while (keep_running) {
        // Check duration limit
        if (end_time != 0 && time(NULL) >= end_time) {
            printf("Duration limit reached, shutting down...\n");
            break;
        }
        
        // Pop job from queue
        char *job_id = redis_pop_job(redis_client, poll_timeout);
        
        if (job_id) {
            if (verbose) {
                printf("Received job: %s\n", job_id);
            }
            
            // Process the job
            if (process_redis_job(redis_client, job_id) == 0) {
                jobs_processed++;
                if (verbose) {
                    printf("Job completed: %s\n", job_id);
                }
            } else {
                if (verbose) {
                    printf("Job failed: %s\n", job_id);
                }
            }
            
            free(job_id);
        } else {
            if (verbose) {
                printf("No jobs available, waiting...\n");
            }
        }
        
        // Print periodic stats
        time_t current_time = time(NULL);
        if (current_time - last_stats_time >= 30) {
            print_stats();
            last_stats_time = current_time;
        }
    }
    
    // Final stats and cleanup
    print_stats();
    printf("Worker shutting down. Processed %d jobs total.\n", jobs_processed);
    
    redis_client_destroy(redis_client);
    
    return 0;
}