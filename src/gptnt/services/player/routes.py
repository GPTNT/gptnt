import structlog
import wandb
from fastapi import APIRouter, BackgroundTasks, HTTPException, Response, status
from pydantic import BaseModel

from gptnt.players.ai.input_builder import AgentInputBuilder
from gptnt.players.ai.message_history import MessageHistory
from gptnt.players.prompts.reflection import ReflectionMessage
from gptnt.players.specification import PlayerProtocol
from gptnt.services.events.player import PlayerMessage, PlayerState, StopPlayerEvent
from gptnt.services.experiment_descriptor import ExperimentDescriptor
from gptnt.services.player.lifespan import MessageManagerDep, PlayerSupervisorDep

logger = structlog.get_logger()
router = APIRouter()


@router.get("/health")
async def health_check() -> bool:
    """Health check endpoint for the player service."""
    return True


@router.get("/state")
async def get_player_state(supervisor: PlayerSupervisorDep) -> PlayerState:
    """Get the current state of the player service."""
    return supervisor.state


@router.post("/send-message")
async def handle_new_message(
    message: PlayerMessage[str], *, message_handler: MessageManagerDep
) -> None:
    """Receive a message from a player."""
    _ = message_handler.handle_new_message(message.message)


@router.post("/send-feedback")
async def handle_feedback(
    feedback: PlayerMessage[str], *, message_handler: MessageManagerDep
) -> None:
    """Receive feedback from a player."""
    _ = message_handler.handle_new_message(feedback.message)
    # TODO: Track the feedback in the tracker?


class _ConfigureExperimentPayload(BaseModel):
    protocol: PlayerProtocol
    experiment_descriptor: ExperimentDescriptor


@router.post("/configure-for-experiment")
async def configure_for_experiment(
    data: _ConfigureExperimentPayload, *, supervisor: PlayerSupervisorDep
) -> None:
    """Configure the player service for an experiment."""
    protocol: PlayerProtocol = data.protocol
    experiment_descriptor: ExperimentDescriptor = data.experiment_descriptor

    if supervisor.state > PlayerState.idle:
        raise HTTPException(
            status_code=500, detail="Player is not ready for experiment configuration."
        )
    supervisor.state = PlayerState.configuring_experiment

    logger.info(
        "Set state to configuring experiment",
        service_name=supervisor.service_name,
        state=supervisor.state,
    )

    supervisor.protocol = protocol
    supervisor.experiment_descriptor = experiment_descriptor
    await supervisor.episode_tracker.configure_for_experiment(
        experiment_descriptor=supervisor.experiment_descriptor,
        protocol=supervisor.protocol,
        player_uuid=supervisor.uuid,
        additional_metadata={},
    )

    supervisor.message_history = MessageHistory(
        capabilities=supervisor.capabilities, protocol=protocol
    )
    supervisor.input_builder = AgentInputBuilder(
        capabilities=supervisor.capabilities,
        protocol=protocol,
        message_history=supervisor.message_history,
        observation_handler=supervisor.observation_handler,
    )

    supervisor.action_predictor.configure_for_experiment(
        protocol=protocol,
        message_history=supervisor.message_history,
        tracker=supervisor.episode_tracker,
    )
    supervisor.action_dispatcher.configure_for_experiment(
        protocol=protocol, experiment_descriptor=experiment_descriptor
    )

    if protocol.role == "defuser":
        supervisor.game_client.recreate_client(url=experiment_descriptor.game_url)

    if other_player_url := experiment_descriptor.get_url_for_other_role(
        current_role=protocol.role
    ):
        supervisor.message_manager.recreate_client(url=other_player_url)

    supervisor.state = PlayerState.waiting_for_turn
    logger.info("Configured player for experiment", protocol=protocol, state=supervisor.state)


