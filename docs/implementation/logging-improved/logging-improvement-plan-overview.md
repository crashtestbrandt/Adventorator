
### **Project Plan: Enhanced Application Logging**

#### **1. Overview**

This document outlines a phased, incremental plan to comprehensively enhance the logging infrastructure of the Adventorator application. The primary goal is to improve observability, traceability, and debuggability across all system components.

By adhering to a defensive programming mindset and modern logging best practices, this effort will produce a robust, structured logging foundation that is invaluable for both development and production operations.

---

#### **2. Guiding Principles & Guardrails**

All implementation work carried out under this plan must adhere to the following principles:

*   **Standardize on Structured Logging:** All log entries must be in a machine-parseable format (JSON). `structlog` is the standard; avoid using unstructured string formatting (e.g., f-strings or `%` formatting) in log messages. All contextual data must be passed as key-value pairs.
*   **Ensure Complete Traceability:** Every log entry generated as part of a request-response cycle must be associated with a unique `request_id`. This is non-negotiable and forms the backbone of our ability to trace operations.
*   **Log at System Boundaries:** Every point of interaction with an external system (Discord API, LLM provider, Database) is a potential point of failure. These boundaries must be logged with details of the request, the response, and latency.
*   **Log Decision Points, Not Just Actions:** Log the *why* behind an action. For example, log the full proposal from an LLM that was rejected by a defensive gate, not just the fact that a rejection occurred.
*   **Use Log Levels Appropriately:**
    *   `DEBUG`: Granular information for deep debugging (e.g., individual function calls, rules engine calculations). Should be disabled in production.
    *   `INFO`: High-level information about the normal flow of the application (e.g., request received, command executed, LLM call completed). This is the default production level.
    *   `WARNING`: Indicates a potential issue or an unexpected but handled event (e.g., LLM response failed validation, a defensive gate was triggered).
    *   `ERROR`: A significant failure that prevented an operation from completing (e.g., an unhandled exception, database connection failure, failed signature verification).
*   **Protect Sensitive Data:** Under no circumstances should secrets (API keys, tokens), user passwords, or excessive Personally Identifiable Information (PII) be logged in plain text. Implement redaction for configuration logs and be mindful of what is included from data payloads.

---

#### **3. Incremental Implementation Plan**

This work is divided into five distinct phases, which should be implemented in order.

##### **Phase 0: Foundational Enhancements**

**Objective:** Establish the core infrastructure for traceable and context-rich logging.

*   **Task 0.1: Implement Request-ID Middleware for Traceability**
    *   **Objective:** To generate and propagate a unique identifier for every incoming HTTP request.
    *   **Key Actions:**
        1.  Create a new FastAPI middleware.
        2.  In the middleware, generate a unique `request_id` (e.g., UUIDv4) for each request.
        3.  Use `structlog.contextvars` to bind the `request_id` to the logging context for the duration of the request.
        4.  Implement a high-level request log entry upon response completion, capturing the final status code and overall duration.
        5.  (Optional but recommended) Add the `request_id` to the HTTP response headers (e.g., `X-Request-ID`) to correlate with client-side or upstream logs.
    *   **Location(s):** A new middleware file (e.g., `Adventorator/middleware.py`); `Adventorator/app.py` to register the middleware.
    *   **Key Log Fields:** `request_id`, `http_path`, `http_method`, `http_status_code`, `duration_ms`.
    *   **Success Criteria:** Every log line generated from handling a single Discord interaction shares the same `request_id`.

