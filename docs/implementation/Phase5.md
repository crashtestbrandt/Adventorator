### **Phase 5 Implementation Plan: Foundation & Narrative Intelligence**

**Overall Goal:** Evolve Adventorator from a prototype into a robust, deployable application with a core AI that is contextually aware of the characters in the world.

---

### **Pillar 1: Foundational Infrastructure**

#### **Milestone 5.1: Database Migration to Postgres**

* **Goal:** Migrate the application's persistence layer from SQLite to Postgres, enabling robust, concurrent data access suitable for production.
* **Key Tasks:**
    1.  Update project dependencies to include `asyncpg`.
    2.  Modify `Adventorator/config.py` to handle a `DATABASE_URL` with a `postgresql+asyncpg://` scheme.
    3.  Update `Adventorator/db.py` to include connection pool settings suitable for Postgres (e.g., `pool_size`, `max_overflow`, `pool_pre_ping`).
    4.  Initialize `alembic` for migration management (`alembic init`).
    5.  Configure `alembic/env.py` to recognize the SQLAlchemy models in `Adventorator/models.py`.
    6.  Generate the initial migration script (`alembic revision --autogenerate -m "Initial schema"`).
    7.  Validate that the generated script accurately reflects the models.

**Workload Characteristics**

This directly informs our pooling strategy.

  * **Interaction Pattern:** The workload is transactional and "spiky." Will receive a burst of requests when users in a guild are active, followed by periods of inactivity. It's not a constant, high-volume stream.
  * **Transaction Time:** Most database interactions are very fast: fetching a character, writing a transcript line, etc. These are sub-50ms operations.
  * **Concurrency Model:** Using `asyncio` with FastAPI. A single running application instance can handle hundreds of concurrent network requests (e.g., waiting for the LLM API). However, only a fraction of those will need a database connection at the exact same moment. The connection pool's job is to manage that fraction.

**The "Per-Instance" Sizing Strategy**

The most critical assumption is that we will **horizontally scale** the application, running multiple Docker containers of the FastAPI app behind a load balancer.

This means the database's `max_connections` limit must be shared by all of them. The formula is:

`(Total App Instances) * (Pool Size per Instance) < (DB max_connections)`

We must leave a buffer for administrative connections, maintenance tasks, and other services. A good rule of thumb is to allocate only 80-90% of `max_connections` to the application fleet.

We will define a pool size for a **single instance** that is efficient and doesn't hoard connections.

**Reasonable Assumptions & Starting Values**

These are designed to be a safe, efficient starting point for a single application instance.

| Parameter | Recommended Value | Justification |
| :--- | :--- | :--- |
| `pool_size` | `5` | An `asyncio` application can serve many requests concurrently, but most are I/O-bound on external APIs (like Discord or the LLM). A small pool of 5 active DB connections is typically sufficient to handle the database-bound work for a burst of requests without overwhelming the database. It's a classic, safe starting point. |
| `max_overflow` | `10` | This allows the pool to temporarily acquire up to 10 additional connections during a sudden, intense spike in traffic. It provides flexibility but is capped to prevent a single runaway instance from exhausting the entire database's connection limit. The total potential connections per instance is `pool_size + max_overflow` (15 in this case). |
| `pool_timeout` | `30` (seconds) | This is the maximum time a request will wait for a connection from the pool before throwing an error. 30 seconds is long enough to ride out a temporary spike but short enough to fail relatively quickly if the system is genuinely overloaded, preventing requests from hanging indefinitely. |
| `pool_pre_ping` | `True` | This is a crucial reliability feature for any long-running service. It sends a simple `SELECT 1` query to the database before checking out a connection to ensure it's still alive. This prevents errors from network blips, firewalls, or database restarts, at the cost of a tiny amount of latency. The trade-off is well worth it for production stability. |

**Implementation in `Adventorator/db.py`**

Modify the `get_engine` function:

```python
# Adventorator/db.py

def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        # Safer defaults per backend
        kwargs: dict[str, object] = {}
        if DATABASE_URL.startswith("sqlite+aiosqlite://"):
            # SQLite ignores pool_size; keep it minimal and avoid pre_ping
            kwargs.update(connect_args={"timeout": 30})
        else:
            # --- PRODUCTION POSTGRES CONFIGURATION ---
            # These values are configured per-instance.
            # Scale by running more instances.
            kwargs.update(
                pool_size=5,          # Number of connections to keep open in the pool
                max_overflow=10,      # Max connections to open beyond pool_size during spikes
                pool_timeout=30,      # Seconds to wait for a connection before timing out
                pool_pre_ping=True,   # Ensure connections are alive before use
            )
            # ------------------------------------------

        _engine = create_async_engine(DATABASE_URL, **kwargs)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine
```

