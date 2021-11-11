#!/usr/bin/bash
set -ex
docker login -u 'api' \
             -p "${proget_api_key}" \
             "${proget_server}"

docker build ./ -t "${proget_server}/docker/makedeb/mprweb"
docker push "${proget_server}/docker/makedeb/mprweb"
