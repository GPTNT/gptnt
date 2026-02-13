from __future__ import annotations

import abc
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from functools import partial
from typing import TYPE_CHECKING, override

import anyio
import httpx
import logfire
import structlog

from gptnt.common.async_ops import Event
from gptnt.prompts.reflection import convert_bomb_state_to_reflection
from gptnt.services.experiment_manager.service_state_watcher import (
    GameStateWatcher,
    PlayerStateWatcher,
)
from gptnt.services.game.client import GameClient
from gptnt.services.player.client import PlayerClient
from gptnt.services.timeouts import ServiceTimeouts

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from coredis import Redis
    from faststream.redis import RedisBroker

    from gptnt.ktane.state.bomb import BombState
    from gptnt.services.experiment_descriptor import ExperimentDescriptor

logger = structlog.get_logger()
timeouts = ServiceTimeouts()


class ExperimentState(IntEnum):
    """State of the experiment."""

    initialising = 0
    running = 1
    post_game = 2
    cleanup = 3
    done = 4


@dataclass(kw_only=True)
class ExperimentRunner(abc.ABC):
    """Handle the lifecycle of the experiment."""

    experiment: ExperimentDescriptor
    game_client: GameClient = field(init=False)
    """Game client to interact with the game service."""
    defuser_player_client: PlayerClient = field(init=False)
    """Player client to interact with the Defuser."""
    expert_player_client: PlayerClient | None = field(default=None, init=False, repr=False)
    """Player client to interact with the Expert."""

    state: ExperimentState = field(default=ExperimentState.initialising, init=False)

    game_state_watcher: GameStateWatcher = field(init=False, repr=False)
    defuser_state_watcher: PlayerStateWatcher = field(init=False, repr=False)
    expert_state_watcher: PlayerStateWatcher | None = field(default=None, init=False, repr=False)

    redis: Redis[str]
    redis_broker: RedisBroker

    # Events
    client_crashed_event: Event = field(default_factory=Event)

    def __post_init__(self) -> None:
        """Initialize the experiment runner."""
        self.game_state_watcher = GameStateWatcher(
            service_name="game", service_uuid=self.experiment.game_uuid, redis=self.redis
        )
        self.defuser_state_watcher = PlayerStateWatcher(
            service_name=self.experiment.defuser.name,
            service_uuid=self.experiment.defuser.uuid,
            redis=self.redis,
        )
        if self.experiment.expert:
            self.expert_state_watcher = PlayerStateWatcher(
                service_name=self.experiment.expert.name,
                service_uuid=self.experiment.expert.uuid,
                redis=self.redis,
            )

        # Create GameClient with shared broker
        self.game_client = GameClient(broker=self.redis_broker)
        self.game_client.game_uuid = self.experiment.game_uuid

        # Initialize Redis player clients with UUIDs
        self.defuser_player_client = PlayerClient(
            player_uuid=self.experiment.defuser.uuid, broker=self.redis_broker
        )

        if self.experiment.expert:
            self.expert_player_client = PlayerClient(
                player_uuid=self.experiment.expert.uuid, broker=self.redis_broker
            )

    @property
    def is_hard_crash(self) -> bool:
        """Check if the experiment has hard crashed."""
        states = [
            self.game_state_watcher.is_hard_crash,
            self.defuser_state_watcher.is_hard_crash,
            self.client_crashed_event.is_set(),
        ]
        if self.expert_state_watcher:
            states.append(self.expert_state_watcher.is_hard_crash)
        return any(states)

    @property
    def is_experiment_over(self) -> bool:
        """Check if the experiment is over."""
        states = [self.game_state_watcher.is_game_over, self.is_hard_crash]
        return any(states)

    @logfire.instrument("Run experiment")
    async def run_experiment(self) -> None:  # noqa: WPS213
        """Run the experiment.

        This method orchestrates the experiment lifecycle through phases:

        1. Setup: Start monitors and configure services
        2. Sync: Ensure all services are ready
        3. Run: Execute the experiment loop
        4. Teardown: Send reflections and stop players
        5. Cleanup: Always cleanup resources regardless of outcome

        To simplify the control flow, we use context managers to handle setup, teardown, and exception handling. This way, we can ensure that even if something goes wrong during the experiment, we still perform necessary cleanup and state updates without crashing the entire service.
        """
        async with (
            self.setup_monitors(),
            self.cleanup_on_end(),
            self.experiment_exception_handler(),
        ):
            logger.debug(
                "Experiment lifecycle started",
                experiment=self.experiment,
                game_ready_state=self.game_state_watcher.ready_state,
                defuser_ready_state=self.defuser_state_watcher.ready_state,
                expert_ready_state=self.expert_state_watcher.ready_state
                if self.expert_state_watcher
                else None,
            )

            await self.configure_services()
            self.state = ExperimentState.running
            await self.synchronize_services()

            logger.debug("Running experiment loop")
            async with anyio.create_task_group() as experiment_tg:
                experiment_tg.start_soon(self.run_experiment_loop)

            self.state = ExperimentState.post_game

            # Do not send reflections/end the game if we have had a hard crash.
            # Note: while we shouldn't be needing this if-statement, it's better to be safe
            # when dealing with this I think.
            if not self.is_hard_crash:
                logger.debug(
                    "Running post-game steps",
                    hard_crash=self.is_hard_crash,
                    experiment=self.experiment,
                )
                try:
                    await self.send_reflection_request()
                except TimeoutError:
                    logger.warning(
                        "Reflection request timed out, skipping, but keeping the experiment as a completed one (hopefully)"
                    )

                await self.stop_all_players()

    @asynccontextmanager
    async def setup_monitors(self) -> AsyncGenerator[None]:
        """Start monitors and configure services for the experiment."""
        async with AsyncExitStack() as stack:
            with logfire.span("Setup monitors"):
                # Monitor the state of the game and players during the experiment.
                await stack.enter_async_context(self.game_state_watcher.run_monitor())
                await stack.enter_async_context(self.defuser_state_watcher.run_monitor())
                if self.expert_state_watcher:
                    await stack.enter_async_context(self.expert_state_watcher.run_monitor())
            yield

    @logfire.instrument("Configure services")
    async def configure_services(self) -> None:
        """Setup the services for the experiment."""
        _ = await self.defuser_player_client.configure_player(
            player_protocol=self.experiment.experiment_spec.defuser_protocol,
            experiment_descriptor=self.experiment,
        )
        if self.experiment.expert and self.expert_player_client:
            _ = await self.expert_player_client.configure_player(
                player_protocol=self.experiment.expert.protocol,
                experiment_descriptor=self.experiment,
            )
        await self.game_client.configure_game(
            spec=self.experiment.mission_spec, session_id=self.experiment.session_id
        )
        # Pause on lights off
        with logfire.span("Pausing game after lights are off"):
            with anyio.fail_after(timeouts.configure_services_timeout):
                await self.game_state_watcher.lights_are_off_event.wait()
            await self.game_client.pause_game()

    @logfire.instrument("Synchronize start")
    async def synchronize_services(self) -> None:
        """Synchronize the start of the experiment across all services.

        Basically, we make sure everyone is ready to go before we start.
        """
        with logfire.span("Waiting for all services to be ready"):
            with anyio.fail_after(timeouts.configure_services_timeout):
                # Wait for everyone to be ready to go
                await self.game_state_watcher.lights_are_off_event.wait()
                await self.defuser_state_watcher.is_first_waiting_for_turn.wait()
                if self.expert_state_watcher:
                    await self.expert_state_watcher.is_first_waiting_for_turn.wait()

        logger.debug("All players are ready, unpausing game")
        with logfire.span("Unpausing game"):
            await self.game_client.unpause_game()

        # Wait for lights on
        with logfire.span("Waiting for first lights on"):
            self.game_state_watcher.update_interval = 0.2
            await self.game_state_watcher.first_lights_on_event.wait()
            self.game_state_watcher.reset_update_interval()

        await self.game_client.pause_game()

    @asynccontextmanager
    async def experiment_exception_handler(self) -> AsyncGenerator[None]:  # noqa: WPS213
        """Run the experiment as a context manager.

        This is separated from the `run_experiment` method to allow for a clear setup and cleanup
        process should anything go wrong during the running of the experiment. If we don't, then it
        would make for a very very messy method with several try/except blocks.
        """
        try:  # noqa: WPS229
            yield
        except* anyio.get_cancelled_exc_class():  # noqa: WPS455
            logger.debug("Experiment cancelled", experiment=self.experiment)
            self.client_crashed_event.set()
            # Note that we are explicitly not re-raising the cancelled exception here because
            # we are going to cleanup the experiment within the finally and not crash the
            # entire thing....
        except* (TimeoutError, httpx.HTTPStatusError):
            logger.exception(
                "A client has timed out or crashed, stopping the experiment",
                experiment=self.experiment,
            )
            self.client_crashed_event.set()

    @asynccontextmanager
    async def cleanup_on_end(self) -> AsyncGenerator[None]:
        """Ensure that we always cleanup at the end of the experiment, even if we crash."""
        try:
            yield
        finally:
            # Shield cleanup from the cancelled scope so we can still send
            # graceful stop commands to services that are alive.
            with anyio.CancelScope(shield=True):
                await self.cleanup_experiment()
                await anyio.sleep(1)

    @abc.abstractmethod
    async def run_experiment_loop(self) -> None:
        """Run the experiment loop."""
        raise NotImplementedError

    @asynccontextmanager
    async def guard_step(self) -> AsyncGenerator[None]:
        """Guard the performed step.

        This is used to ensure that if any step of the experiment loop fails, we catch the
        exception and stop the experiment.
        """
        try:
            yield
        except httpx.HTTPError:
            logger.exception(
                "An error occurred during the experiment loop, stopping the experiment"
            )
            self.client_crashed_event.set()

    @logfire.instrument("Send reflection request")
    async def send_reflection_request(self) -> None:
        """Send a reflection request to the players.

        Note that a crash here does NOT mean that the experiment is a failure. We will just regard
        it as a missing reflection.
        """
        if self.defuser_state_watcher.is_hard_crash or (
            self.expert_state_watcher and self.expert_state_watcher.is_hard_crash
        ):
            logger.warning("A player has crashed, skipping reflection request")
            return

        # Make sure players are waiting for a turn and ready ORRR crashed
        logger.debug("Waiting for Defuser to be ready for reflection")
        await self.defuser_state_watcher.wait_for_waiting_for_turn()

        if self.expert_state_watcher:
            logger.debug("Waiting for Expert to be ready for reflection")
            await self.expert_state_watcher.wait_for_waiting_for_turn()

        try:
            bomb_state = await self.game_client.get_bomb_state()
        except httpx.HTTPError:
            return

        reflection_message = convert_bomb_state_to_reflection(bomb_state)
        if reflection_message:
            logger.debug("Sending reflection message", reflection=reflection_message)
            async with anyio.create_task_group() as tg:
                tg.start_soon(
                    self.defuser_player_client.send_reflection_request, reflection_message
                )
                if self.expert_player_client:
                    tg.start_soon(
                        self.expert_player_client.send_reflection_request, reflection_message
                    )

    @logfire.instrument("Stop all players")
    async def stop_all_players(self) -> None:
        """Run the post-game steps after the game has finished.

        Players run the stop logic through a background task, so we expect this to return quickly.
        If there is an exception in the background task, that will be completely separate to the EM
        and the runner because it is being handled in its own service. What this means is that if
        the player crashes, it will never update the heartbeat and the EM will not start a new
        experiment with that player because it would be marked as dead.
        """
        # If we have crashed somehow, then we are going to skip the bomb state retrieval and just
        # tell the players to stop
        bomb_state = None if self.is_hard_crash else await self.game_client.get_bomb_state()

        async with anyio.create_task_group() as tg:
            tg.start_soon(
                partial(
                    self.defuser_player_client.stop_player,
                    bomb_state=bomb_state,
                    is_hard_crash=self.is_hard_crash,
                )
            )
            if self.expert_player_client:
                tg.start_soon(
                    partial(
                        self.expert_player_client.stop_player,
                        bomb_state=bomb_state,
                        is_hard_crash=self.is_hard_crash,
                    )
                )
            # Note: this can superspeed jump to the cleanup before the player even has a chance to
            # start the stopping so we are going to just stick a lil wait here because there
            # isn't really a clear way to know when it'll actually start the processing under the
            # hood. The thing is, this should not be an actual issue because the state gets updated
            # before the task starts, but I'm guessing that this is a consequence of the fact that
            # the service state watcher being a interval-based thing.
            await anyio.sleep(timeouts.session_state_watcher_interval + 1)

    @logfire.instrument("Cleanup experiment")
    async def cleanup_experiment(self) -> None:
        """Cleanup the experiment after it has finished.

        This means that this needs to happen AFTER the reflections, when no services are needed
        anymore.
        """
        self.state = ExperimentState.cleanup
        logger.debug("Cleaning up experiment", experiment=self.experiment)

        try:
            await self.game_client.stop_game()
        except (httpx.HTTPError, TimeoutError):
            logger.warning(
                "Failed to stop the game, it might have already been stopped or crashed"
            )

        await self._try_stop_player(
            client=self.defuser_player_client, watcher=self.defuser_state_watcher, role="defuser"
        )
        if self.experiment.expert and self.expert_player_client and self.expert_state_watcher:
            await self._try_stop_player(
                client=self.expert_player_client, watcher=self.expert_state_watcher, role="expert"
            )

        self.state = ExperimentState.done
        logger.debug("Experiment cleanup completed")

    async def _try_stop_player(
        self, *, client: PlayerClient, watcher: PlayerStateWatcher, role: str
    ) -> None:
        """Stop a player, using a short timeout if the service is already dead.

        If the service has hard-crashed we know the RPC will never be answered, so we cap the wait
        at 5 seconds rather than the full ``redis_rpc_timeout``. Alive services get their normal
        timeout so that in-flight work (e.g. saving results) can finish.
        """
        if watcher.is_stopping.is_set():
            return

        try:
            if watcher.is_hard_crash:
                with anyio.fail_after(5):
                    _ = await client.stop_player(is_hard_crash=self.is_hard_crash)
            else:
                _ = await client.stop_player(is_hard_crash=self.is_hard_crash)
        except (httpx.HTTPError, TimeoutError, anyio.get_cancelled_exc_class()):  # noqa: WPS455
            logger.warning(
                "Failed to stop player, it may have already stopped or crashed", role=role
            )


