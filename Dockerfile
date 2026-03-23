FROM 992382605253.dkr.ecr.us-east-2.amazonaws.com/testserver:45cc8a01c68e231b1f113f99a971d0cab43026b3 AS previous
RUN echo "=== PREVIOUS IMAGE PULL SUCCEEDED ==="

FROM alpine:3.20
COPY --from=previous /etc/os-release /tmp/previous-os-release

ARG ENV_A
ARG PORTER_ENV_A
ARG GHA_ONLY_VAR
ARG VARIABLES_FLAG_VAR

RUN --mount=type=cache,target=/tmp/test-cache,id=test-cache \
    echo "=== MOUNT CACHE TEST ===" && \
    ls -la /tmp/test-cache && \
    echo "mount cache works" > /tmp/test-cache/proof.txt && \
    echo "=== MOUNT CACHE SUCCEEDED ==="

RUN echo "=== BUILD ARG TEST RESULTS ===" && \
    echo "ENV_A=${ENV_A:-NOT SET}" && \
    echo "PORTER_ENV_A=${PORTER_ENV_A:-NOT SET}" && \
    echo "GHA_ONLY_VAR=${GHA_ONLY_VAR:-NOT SET}" && \
    echo "VARIABLES_FLAG_VAR=${VARIABLES_FLAG_VAR:-NOT SET}" && \
    echo "=== END TEST RESULTS ==="

CMD ["sleep", "infinity"]
