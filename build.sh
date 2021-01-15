#!/bin/bash

PACKAGE_PATH=$(dirname $0);

push="$1"
if [[ "$push" = "--push" ]]; then
  build_type="$2"
else
  push=""
  build_type="$1"
fi

if [[ "$build_type" = "" ]]; then
  build_type="build";
fi

IMAGE_NAME=mcenv
DOCKER_IMAGE_NAME=mccoygroup/mcenv
if [[ "$build_type" = "update" ]]; then
  docker build -t $IMAGE_NAME -f $PACKAGE_PATH/DockerfileUpdate $PACKAGE_PATH
else
  docker build -t $IMAGE_NAME -f $PACKAGE_PATH/Dockerfile $PACKAGE_PATH
  docker tag $IMAGE_NAME $IMAGE_NAME-core
fi
if [[ "$push" == "--push" ]]; then
  docker tag $IMAGE_NAME $DOCKER_IMAGE_NAME
  docker push $DOCKER_IMAGE_NAME
fi