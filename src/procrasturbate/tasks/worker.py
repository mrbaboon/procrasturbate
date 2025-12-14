"""Procrastinate worker configuration."""

import procrastinate

from ..config import settings

# Create procrastinate app with async connector
app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=settings.procrastinate_database_url,
        kwargs={},
    ),
    import_paths=["procrasturbate.tasks.review_tasks"],
)
