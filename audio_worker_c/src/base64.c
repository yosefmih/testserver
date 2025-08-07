#include "base64.h"
#include <string.h>

static const char base64_chars[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

static int base64_char_to_value(char c) {
    if (c >= 'A' && c <= 'Z') return c - 'A';
    if (c >= 'a' && c <= 'z') return c - 'a' + 26;
    if (c >= '0' && c <= '9') return c - '0' + 52;
    if (c == '+') return 62;
    if (c == '/') return 63;
    return -1;
}

size_t base64_encoded_size(size_t input_len) {
    return ((input_len + 2) / 3) * 4;
}

size_t base64_decoded_size(const char *input) {
    size_t len = strlen(input);
    size_t padding = 0;
    
    if (len >= 1 && input[len - 1] == '=') padding++;
    if (len >= 2 && input[len - 2] == '=') padding++;
    
    return (len * 3) / 4 - padding;
}

int base64_encode(const unsigned char *input, size_t input_len, char *output) {
    if (!input || !output) return -1;
    
    size_t i, j;
    for (i = 0, j = 0; i < input_len; i += 3, j += 4) {
        unsigned int triple = (input[i] << 16);
        
        if (i + 1 < input_len) {
            triple |= (input[i + 1] << 8);
        }
        if (i + 2 < input_len) {
            triple |= input[i + 2];
        }
        
        output[j] = base64_chars[(triple >> 18) & 0x3F];
        output[j + 1] = base64_chars[(triple >> 12) & 0x3F];
        output[j + 2] = (i + 1 < input_len) ? base64_chars[(triple >> 6) & 0x3F] : '=';
        output[j + 3] = (i + 2 < input_len) ? base64_chars[triple & 0x3F] : '=';
    }
    
    output[j] = '\0';
    return 0;
}

int base64_decode(const char *input, unsigned char *output, size_t *output_len) {
    if (!input || !output || !output_len) return -1;
    
    size_t input_len = strlen(input);
    if (input_len % 4 != 0) return -1;
    
    *output_len = 0;
    
    for (size_t i = 0; i < input_len; i += 4) {
        int values[4];
        
        for (int j = 0; j < 4; j++) {
            if (input[i + j] == '=') {
                values[j] = 0;
            } else {
                values[j] = base64_char_to_value(input[i + j]);
                if (values[j] == -1) return -1;
            }
        }
        
        unsigned int triple = (values[0] << 18) | (values[1] << 12) | (values[2] << 6) | values[3];
        
        output[*output_len] = (triple >> 16) & 0xFF;
        (*output_len)++;
        
        if (input[i + 2] != '=') {
            output[*output_len] = (triple >> 8) & 0xFF;
            (*output_len)++;
        }
        
        if (input[i + 3] != '=') {
            output[*output_len] = triple & 0xFF;
            (*output_len)++;
        }
    }
    
    return 0;
}