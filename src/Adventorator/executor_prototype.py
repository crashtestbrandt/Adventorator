"""Simple executor prototype demonstrating idempotency key v2 reuse (STORY-CDA-CORE-001D)."""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime, timezone

from Adventorator.events.envelope import compute_idempotency_key_v2, compute_payload_hash
from Adventorator.events.envelope import GENESIS_SCHEMA_VERSION


@dataclass
class ExecutorRequest:
    """Request for executor operation."""
    plan_id: str
    campaign_id: int
    tool_name: str
    ruleset_version: str
    args_json: Dict[str, Any]
    actor_id: str
    scene_id: int


@dataclass
class ExecutorResult:
    """Result of executor operation."""
    event_id: Optional[int]
    idempotency_key: bytes
    payload: Dict[str, Any]
    was_reused: bool
    error: Optional[str] = None


class SimpleExecutorPrototype:
    """Simplified executor demonstrating idempotency key v2 reuse.
    
    This prototype shows how the executor path should handle retry storms
    by checking for existing events with the same idempotency key before
    creating new ones.
    """
    
    def __init__(self, db_session):
        self.db = db_session
        
    async def execute_with_idempotency(self, request: ExecutorRequest) -> ExecutorResult:
        """Execute operation with idempotency check.
        
        This demonstrates the core logic for STORY-CDA-CORE-001D:
        1. Compute idempotency key from operation parameters
        2. Check if event already exists with this key
        3. If exists, return existing event (idempotent reuse)
        4. If not exists, execute operation and create new event
        """
        
        # Step 1: Compute idempotency key using v2 composition
        idempotency_key = compute_idempotency_key_v2(
            plan_id=request.plan_id,
            campaign_id=request.campaign_id,
            event_type="tool.execute",
            tool_name=request.tool_name,
            ruleset_version=request.ruleset_version,
            args_json=request.args_json,
        )
        
        # Step 2: Check for existing event with this idempotency key
        existing_event = await self._find_existing_event(
            request.campaign_id, idempotency_key
        )
        
        if existing_event:
            # Step 3: Return existing event (idempotent reuse)
            # TODO: Increment events.idempotent_reuse metric here
            return ExecutorResult(
                event_id=existing_event.id,
                idempotency_key=idempotency_key,
                payload=existing_event.payload,
                was_reused=True,
            )
        
        # Step 4: Execute operation and create new event
        try:
            # Simulate tool execution
            execution_result = await self._execute_tool(request)
            
            # Create new event
            event = await self._create_event(
                request, idempotency_key, execution_result
            )
            
            return ExecutorResult(
                event_id=event.id,
                idempotency_key=idempotency_key,
                payload=execution_result,
                was_reused=False,
            )
            
        except Exception as e:
            return ExecutorResult(
                event_id=None,
                idempotency_key=idempotency_key,
                payload={},
                was_reused=False,
                error=str(e),
            )
    
    async def _find_existing_event(self, campaign_id: int, idempotency_key: bytes):
        """Find existing event with the given idempotency key."""
        from sqlalchemy import select
        from Adventorator import models
        
        stmt = select(models.Event).where(
            models.Event.campaign_id == campaign_id,
            models.Event.idempotency_key == idempotency_key
        )
        return await self.db.scalar(stmt)
    
    async def _execute_tool(self, request: ExecutorRequest) -> Dict[str, Any]:
        """Simulate tool execution (placeholder implementation)."""
        
        # Simple tool simulation based on tool name
        if request.tool_name == "dice_roll":
            sides = request.args_json.get("sides", 20)
            count = request.args_json.get("count", 1) 
            modifier = request.args_json.get("modifier", 0)
            
            # Simulate dice roll (deterministic for testing)
            import random
            random.seed(hash(str(request.args_json)))
            total = sum(random.randint(1, sides) for _ in range(count)) + modifier
            
            return {
                "tool": "dice_roll",
                "result": total,
                "details": f"{count}d{sides}+{modifier} = {total}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
        elif request.tool_name == "spell_check":
            spell = request.args_json.get("spell", "unknown")
            level = request.args_json.get("level", 1)
            
            return {
                "tool": "spell_check",
                "spell": spell,
                "level": level,
                "valid": True,  # Simplified validation
                "description": f"Level {level} {spell} spell",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
        else:
            return {
                "tool": request.tool_name,
                "result": "executed",
                "args": request.args_json,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    
    async def _create_event(
        self, request: ExecutorRequest, idempotency_key: bytes, payload: Dict[str, Any]
    ):
        """Create new event in the database."""
        from Adventorator import models
        
        # Get latest replay ordinal for proper sequencing
        latest_ordinal = await self._get_latest_replay_ordinal(request.campaign_id)
        
        event = models.Event(
            campaign_id=request.campaign_id,
            scene_id=request.scene_id,
            replay_ordinal=latest_ordinal + 1,
            type="tool.execute",
            event_schema_version=GENESIS_SCHEMA_VERSION,
            world_time=latest_ordinal + 1,  # Simplified world time
            wall_time_utc=datetime.now(timezone.utc),
            prev_event_hash=b'\x00' * 32,  # Simplified for prototype
            payload_hash=compute_payload_hash(payload),
            idempotency_key=idempotency_key,
            actor_id=request.actor_id,
            plan_id=request.plan_id,
            execution_request_id=None,  # Not used in v2 idempotency
            approved_by=None,
            payload=payload,
            migrator_applied_from=None,
        )
        
        self.db.add(event)
        await self.db.flush()
        
        return event
    
    async def _get_latest_replay_ordinal(self, campaign_id: int) -> int:
        """Get latest replay ordinal for campaign (simplified)."""
        from sqlalchemy import select, func
        from Adventorator import models
        
        stmt = select(func.max(models.Event.replay_ordinal)).where(
            models.Event.campaign_id == campaign_id
        )
        result = await self.db.scalar(stmt)
        return result or 0