import httpx
import structlog
from fastapi import APIRouter, HTTPException

from gptnt.ktane.actions import KtaneAction
from gptnt.ktane.client import RawObservationFrames
from gptnt.ktane.mission_spec import KtaneMissionSpec
from gptnt.ktane.state.bomb import BombState
from gptnt.ktane.state.game import GameState
from gptnt.services.events.heartbeat import ReadyState
from gptnt.services.game.lifespan import (
    GameProcessManagerDep,
    GameStateMonitorDep,
    GameSupervisorDep,
    KtaneClientDep,
)
from gptnt.services.timeouts import ServiceTimeouts

logger = structlog.get_logger()
service_timeouts = ServiceTimeouts()
router = APIRouter()


@router.get("/health")
async def health_check() -> bool:
    """Health check endpoint, just to know the service is alive."""
    return True


@router.get("/state")
async def get_game_state(state_monitor: GameStateMonitorDep) -> GameState:
    """Get the current state of the game."""
    return state_monitor.state.value


@router.post("/configure-experiment")
async def configure_experiment(
    spec: KtaneMissionSpec, ktane_client: KtaneClientDep, state_monitor: GameStateMonitorDep
) -> bool:
    """Configure a new experiment."""
    if state_monitor.state.value != GameState.main_menu:
        raise HTTPException(
            status_code=400,
            detail="Game is not in setup state, cannot configure experiment. Try to reset the game first.",
            headers={
                "X-Reason": f"Invalid game state for creating a new experiment. Expected 'Setup', got '{state_monitor.state.value}'"
            },
        )

    try:
        _ = await ktane_client.start_mission(spec)
    except httpx.HTTPStatusError as err:
        logger.exception(
            "Failed to start mission",
            spec=spec,
            reason=err.response.text,
            request=err.response.request,
            state_history=state_monitor.history,
            light_on_event=state_monitor.first_lights_on.is_set(),
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to start the mission",
            headers={"X-Reason": err.response.text},  # noqa: WPS204
        ) from err

    _ = await state_monitor.first_lights_off.wait()
    return await ktane_client.stop_time()


@router.post("/stop-experiment")
async def stop_experiment(
    game_supervisor: GameSupervisorDep,
    process_manager: GameProcessManagerDep,
    state_monitor: GameStateMonitorDep,
) -> bool:
    """Stop the current experiment."""
    # If we are not ready, it means the game has already been rebooted and should not be rebooted
    # again otherwise it will just hang forever. Therefore only terminate the process is we are in
    # the ready state. If we are not ready, the GameSupervisor will take care of it.
    if game_supervisor.ready_state == ReadyState.ready:
        await process_manager.terminate()
    state_monitor.reset()
    return True


@router.post("/pause")
async def pause_game(ktane_client: KtaneClientDep) -> bool:
    """Pause the game."""
    try:
        return await ktane_client.stop_time()
    except httpx.HTTPStatusError as err:
        logger.exception(
            "Failed to pause the game", reason=err.response.text, request=err.response.request
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to pause the game",
            headers={"X-Reason": err.response.text},
        ) from err


@router.post("/unpause")
async def unpause_game(ktane_client: KtaneClientDep) -> bool:
    """Unpause the game."""
    try:
        return await ktane_client.resume_time()
    except httpx.HTTPStatusError as err:
        logger.exception(
            "Failed to unpause the game", reason=err.response.text, request=err.response.request
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to unpause the game",
            headers={"X-Reason": err.response.text},
        ) from err


@router.post("/reset")
async def reset_game(ktane_client: KtaneClientDep) -> bool:
    """Reset the game."""
    try:
        return await ktane_client.go_to_main_menu()
    except httpx.HTTPStatusError as err:
        logger.exception(
            "Failed to return to the main menu",
            reason=err.response.text,
            request=err.response.request,
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to return to the main menu",
            headers={"X-Reason": err.response.text},
        ) from err


@router.post("/advance-time")
async def advance_time(ktane_client: KtaneClientDep) -> bool:
    """Advance the game time."""
    try:
        return await ktane_client.advance_time()
    except httpx.HTTPStatusError as err:
        logger.exception(
            "Failed to advance the time", reason=err.response.text, request=err.response.request
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to advance the time",
            headers={"X-Reason": err.response.text},
        ) from err


@router.post("/set-game-speed")
async def set_game_speed(ktane_client: KtaneClientDep, speed: float | None = None) -> bool:
    """Set the game speed."""
    try:
        return await ktane_client.set_game_speed(speed=speed)
    except httpx.HTTPStatusError as err:
        logger.exception(
            "Failed to set game speed", reason=err.response.text, request=err.response.request
        )
        raise HTTPException(
            status_code=503,
            detail="Failed to set game speed",
            headers={"X-Reason": err.response.text},
        ) from err


@router.post("/send-action")
async def send_action(action: KtaneAction, ktane_client: KtaneClientDep) -> bool:
    """Send an action to the game."""
    try:
        return await ktane_client.send_action(action=action)
    except httpx.HTTPStatusError as err:
        # logger.exception(
        #     "Failed to send action",
        #     action=action,
        #     reason=err.response.text,
        #     request=err.response.request,
        # )
        raise HTTPException(
            status_code=503,
            detail="Failed to send the action",
            headers={"X-Reason": err.response.text},
        ) from err


@router.get("/bomb-state")
async def get_bomb_state(ktane_client: KtaneClientDep) -> BombState:
    """Get the current state of the bomb."""
    try:
        bomb_state = await ktane_client.get_bomb_state()
    except httpx.RequestError as request_err:
        raise HTTPException(
            status_code=503, detail="Failed to REQUEST bomb state"
        ) from request_err
    except httpx.HTTPStatusError as err:
        raise HTTPException(
            status_code=503,
            detail="Failed to RECEIVE bomb state",
            headers={"X-Reason": err.response.text},
        ) from err

    return bomb_state


@router.get("/observation-frames")
async def get_observation_frames(ktane_client: KtaneClientDep) -> RawObservationFrames:
    """Get the raw observation frames from the game."""
    try:
        return await ktane_client.get_observation_frames()
    except httpx.RequestError as request_err:
        raise HTTPException(
            status_code=503, detail="Failed to REQUEST observation frames"
        ) from request_err
    except httpx.HTTPStatusError as response_err:
        raise HTTPException(
            status_code=503,
            detail="Failed to RECEIVE observation frames",
            headers={"X-Reason": response_err.response.text},
        ) from response_err
