# ref: https://github.com/mamba-org/micromamba-docker/blob/main/Dockerfile
FROM condaforge/mambaforge:latest

LABEL maintainer="Sandro Loch <es.loch@gmail.com>"
LABEL org.opencontainers.image.title="AlertaDengue"
LABEL org.opencontainers.image.authors="AlertaDengue Team"
LABEL org.opencontainers.image.source="https://github.com/AlertaDengue/AlertaDengue"
LABEL org.opencontainers.image.version="latest"
LABEL org.opencontainers.image.description="AlertaDengue package"

# it is the default, but using it here to have it explicitly
USER root

ARG HOST_UID
ARG HOST_GID
ARG SERVICES
ARG ENV
ENV ENV_NAME=alertadengue
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get -qq update --yes \
    && apt-get -qq install --yes --no-install-recommends \
    build-essential git make postgresql-client vim \
    ca-certificates wget locales sudo inotify-tools \
    && rm -rf /var/lib/apt/lists/* \
    /var/cache/apt/archives \
    /tmp/*

# Set locale
RUN sed -i -e "s/# pt_BR.*/pt_BR.UTF-8 UTF-8/" /etc/locale.gen \
    && dpkg-reconfigure --frontend=noninteractive locales \
    && update-locale LANG=pt_BR.UTF-8

# Create deploy user
RUN addgroup --gid ${HOST_GID} deploy \
    && useradd --uid ${HOST_UID} --gid ${HOST_GID} -ms /bin/bash deploy \
    && echo "deploy ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/deploy \
    && chmod 0440 /etc/sudoers.d/deploy \
    && export ENV_NAME="$ENV_NAME" \
    && mkdir -p /opt/conda /opt/services/ /tmp/dbf_parquet /opt/services/episcanner \
    && chown ${HOST_UID}:${HOST_GID} /opt/services/ /tmp/dbf_parquet \
    && chmod -R a+rwx /opt/conda /opt/services /tmp \
    && echo 'source activate "$ENV_NAME"' >  /home/deploy/.bashrc
ENV PATH "$PATH:/home/deploy/.local/bin"
ENV PATH /opt/conda/envs/$ENV_NAME/bin:$PATH

# Create script activate environment
RUN echo 'source /opt/conda/bin/activate alertadengue && exec "$@"' > /activate.sh
RUN chmod +x /activate.sh

USER deploy

# Change shell to bash
SHELL ["/bin/bash", "-c"]

COPY --chown=${HOST_UID}:${HOST_GID} conda/base.yaml /tmp/environment.yaml

# Use environment to update the env alertadengue
RUN conda env create -n $ENV_NAME \
    --file /tmp/environment.yaml \
    && conda clean --all \
    && find /opt/conda/ -type f,l -name '*.a' -delete \
    && find /opt/conda/ -type f,l -name '*.pyc' -delete \
    && find /opt/conda/ -type f,l -name '*.js.map' -delete
# && rm -rf /home/deploy/.conda/pkgs

COPY --chown=${HOST_UID}:${HOST_GID} ./AlertaDengue  /opt/services/AlertaDengue

WORKDIR /opt/services/AlertaDengue

COPY --chown=${HOST_UID}:${HOST_GID} .env.tpl pyproject.toml README.md /opt/services/
COPY --chown=${HOST_UID}:${HOST_GID} ./containers/scripts/poetry-install.sh /tmp/poetry-install.sh

RUN bash /tmp/poetry-install.sh

RUN mkdir -p /opt/services/scripts/
RUN chown -R ${HOST_UID}:${HOST_GID} /opt/services/scripts/

RUN mkdir -p /opt/services/collector
RUN chown -R ${HOST_UID}:${HOST_GID} /opt/services/collector

COPY --chown=${HOST_UID}:${HOST_GID} ./containers/scripts/celery.sh  /opt/services/celery.sh
COPY --chown=${HOST_UID}:${HOST_GID} ./containers/scripts/entrypoint.sh  /entrypoint.sh
COPY --chown=${HOST_UID}:${HOST_GID} ./containers/scripts/test.sh /opt/services/test.sh

# The command specified in the Compose file will be executed
# ENTRYPOINT ["/entrypoint.sh"]