@dataclass(kw_only=True)
class SyncExperimentRunner(ExperimentRunner):
    """Run the experiment in sync mode.

    One player at a time, with paused time in the middle.
    """

    @override
    async def run_experiment_loop(self) -> None:
        """Run the experiment loop in sync mode.

        While the try-block is long (which we don't like), we're doing it because if this one
        exception occurs in any of the steps, we want to catch it and stop the experiment. Let's
        hope we don't need to make it longer.
        """
        logger.debug("Starting sync loop", is_game_over=self.is_experiment_over)
        while not self.is_experiment_over:
            try:
                async with self.send_feedback_after_step():
                    await self.run_single_sync_step()
            except httpx.HTTPError:
                logger.exception("An error occurred during the sync step, stopping the experiment")
                self.client_crashed_event.set()
            else:
                await anyio.sleep(0.5)

        logger.debug(
            "Experiment sync loop completed",
            experiment=self.experiment.experiment_spec.experiment_name,
        )

    async def run_single_sync_step(self) -> None:
        """Run a single step of the sync experiment loop.

        We are constantly checking if the game is supposed to be over or not during this too to
        ensure that we don't run any more steps if the game is over.
        """
        logger.debug("Running single sync step", is_game_over=self.is_experiment_over)

        async with self.guard_step():
            if not self.is_experiment_over:
                with logfire.span(f"Forward pass (defuser; {self.experiment.defuser.name})"):
                    _ = await self.defuser_player_client.forward_pass()

            # Force update the game state before we advance just in case the game is now over,
            # because otherwise it causes the experiment to crash because the it can't advance the
            # game time
            _ = await self.game_state_watcher.update_service_state()

            if not self.is_experiment_over:
                await self.game_client.advance_game_time()

            if (
                self.expert_player_client
                and self.experiment.expert
                and not self.is_experiment_over
            ):
                with logfire.span(f"Forward pass (expert; {self.experiment.expert.name})"):
                    _ = await self.expert_player_client.forward_pass()

    @asynccontextmanager
    async def send_feedback_after_step(self) -> AsyncGenerator[None]:
        """Context manager to send feedback after a step.

        This is used to send feedback to the players after each step of the experiment. If no
        player wants feedback, then this context manager is a no-op and it just yields without
        doing anything.
        """
        # If we don't want feedback, then we can skip this context manager entirely.
        if not self.experiment.experiment_spec.some_player_wants_feedback:
            yield
            return

        previous_bomb_state = await self.game_client.get_bomb_state()
        yield
        await self.send_feedback_to_players(previous_bomb_state=previous_bomb_state)

    async def send_feedback_to_players(self, *, previous_bomb_state: BombState) -> None:  # noqa: ARG002
        """Send the feedback to the players, if needed/wanted."""
        if not self.experiment.experiment_spec.some_player_wants_feedback:
            return

        # If we cannot get the bomb state, do we assume that the game has crashed?
        current_bomb_state = await self.game_client.get_bomb_state()  # noqa: F841

        # TODO: Convert bomb state to feedback
        feedback = ""

        # Send feedback to the defuser (if wanted)
        if self.experiment.defuser.protocol.receive_feedback_after_action:
            _ = await self.defuser_player_client.send_feedback(feedback)

        if (
            self.expert_player_client
            and self.experiment.expert
            and self.experiment.expert.protocol.receive_feedback_after_action
        ):
            _ = await self.expert_player_client.send_feedback(feedback)


