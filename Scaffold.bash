    Clients (Web / Mobile / Telegram Bot)
                    │
                    ▼
                API Gateway
                (FastAPI App)
                    │
            ┌───────┴────────┐
            │                │
        Core           Business Domains
    (Infra layer)     (Modules / Bounded Contexts)


app/
├── main.py # entrypoint
├── app_factory.py # create_app()
│
├── core/ # framework-level stuff
│ ├── config.py # settings (pydantic)
│ ├── security.py # jwt, hashing
│ ├── deps.py # common Depends()
│ ├── exceptions.py # custom errors
│ └── logging.py
│
├── infrastructure/ # external systems
│ ├── database/
│ │ ├── session.py # engine, sessionmaker
│ │ ├── base.py # Base = declarative_base()
│ │ └── migrations/ # alembic
│ └── redis/
│ └── client.py
│
├── modules/ # BUSINESS DOMAINS
│ ├── auth/
│ │ ├── router.py
│ │ ├── service.py
│ │ ├── repository.py
│ │ ├── schemas.py
│ │ ├── models.py
│ │ └── dependencies.py
│ │
│ ├── users/
│ │ ├── router.py
│ │ ├── service.py
│ │ ├── repository.py
│ │ ├── schemas.py
│ │ └── models.py
│ │
│ ├── daily_vocab/
│ │ ├── router.py
│ │ ├── service.py
│ │ ├── repository.py
│ │ ├── schemas.py
│ │ └── models.py
│ │
│ └── courses/
│ └── ...
│
├── shared/ # shared business logic
│ ├── pagination.py
│ ├── responses.py
│ └── enums.py
│
├── tests/
│ ├── conftest.py
│ ├── auth/
│ └── daily_vocab/
│
├── scripts/ # cli, cron
│
└── integrations/
    └── telegram/                      # BOT (separate runtime)