@router.post("/forward")
async def forward_pass(player_supervisor: PlayerSupervisorDep) -> None:
    """Perform a forward pass for the player.

    Note that this can be a long-running operation so it needs to be handled a bit carefully. We
    shouldn't be blocking the main thread and I know that this is a no-no but we want to ensure
    that this is a closed loop, essentially so the caller waits for this response before sending
    more. We do not want to have multiple forward passes in flight at the same time.
    """
    if player_supervisor.state != PlayerState.waiting_for_turn:
        raise HTTPException(status_code=503, detail="Player is not ready for a forward pass.")

    # Collect the state and the observations
    player_supervisor.state = PlayerState.pulling_messages
    messages = player_supervisor.message_manager.pull_messages()

    if player_supervisor.protocol.role == "defuser":
        player_supervisor.state = PlayerState.waiting_for_observation
        bomb_state, raw_frames = await player_supervisor.game_client.get_observation()
    else:
        bomb_state, raw_frames = None, None

    # Prepare the input
    player_supervisor.state = PlayerState.preparing_agent_input
    agent_input = await player_supervisor.input_builder.build_agent_input(
        messages=messages,
        raw_frames=raw_frames,
        bomb_state=bomb_state,
        is_message_history_empty=player_supervisor.message_history.is_empty,
    )
    # decide what action to do
    player_supervisor.state = PlayerState.waiting_for_action
    action_to_perform = await player_supervisor.action_predictor.send_request_to_agent(
        message_input=agent_input
    )

    # perform the action
    player_supervisor.state = PlayerState.performing_action
    # Note: if this fails, everything crashes
    await player_supervisor.action_dispatcher.direct_output_from_agent(action_to_perform.output)

    player_supervisor.episode_tracker.num_requests += 1
    player_supervisor.episode_tracker.step()

    # Return to a waiting for turn state
    player_supervisor.state = PlayerState.waiting_for_turn


@router.post("/reflection")
async def perform_reflection(
    message: PlayerMessage[ReflectionMessage], *, player_supervisor: PlayerSupervisorDep
) -> None:
    """Perform a reflection for the player."""
    if player_supervisor.state != PlayerState.waiting_for_turn:
        raise HTTPException(
            status_code=503,
            detail=f"Player is not ready for a reflection. They are: {player_supervisor.state.name}",
        )

    player_supervisor.state = PlayerState.reflecting
    await player_supervisor.action_predictor.send_reflection_request(
        reflection_message=message.message
    )


@router.post("/reset")
async def reset(player_supervisor: PlayerSupervisorDep) -> None:
    """Reset the player service."""
    player_supervisor.reset()


async def _stop_player(
    *, player_supervisor: PlayerSupervisorDep, stop_event: StopPlayerEvent
) -> None:
    """Stop the experiment tracking."""
    if not hasattr(player_supervisor, "protocol"):
        logger.error("Can't stop player, player was not setup properly")
        player_supervisor.reset()
        return

    # Add the final bomb state for the defuser
    if player_supervisor.protocol.role == "defuser" and stop_event.bomb_state:
        player_supervisor.episode_tracker.add_bomb_state(stop_event.bomb_state)

    # Update some states
    player_supervisor.episode_tracker.num_prompt_truncations = (
        player_supervisor.message_history.num_times_truncated
    )

    # Stop the experiment tracking (in the bg)
    player_supervisor.state = PlayerState.uploading
    try:
        await player_supervisor.episode_tracker.on_experiment_stop(
            is_hard_crash=stop_event.hard_crash
        )
    except wandb.Error as err:
        if err.message == "You must call wandb.init() before wandb.log()":
            logger.warning("It seems like the run was never started, skipping finish??")
        else:
            logger.exception("Error finishing WandB run", error=err)

    # Reset the state
    player_supervisor.reset()


@router.post("/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_player(
    stop_event: StopPlayerEvent,
    player_supervisor: PlayerSupervisorDep,
    background_tasks: BackgroundTasks,
) -> Response:
    """Stop the player and end the experiment.

    We respond quickly with a 202 and let this run in the background because wandb can block and
    take a while to finish. The EpisodeTracker will already run wandb in a background thread but we
    don't want to block API calls while waiting for the experiment to finish.

    This is less important in context of an experiment since the heartbeats are done completely
    separately by a supervisor, but it is still a good practice to not block the API.
    """
    logger.info("Stopping player and ending experiment")
    player_supervisor.state = PlayerState.stopping
    background_tasks.add_task(
        _stop_player, player_supervisor=player_supervisor, stop_event=stop_event
    )
    return Response(
        status_code=status.HTTP_202_ACCEPTED,
        headers={"X-Reason": "Stopping player and ending experiment"},
    )
