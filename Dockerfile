FROM python:3.14

ARG USER
ARG GROUP

WORKDIR /app

# Install Node.js and npm
RUN apt-get update && apt-get install -y curl ca-certificates gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*


RUN pip install --upgrade pip && pip install poetry
RUN poetry config virtualenvs.create false 
COPY --chown=${USER}:${GROUP} pyproject.toml poetry.lock /app/
RUN poetry install --no-interaction --no-ansi --no-root

COPY --chown=${USER}:${GROUP} . /app/
RUN chmod +x entrypoint.sh

# Install Tailwind dependencies for the Linux container
RUN cd /app/theme/static_src && npm install
RUN mkdir -p /app/theme/static/css/dist

CMD ["python", "manage.py", "tailwind", "start"]