@dataclass(kw_only=True)
class AsyncExperimentRunner(ExperimentRunner):
    """Run the experiment in async mode.

    Each player runs on their own, and we don't stop the time.

    We (currently) do not support sending feedback to playing during async mode because the loop
    needs ot move fast.
    """

    @override
    async def run_experiment_loop(self) -> None:
        """Run the experiment loop in async mode."""
        if self.experiment.experiment_spec.some_player_wants_feedback:
            logger.warning("Feedback is not supported in async mode, ignoring.")

        async with anyio.create_task_group() as tg:
            tg.start_soon(self.run_player_loop, self.defuser_player_client, name="defuser")
            if self.expert_player_client is not None:
                tg.start_soon(self.run_player_loop, self.expert_player_client, name="expert")

        logger.debug(
            "Experiment loop started", experiment=self.experiment.experiment_spec.experiment_name
        )

    async def run_player_loop(self, player_client: PlayerClient) -> None:
        """Run the player loop in async mode."""
        logger.debug("Starting (async) player loop", is_game_over=self.is_experiment_over)

        while not self.is_experiment_over:
            async with self.guard_step():
                _ = await player_client.forward_pass()

                await anyio.sleep(0.5)

        logger.debug(
            "Player loop completed", experiment=self.experiment.experiment_spec.experiment_name
        )
