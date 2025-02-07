#!/bin/bash

set -euo pipefail
# set trace=1 to enable debugging: trace=1 $0
[[ -n "${TRACE-}" ]] && set -x

SH_DIR=$(dirname "$(realpath "$0")")
ROOT_DIR=$(dirname "$SH_DIR")
API_SDK_CONFIG_PATH="${ROOT_DIR}/validate-config.json"

# Using the jq Docker image to avoid requiring developers to install jq on the host machine.
jq() {
  local jq_image='ghcr.io/jqlang/jq'
  local jq_version='1.7.1'
  docker run --rm -i "${jq_image}:${jq_version}" "$@"
}

load_api_sdk_config() {
  OPEN_API_GENERATOR_IMAGE=$(jq -r '.openApiGeneratorImage' < "$API_SDK_CONFIG_PATH")
  OPEN_API_GENERATOR_VERSION=$(jq -r '.openApiGeneratorVersion' < "$API_SDK_CONFIG_PATH")
  OPEN_API_PATH=$(jq -r '.openApiPath' < "$API_SDK_CONFIG_PATH")
}

setup_docker_path() {
  DOCKER_WORKDIR="/app"
  DOCKER_OPEN_API_PATH="${DOCKER_WORKDIR}/${OPEN_API_PATH}"
}

validate_api_swagger() {
  # Using the openapi-generator-cli Docker image,
  # since we don't want to install JVM on the host machine.
  # Reference: https://github.com/OpenAPITools/openapi-generator?tab=readme-ov-file#17---npm
  docker run \
    --rm \
    -w "$DOCKER_WORKDIR" \
    -v "${ROOT_DIR}:${DOCKER_WORKDIR}" \
    "${OPEN_API_GENERATOR_IMAGE}:${OPEN_API_GENERATOR_VERSION}" \
    validate \
    -i "$DOCKER_OPEN_API_PATH"
}

main() {
  load_api_sdk_config
  setup_docker_path
  validate_api_swagger
}

main "$@"