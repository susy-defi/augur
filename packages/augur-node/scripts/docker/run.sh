#!/bin/bash

IMAGE=$1
TAG=$(node ./scripts/get-contract-hashes.js)
docker run -it -e ETHEREUM_WS=${ETHEREUM_WS} --rm -p 9001:9001 -p 9002:9002 --name ${CONTAINER_NAME:-augur-node} $IMAGE:$TAG