**Scaling and Tuning Strategy (The Path Forward)**

These locked-in values are a starting point. The operational plan should include monitoring and tuning.

  * **Self-Hosted Users:** For people running their own instance, this configuration is robust and safe for a typical single-guild or multi-guild setup on a reasonable server.
  * **Managed Service:** As the managed service grows, monitor key metrics:
      * **Pool Statistics:** Monitor the number of active connections, total connections, and overflow connections per instance. If the instances are constantly using all 15 (5 + 10) connections, it's a sign we either need to increase the per-instance pool size or, more likely, add more application instances.
      * **DB CPU and Load:** If the database CPU is high even with low connection counts, the problem isn't the pool; it's inefficient queries or an undersized database.
      * **Future Scaling:** When we reach a very large number of application instances (e.g., 50+), we would introduce a server-side connection pooler like **PgBouncer**. It would sit between the app fleet and Postgres, managing a large pool of connections and handing them out to the instances in "transaction pooling" mode. This is the standard pattern for massive scale, but we do not need it for MVP. Current per-instance strategy will take us very far.

* **Definition of Done:**
    * The application runs successfully against a local Postgres database.
    * All existing unit and integration tests pass.
    * The `alembic upgrade head` command correctly creates the entire database schema from scratch.

---

#### **Milestone 5.2: Full Containerization for Development and CI/CD**
* **Goal:** Create a one-command `docker-compose up` environment that fully encapsulates the application and its database for streamlined local development and reliable CI testing.
* **Key Tasks:**
    1.  Create a `Dockerfile` for the Adventorator application. Use a multi-stage build to produce a lean production image.
    2.  Create a `docker-compose.yml` file defining two services: `app` (for the FastAPI application) and `db` (for Postgres).
    3.  Configure a named volume in `docker-compose.yml` to persist Postgres data across container restarts.
    4.  Configure the `app` service to use the `db` service for its `DATABASE_URL` via Docker's internal networking.
    5.  Update the CI/CD workflow (`.github/workflows/` or similar) to:
        * Build the Docker image.
        * Use `docker-compose` to spin up the `app` and `db` services.
        * Run tests from within the `app` container against the `db` container.
