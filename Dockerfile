FROM 992382605253.dkr.ecr.us-east-2.amazonaws.com/testserver:latest AS previous
RUN echo "=== PREVIOUS IMAGE PULL SUCCEEDED ==="

FROM alpine:3.20
COPY --from=previous /etc/os-release /tmp/previous-os-release

ARG ENV_A
ARG PORTER_ENV_A
ARG GHA_ONLY_VAR
ARG VARIABLES_FLAG_VAR

RUN echo "=== BUILD ARG TEST RESULTS ===" && \
    echo "ENV_A=${ENV_A:-NOT SET}" && \
    echo "PORTER_ENV_A=${PORTER_ENV_A:-NOT SET}" && \
    echo "GHA_ONLY_VAR=${GHA_ONLY_VAR:-NOT SET}" && \
    echo "VARIABLES_FLAG_VAR=${VARIABLES_FLAG_VAR:-NOT SET}" && \
    echo "=== END TEST RESULTS ==="

CMD ["sleep", "infinity"]
