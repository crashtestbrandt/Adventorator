# Revised ooc.py Flow Plan

## New Proposed Flow

1. **Receive player input message**
    - Send deferred response to player immediately (e.g., "Processing...").
2. **Initial safety-parsing checks**
    - Ensure message is safe to process further (ensure safe to handle for submitting to database, injection attempts, etc.).
3. **Write message to transcript database with `status='pending'`**
    - Guarantees all player input is recorded, even if later steps fail.
4. **Perform all validations, fetch history, and call the LLM**
    - If any step fails:
        - Update transcript status to `error`
        - Inform the user and exit
    - Validations include:
        - Basic message sanity (e.g., not empty, not obviously malicious)
        - Handling odd/short responses (e.g., "yes", "no")—define policy for these
        - Campaign, scene, valid-actors, inventory checks, etc.
5. **Send Response**
    - Write the LLM response to the transcript with `status='pending'`.
        - Validate LLM response - various levels of checks (structure, content, context relevance, rule adherence, etc).
    - Attempt to send the response to the player.
    - If successful, update transcript status for both messages to `complete`.
    - If sending fails, update transcript status for both messages to `error` and log the issue.

---

## Notes

- The `status` field (`pending`, `complete`, `error`) enables robust recovery and debugging.
- Policy for handling short/odd responses should be defined (e.g., prompt for clarification, reject, or accept as-is).
- All transcript updates should be atomic where possible to avoid partial/inconsistent states.