* **Open Questions / TODOs for Low-Level Planning:**
    * **TODO:** Finalize the production secrets management strategy. How will sensitive environment variables be injected in a real deployment environment (e.g., Kubernetes Secrets, cloud provider's secret manager)?
    * **TODO:** Design the specific test execution steps for the CI pipeline. Will it run `alembic upgrade head` before `pytest`? How will the database be cleaned up between test runs?
* **Definition of Done:**
    * A developer can clone the repository, run `docker-compose up`, and have a fully functional local environment.
    * The CI pipeline successfully builds the containers and runs the entire test suite against the containerized Postgres database on every commit.

---

### **Pillar 2: Core Architecture Refinements**

#### **Milestone 5.3: Rules Engine Encapsulation**

See: [Milestone 5.3 Low-Level Implementation Plan](./Phase5_Milestone3.md)

* **Goal:** Refactor the procedural rules functions into a formal, object-oriented `Ruleset` class to improve modularity, testability, and prepare for future multi-system support.
* **Key Tasks:**
    1.  Create a new module: `Adventorator/rules/engine.py`.
    2.  Define a `Ruleset` base class and a `Dnd5eRuleset` implementation.
    3.  Move the logic from `Adventorator/rules/checks.py` and `Adventorator/rules/dice.py` into methods on the `Dnd5eRuleset` class (e.g., `perform_check`, `roll_dice`).
    4.  Refactor the `/check` and `/roll` command handlers to use an instance of `Dnd5eRuleset`.
    5.  Use dependency injection: Add a `ruleset` attribute to the `Invocation` data class and instantiate it at the beginning of the command dispatch process in `app.py`.
* **Open Questions / TODOs for Low-Level Planning:**
    * **TODO:** Define the complete public API for the `Ruleset` class. What methods beyond `perform_check` are needed (e.g., `get_ability_modifier`, `get_proficiency_bonus`)?
    * **TODO:** Confirm the multi-system strategy. For Phase 5, we will hardcode the use of `Dnd5eRuleset` but design the base class interface to allow for future expansion. A factory is not needed yet.
* **Definition of Done:**
    * The logic from `rules/checks.py` and `rules/dice.py` now resides within the `Dnd5eRuleset` class.
    * All command handlers that perform rolls or checks do so via the `Ruleset` object passed in the `Invocation` context.
    * All related tests are updated and pass.

---
#### **Milestone 5.4: Mature Character Persistence Service**
* **Goal:** Abstract character data access behind a dedicated service layer, making it easy to load, cache, and resolve the active character for any given interaction.
* **Key Tasks:**
    1.  Create a new module: `Adventorator/services/character_service.py`.
    2.  Implement a `CharacterService` class that handles the logic for fetching character data from the repository layer (`repos.py`).
    3.  Implement a method `get_active_character_for_user(user_id: str, campaign_id: int) -> models.Character | None`. This will contain the logic for resolving the active character.
    4.  Implement a simple, in-memory TTL cache (e.g., using Python's `functools.lru_cache` with a time-based wrapper) within the service to reduce database queries for recently accessed characters.
    5.  Refactor the `/sheet show` and `/do` command handlers to use the new `CharacterService` instead of calling `repos.py` directly.
* **Open Questions / TODOs for Low-Level Planning:**
    * **TODO:** Decide and document the "active character" resolution strategy. Options include:
        1.  Player has only one character in the campaign.
        2.  Assume the most recently created/updated character.
        3.  Implement a `/character switch <name>` command to explicitly set the active character (persisted in a new table or field).
        *Decision for MVP should be the simplest path, likely Option 1 or 2.*
    * **TODO:** Define the caching strategy parameters (e.g., cache size, TTL in seconds).
* **Definition of Done:**
    * `CharacterService` is implemented and used by command handlers.
    * The "active character" resolution logic is implemented.
    * An in-memory cache is in place, demonstrably reducing redundant DB calls in tests.

---

### **Pillar 3: Core Capability Maturation**

#### **Milestone 5.5: Context-Aware Orchestrator**
* **Goal:** Enhance the LLM Narrator by providing it with the active character's core stats, enabling it to propose more intelligent, mechanically relevant, and personalized ability checks.
* **Key Tasks:**
    1.  Modify the `run_orchestrator` function signature to accept a `character_id`.
    2.  Inside `run_orchestrator`, use the `CharacterService` to load the full `CharacterSheet` for the given ID.
    3.  Create a new helper function, e.g., `summarize_sheet_for_prompt(sheet: CharacterSheet) -> str`, that generates a concise, token-efficient summary of the character's key stats.
    4.  Update `build_narrator_messages` in `llm_prompts.py` to include this summary in the context provided to the LLM.
    5.  Crucially, modify the `run_orchestrator` logic to populate the `CheckInput` for the `Ruleset` with the *actual stats from the loaded character sheet*, not default values or user input.
* **Open Questions / TODOs for Low-Level Planning:**
    * **TODO:** Design the exact format of the character summary for the prompt. It must be dense with useful information but low on tokens.
    * **TODO:** Define the token budgeting logic. When context is tight, what is prioritized: the character summary or the most recent transcript lines?
* **Definition of Done:**
    * The final prompt sent to the narrator LLM includes a summary of the active character.
    * The ability check performed by the orchestrator uses the real ability scores, proficiency bonus, and skill proficiencies from the character's sheet in the database.

---
#### **Milestone 5.6: Smarter Planner Enhancements**
* **Goal:** Improve the user experience of the `/act` command by gracefully handling ambiguous plans and providing clearer guidance for commands that require arguments.
* **Key Tasks:**
    1.  **Argument Prompting:**
        * Modify the `/act` command's logic. If the planner returns a valid command (e.g., `sheet.create`) but is missing required arguments (`args` is empty), the handler should not fail silently.
        * Instead, it will send an ephemeral follow-up message guiding the user. E.g., "To create a character, please use the `/sheet create` command with the required `json` option."
    2.  **Disambiguation (Stretch Goal):**
        * Enhance the `PlannerOutput` schema with an optional `confidence: float` score.
        * Update the planner prompt to ask the LLM to provide a confidence score.
        * In the `/act` handler, if confidence is below a defined threshold, send an ephemeral follow-up message with Discord buttons offering the top 2-3 most likely commands as choices.
* **Open Questions / TODOs for Low-Level Planning:**
    * **TODO:** What is the specific confidence threshold for triggering disambiguation? (e.g., `< 0.75`).
    * **TODO:** Is the "Argument Prompting" guidance sufficient for the MVP, or is a full conversational flow necessary? *Decision for MVP: The simple guidance message is sufficient. A conversational flow is out of scope for Phase 5.*
* **Definition of Done:**
    * `/act create character` no longer fails but instead replies with a helpful message guiding the user to `/sheet create`.
    * (Stretch) The `/act` command can present disambiguation buttons to the user on a low-confidence plan.