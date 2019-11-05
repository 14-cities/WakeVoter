FROM python:3.7-slim-buster

# Output print statements directly to console instead of buffering them up and printing them out in batches
ENV PYTHONUNBUFFERED=1

RUN mkdir -p /www/WakeVoter
WORKDIR /www/WakeVoter

COPY APIkey.txt .

# Required for Rtree (installed by pip)
RUN apt-get update && apt-get install -y libspatialindex-dev

COPY reqs.txt .
RUN pip install -r reqs.txt

COPY VoteSquad.py .

CMD ["python", "-c", "import VoteSquad"]