*   **Task 0.2: Implement Startup Configuration Logging**
    *   **Objective:** To create a definitive record of the application's configuration at launch time.
    *   **Key Actions:**
        1.  Immediately after the `Settings` object is loaded, create a structured log entry at the `INFO` level.
        2.  The payload of this log entry should be the entire settings object.
        3.  **Crucially**, ensure that all sensitive fields are redacted before logging. A succinct format for this is `"[REDACTED]"`. Fields to redact include `llm_api_key`, `discord_bot_token`, and `discord_public_key`.
    *   **Location(s):** `Adventorator/app.py`.
    *   **Key Log Fields:** `config` (containing the nested, redacted settings object).
    *   **Success Criteria:** A single, clearly identifiable log entry is present at the beginning of the log file containing the application's startup configuration with secrets redacted.

---

##### **Phase 1: Critical Boundaries (Discord & LLM)**

**Objective:** Gain full visibility into all interactions with external services.

*   **Task 1.1: Enhance Discord API Interaction Logging**
    *   **Objective:** To audit and debug every incoming request from Discord.
    *   **Key Actions:**
        1.  Log the initial receipt of a request *before* signature validation.
        2.  Enhance existing error logs for signature failures to ensure they are structured.
        3.  Log the successfully parsed and validated `Interaction` object as a structured payload.
        4.  Add an error log for cases where the request body is not valid JSON or fails Pydantic validation.
    *   **Location(s):** `Adventorator/app.py` (within the `/interactions` endpoint).
    *   **Key Log Fields:** `interaction` (the full, model-dumped object), `raw_body_preview` (on parsing failure).
    *   **Success Criteria:** The lifecycle of an incoming Discord webhook—receipt, validation, parsing—is clearly visible in the logs.

*   **Task 1.2: Implement Comprehensive LLM Client Call Logging**
    *   **Objective:** To monitor the performance, cost, and correctness of all LLM interactions.
    *   **Key Actions:**
        1.  Create a log entry *before* an API call is made to the LLM provider. This "initiated" entry should include key parameters of the request.
        2.  Wrap the API call to measure its duration.
        3.  Create a log entry *after* the call completes. This "completed" entry should include the duration and status (e.g., `success`, `api_error`, `validation_failed`).
        4.  For successful calls that produce structured JSON, log key parts of the validated output (e.g., the `proposal` object). For failures, log any available error details.
    *   **Location(s):** `Adventorator/llm.py` (within `generate_response` and `generate_json`).
    *   **Key Log Fields:** `provider`, `model`, `duration_ms`, `prompt_messages`, `prompt_approx_chars`, `response_proposal`, `status`.
    *   **Success Criteria:** Every LLM API call is bookended by "initiated" and "completed" log entries containing performance metrics and contextual data.

---

##### **Phase 2: Core Logic & Decision Points (Orchestrator & Planner)**

**Objective:** To understand the internal decision-making processes of the application's intelligent components.

*   **Task 2.1: Log Planner Logic and Decisions**
    *   **Objective:** To trace how natural language input is converted into a structured application command.
    *   **Key Actions:**
        1.  Inside the `plan` function, log the initiation of a planning request with the user's message.
    2.  Log the successfully parsed and validated `Plan` (single-step) object (legacy `PlannerOutput` adapter retained only for backward compatibility).
        3.  Log any failures during JSON extraction or Pydantic validation of the LLM's response.
    4.  Review the existing `planner.decision` logs in `commands/plan.py` and ensure they correctly inherit the `request_id` from the context.
    *   **Location(s):** `Adventorator/planner.py`; `Adventorator/commands/plan.py`.
    *   **Key Log Fields:** `user_msg`, `plan` (the full output object), `raw_text_preview` (on failure).
    *   **Success Criteria:** We can follow the data flow from a raw user string to a validated `Plan` object and see the final accepted/rejected decision.

