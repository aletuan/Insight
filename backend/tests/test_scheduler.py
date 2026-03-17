from app.scheduler import configure_scheduler


def test_scheduler_has_two_jobs():
    """Scheduler should register clustering and digest jobs."""
    scheduler = configure_scheduler()
    jobs = scheduler.get_jobs()
    job_ids = {job.id for job in jobs}
    assert "clustering_nightly" in job_ids
    assert "digest_daily" in job_ids


def test_scheduler_clustering_runs_at_3am():
    """Clustering job should be scheduled at 3:00 AM."""
    scheduler = configure_scheduler()
    job = scheduler.get_job("clustering_nightly")
    trigger = job.trigger
    assert str(trigger.fields[trigger.FIELD_NAMES.index("hour")]) == "3"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("minute")]) == "0"


def test_scheduler_digest_runs_at_7am():
    """Digest job should be scheduled at 7:00 AM."""
    scheduler = configure_scheduler()
    job = scheduler.get_job("digest_daily")
    trigger = job.trigger
    assert str(trigger.fields[trigger.FIELD_NAMES.index("hour")]) == "7"
    assert str(trigger.fields[trigger.FIELD_NAMES.index("minute")]) == "0"
