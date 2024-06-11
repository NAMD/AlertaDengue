# from https://github.com/postgis/docker-postgis/blob/969ef8a9e4a22e1556ca99cab4178f6e60c1483d/14-3.2/Dockerfile
FROM postgres:14-bullseye

LABEL maintainer="Sandro Loch <es.loch@gmail.com>"

ENV PG_MAJOR 14
ENV POSTGIS_MAJOR 3

ARG HOST_UID
ARG HOST_GID

RUN usermod -u ${HOST_UID} postgres \
  && groupmod -g ${HOST_GID} postgres \
  && echo "postgres:x:${HOST_UID}:${HOST_GID}:PostgreSQL,,,:/var/lib/postgresql:/bin/bash" >> /etc/passwd

RUN apt-get update \
  && apt-cache showpkg postgresql-$PG_MAJOR-postgis-$POSTGIS_MAJOR \
  && apt-get install -y --no-install-recommends \
  postgresql-$PG_MAJOR-postgis-$POSTGIS_MAJOR \
  postgresql-$PG_MAJOR-postgis-$POSTGIS_MAJOR-scripts \
  postgresql-plpython3-$PG_MAJOR \
  && rm -rf /var/lib/apt/lists/*

USER postgres
