# Enterprise IT Service Management Platform

A lightweight IT service management platform built with Django REST Framework, React, PostgreSQL, Redis/Celery, and Docker.

## Project structure

- `backend/` — Django REST API (Django project and apps will be generated later)
- `frontend/` — React application (to be scaffolded later)
- `docs/` — Project documentation
- `docker/` — Docker-related configuration and assets
- `docker-compose.yml` — Local PostgreSQL and Redis services
- `.env.example` — Example local environment configuration

Copy `.env.example` to `.env` and edit the local values as needed. Start the
development infrastructure with `docker compose up -d`. The backend and
frontend services will be added after their application scaffolds are created.
