#ifndef BASE64_H
#define BASE64_H

#include <stddef.h>

// Base64 encoding/decoding functions
size_t base64_encoded_size(size_t input_len);
size_t base64_decoded_size(const char *input);
int base64_encode(const unsigned char *input, size_t input_len, char *output);
int base64_decode(const char *input, unsigned char *output, size_t *output_len);

#endif // BASE64_H