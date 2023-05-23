FROM python:3.11-bullseye

# Create empty directory for persistent data.
WORKDIR /usr/src/data

WORKDIR /usr/src/app

COPY . .

CMD [ "python", "./server.py" ]
