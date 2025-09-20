"""In-process simulation adapter placeholders."""

from __future__ import annotations

from ..interfaces import RaycastRequest, RaycastResponse


class InProcessSimulationAdapter:
    """Stubbed simulation adapter for future expansion."""

    def raycast(self, request: RaycastRequest) -> RaycastResponse:
        # Local scaffolding returns a miss to avoid introducing new mechanics yet.
        return RaycastResponse(hit=False, point=None)
