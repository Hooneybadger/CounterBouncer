#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts/setup vendor/cloudsuite-servers
# Dedicated names/network; leave unrelated Docker workloads untouched.
# The first campaign used metrictrust-* names; rename if the new names are free.
if docker container inspect metrictrust-dc-server >/dev/null 2>&1 \
   && ! docker container inspect counterbouncer-dc-server >/dev/null 2>&1; then
  docker rename metrictrust-dc-server counterbouncer-dc-server
fi
if docker container inspect metrictrust-dc-client >/dev/null 2>&1 \
   && ! docker container inspect counterbouncer-dc-client >/dev/null 2>&1; then
  docker rename metrictrust-dc-client counterbouncer-dc-client
fi
NET=counterbouncer-net
if docker container inspect counterbouncer-dc-server >/dev/null 2>&1; then
  NET=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' counterbouncer-dc-server | awk '{print $1}')
fi
docker network inspect "$NET" >/dev/null 2>&1 || docker network create "$NET"
docker image inspect cloudsuite/data-caching:server > artifacts/setup/cloudsuite-server-image.json
docker image inspect cloudsuite/data-caching:client > artifacts/setup/cloudsuite-client-image.json
printf 'counterbouncer-dc-server, 11211\n' > vendor/cloudsuite-servers/docker_servers.txt
if ! docker container inspect counterbouncer-dc-server >/dev/null 2>&1; then
  docker run --name counterbouncer-dc-server --network "$NET" --cpuset-cpus 2,4,6,8 \
    --user "$(id -u):$(id -g)" -d cloudsuite/data-caching:server -t 4 -m 10240 -n 550
fi
if ! docker container inspect counterbouncer-dc-client >/dev/null 2>&1; then
  docker run -dit --name counterbouncer-dc-client --network "$NET" --cpuset-cpus 16-23 \
    -v "$PWD/vendor/cloudsuite-servers:/usr/src/memcached/memcached_client/docker_servers:ro" \
    cloudsuite/data-caching:client
fi
docker exec counterbouncer-dc-client /bin/bash /entrypoint.sh '--m=S&W' --S=28 --D=10240 --w=8 --T=1