*   **Task 2.2: Log Orchestrator Defensive Gate Rejections**
    *   **Objective:** To monitor the effectiveness of security and safety checks on LLM-generated content.
    *   **Key Actions:**
        1.  Standardize the existing `llm.defense.rejected` log events.
        2.  For every rejection (`_validate_proposal`, `_contains_banned_verbs`, `_unknown_actor_present`), the log entry must include the specific reason for rejection.
        3.  The log entry must also include the full `LLMOutput` object that was rejected, providing complete context for why the gate was triggered.
    *   **Location(s):** `Adventorator/orchestrator.py` (within `run_orchestrator`).
    *   **Key Log Fields:** `reason` (e.g., `unsafe_verb`, `unknown_actor`), `proposal` (object), `narration` (string).
    *   **Success Criteria:** Every time an LLM proposal is denied by the orchestrator, a `WARNING` log is generated with sufficient detail to analyze the model's behavior.

---

##### **Phase 3: Command Dispatch & Execution**

**Objective:** Create a clear audit trail of all commands executed by the application.

*   **Task 3.1: Log Command Invocation Lifecycle**
    *   **Objective:** To know which commands are being run, by whom, with what arguments, and whether they succeeded.
    *   **Key Actions:**
        1.  In the central command dispatcher, log the initiation of a command *before* its handler is called. This entry should include the command name, subcommand, and all user-provided options.
        2.  Wrap the call to the command's handler to measure duration.
        3.  After the handler completes, log a "completed" event with the duration and a status of `success`.
        4.  If the handler raises an exception, catch it, log a "completed" event with a status of `error` and the exception info, and then re-raise or handle as appropriate.
    *   **Location(s):** `Adventorator/app.py` (within `_dispatch_command`).
    *   **Key Log Fields:** `command_name`, `subcommand`, `options`, `user_id`, `guild_id`, `status` (`success`/`error`), `duration_ms`.
    *   **Success Criteria:** Every slash command execution results in clear "initiated" and "completed" log entries.

---

##### **Phase 4: Supporting Systems (Rules & Database)**

**Objective:** Add targeted, low-level logging for deep debugging without creating excessive noise.

*   **Task 4.1: Add DEBUG-Level Rules Engine Logging**
    *   **Objective:** To enable detailed tracing of game mechanic calculations during development.
    *   **Key Actions:**
        1.  Add log statements at the `DEBUG` level to the `compute_check` and `DiceRNG.roll` functions.
        2.  These logs should capture the complete inputs to the function and the final computed result object.
    *   **Location(s):** `Adventorator/rules/checks.py`; `Adventorator/rules/dice.py`.
    *   **Key Log Fields:** `inputs` (object), `result` (object).
    *   **Success Criteria:** When the application log level is set to `DEBUG`, the logs contain detailed traces of all dice rolls and ability checks. These logs are absent at the `INFO` level.

*   **Task 4.2: Add General Database Error Logging**
    *   **Objective:** To ensure any unexpected database-layer exception is captured.
    *   **Key Actions:**
        1.  In the `session_scope` context manager, add a structured `ERROR` log entry within the `except` block.
        2.  This log should capture the full exception information before the session is rolled back.
    *   **Location(s):** `Adventorator/db.py`.
    *   **Key Log Fields:** `exc_info`.
    *   **Success Criteria:** A database error that causes a transaction to fail (e.g., constraint violation, deadlock) generates a structured error log with a stack trace.

---

#### **4. Validation and Review**

Upon completion of all phases, a final validation pass is required:

1.  **Run a Suite of Commands:** Execute every major command in the application (`/plan`, `/do`, `/roll`, `/sheet`, etc.).
2.  **Review Log Output:** Inspect the generated `adventorator.jsonl` file.
3.  **Confirm against Checklist:**
    *   [ ] Does every log entry related to a request have a `request_id`?
    *   [ ] Is the startup configuration logged correctly with secrets redacted?
    *   [ ] Are log levels used appropriately (e.g., no `DEBUG` messages at `INFO` level)?
    *   [ ] Is all log output valid JSON?
    *   [ ] Are there any instances of sensitive information being leaked?
    *   [ ] Can you successfully trace a single `/plan` command from the initial Discord request through the Planner, LLM calls, and final command dispatch using its `request_id`?