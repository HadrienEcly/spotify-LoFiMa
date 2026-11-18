"""Tests de la file d'attente (jobs.py), seule puis via l'API."""

import threading

from lofima.errors import DownloadError
from lofima.jobs import JobQueue, split_urls
from lofima.models import JobStatus

URL = "https://www.youtube.com/watch?v=abc123XYZ_-"


def test_split_urls_handles_pasted_lists_and_duplicates():
    assert split_urls(["a\nb  c", "", "a", " d "]) == ["a", "b", "c", "d"]


def test_queue_processes_in_order_and_reports_errors():
    processed = []

    def processor(url, reporter):
        reporter.set_title(f"Titre {url}")
        if url == "bad":
            raise DownloadError("vidéo supprimée")
        processed.append(url)
        return f"id-{url}"

    queue = JobQueue(processor)
    queue.submit(["one", "bad", "two"])
    assert queue.wait_idle()

    jobs = {job.url: job for job in queue.list()}
    assert processed == ["one", "two"]
    assert jobs["one"].status == JobStatus.DONE and jobs["one"].track_id == "id-one"
    assert jobs["bad"].status == JobStatus.FAILED and "supprimée" in jobs["bad"].error
    assert jobs["two"].title == "Titre two"

    assert queue.clear_finished() == 3
    assert queue.list() == []


def test_queued_job_can_be_cancelled_but_not_running_one():
    started, release = threading.Event(), threading.Event()

    def slow_processor(url, reporter):
        started.set()
        release.wait(5)
        return url

    queue = JobQueue(slow_processor)
    running, waiting = queue.submit(["first", "second"])
    assert started.wait(5)

    assert queue.remove(running.id) is False  # en cours
    assert queue.remove(waiting.id) is True   # en attente -> annulé
    release.set()
    assert queue.wait_idle()
    assert [job.url for job in queue.list()] == ["first"]


def test_api_jobs_end_to_end(env):
    client = env["client"]
    response = client.post("/api/jobs", json={"urls": [f"{URL}\n{URL}"]})  # doublon fusionné
    assert response.status_code == 202 and len(response.json()) == 1

    assert env["queue"].wait_idle()
    job = client.get("/api/jobs").json()[0]
    assert job["status"] == "done" and job["track_id"] == "youtube-abc123XYZ_-"
    assert job["title"].startswith("Daft Punk")

    # Le même lien une 2e fois : le job échoue proprement (déjà dans la bibliothèque)
    client.post("/api/jobs", json={"urls": [URL]})
    assert env["queue"].wait_idle()
    assert "déjà" in client.get("/api/jobs").json()[1]["error"]

    assert client.post("/api/jobs/clear").json() == {"removed": 2}
    assert client.post("/api/jobs", json={"urls": ["  "]}).status_code == 422
