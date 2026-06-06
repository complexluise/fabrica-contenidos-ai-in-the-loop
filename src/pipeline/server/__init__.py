"""Studio local (D-031): backend FastAPI + job manager sobre el pipeline.

La API es una cáscara fina: los endpoints llaman a `studio`/`runner`/`export`.
Local, single-user, sin auth; el estado vive en disco (`projects/`/`runs/`/`cache/`).
"""
