### Low-Level Implementation Plan for Milestone 5.1

#### **Step 1: Environment Setup & Dependencies**

**Goal:** Prepare the project and local environment for Postgres development without breaking existing SQLite functionality.

1.  **Add New Dependencies:**

      * Add `alembic` for schema migrations and `psycopg` for the `asyncpg` driver. We will use the modern `psycopg` (v3) library, which integrates well with `asyncpg`.

    <!-- end list -->

    uv pip install alembic "psycopg[binary,pool]"
    uv pip freeze > requirements.txt
    ```

      * **Verification:** Confirm that `alembic` and `psycopg` are now listed in your `pyproject.toml` or `requirements.txt`.
2.  **Start a Local Postgres Instance:**

      * Use Docker for a consistent, isolated development database. This command will start a Postgres 16 container, create a database named `adventorator`, and persist its data in a Docker volume.

    <!-- end list -->

    ```bash
    docker run --name adventorator-pg -e POSTGRES_DB=adventorator -e POSTGRES_USER=user -e POSTGRES_PASSWORD=pass -p 5432:5432 -v adventorator-pg-data:/var/lib/postgresql/data -d postgres:16
    ```

      * **Verification:** You can connect to the database using a client like `psql` or DBeaver to confirm it is running.

-----

#### **Step 2: Code & Configuration Updates**

**Goal:** Modify the application code to support a Postgres connection while retaining SQLite compatibility for testing and simple setups.

1.  **Create a Local Environment File:**

      * Create a `.env` file in the project root (if it doesn't exist) and add the `DATABASE_URL` for your local Postgres instance.

    <!-- end list -->

    ```ini
    # .env
    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/adventorator"
    ```

2.  **Update Example Environment File:**

      * Add a commented-out Postgres URL to `.env.example` to guide future developers.

    <!-- end list -->

    ```ini
    # .env.example
    # DATABASE_URL="sqlite+aiosqlite:///./adventorator.sqlite3"
    # DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/adventorator"
    ```

3.  **Implement Defensive Pooling Logic:**

      * Update `Adventorator/db.py` with the exact logic you outlined. This change is defensive because it only applies the Postgres-specific pooling settings when a `postgresql` URL is detected.

    <!-- end list -->

    ```python
    # In Adventorator/db.py -> get_engine()

    # ... (inside the if _engine is None block)
    kwargs: dict[str, object] = {}
    if DATABASE_URL.startswith("sqlite+aiosqlite://"):
        # SQLite ignores pool_size; keep it minimal and avoid pre_ping
        kwargs.update(connect_args={"timeout": 30})
    else:
        # --- PRODUCTION POSTGRES CONFIGURATION ---
        kwargs.update(
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            pool_pre_ping=True,
        )
        # ------------------------------------------

    _engine = create_async_engine(DATABASE_URL, **kwargs)
    # ...
    ```

      * **Verification:** The application should still run perfectly fine if you comment out the Postgres URL in your `.env` and let it fall back to the SQLite default. All tests should still pass against SQLite.

-----

#### **Step 3: Alembic Initialization and Configuration**

**Goal:** Use Alembic to generate a migration script that can create the application's entire schema in a new Postgres database.

1.  **Initialize Alembic:**

      * Run this command in the project's root directory.

    <!-- end list -->

    ```bash
    alembic init alembic
    ```

      * **Verification:** A new `alembic` directory and an `alembic.ini` file are created.

2.  **Configure `alembic.ini`:**

      * Open `alembic.ini` and set the `sqlalchemy.url` to your Postgres database URL. This tells Alembic where to connect to run migrations.

    <!-- end list -->

    ```ini
    # alembic.ini
    sqlalchemy.url = postgresql+asyncpg://user:pass@localhost:5432/adventorator
    ```

3.  **Configure `alembic/env.py` for Autogeneration:**

      * Open `alembic/env.py`. Find the line `target_metadata = None` and modify it to point to your SQLAlchemy models' `Base.metadata`. This is how Alembic knows what your schema *should* look like.

    <!-- end list -->

    ```python
    # alembic/env.py

    # Add these imports at the top
    import sys
    from os.path import abspath, dirname
    sys.path.insert(0, dirname(dirname(abspath(__file__))))

    from Adventorator.models import Base # Make sure this import works

    # ... other imports

    # Find this line and change it
    # target_metadata = None
    target_metadata = Base.metadata

    # ... rest of the file
    ```

4.  **Generate the Initial Migration Script:**

      * Now, ask Alembic to compare your models (`target_metadata`) with the empty database and generate the script to create the schema.

    <!-- end list -->

    ```bash
    alembic revision --autogenerate -m "Initial database schema"
    ```

5.  **CRITICAL: Inspect the Generated Script:**

      * A new file will be created, e.g., `alembic/versions/xxxx_initial_database_schema.py`.
      * **Manually open and review this file carefully.** Verify that it correctly creates all tables, columns, data types, indexes, and foreign key constraints defined in `Adventorator/models.py`. Autogeneration is good but not infallible.
      * **Verification:** The script is generated without errors and its contents accurately reflect your `Base` models.

-----

#### **Step 4: Full Local Validation**

**Goal:** Confirm that the generated migration works and that the application runs correctly against the new Postgres schema.

1.  **Apply the Migration:**

      * Run the migration against your local Postgres container.

    <!-- end list -->

    ```bash
    alembic upgrade head
    ```

      * **Verification:** Connect to your database and confirm that all tables (`campaigns`, `players`, `characters`, etc.) now exist and have the correct structure.

2.  **Run Application and Tests:**

      * Ensure your `.env` file is pointing to the Postgres database.
      * Start the FastAPI application: `uvicorn Adventorator.app:app --reload`
      * Run the full test suite, ensuring it targets the Postgres database. You may need to configure `pytest` to use the environment variable.

    <!-- end list -->

    ```bash
    # Example of running pytest against Postgres
    DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/adventorator_test" pytest
    ```

      * **Verification:** The application starts and functions correctly. All tests pass when run against the Postgres database.

-----

#### **Step 5: Finalization and Documentation**

**Goal:** Clean up, update documentation, and merge the changes.

1.  **Update `README.md`:**
      * Add a "Development Setup" section explaining how to set up the local Postgres container and configure the `.env` file.
2.  **Commit and Merge:**
      * Commit all changes, including the new `alembic` directory, updated dependencies, and code modifications.
      * Open a Pull Request, allow CI to validate the changes, and merge to `main`.

This incremental and defensive plan ensures a safe and verifiable migration to Postgres, setting a solid foundation for all subsequent development.