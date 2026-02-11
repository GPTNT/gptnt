# import anyio
# import httpx
# import pytest
# import respx
# from pydantic import RedisDsn
# from pytest_cases import fixture, parametrize
# from pytest_mock import MockerFixture

# from gptnt.experiments.experiments import ExperimentSpec
# from gptnt.services.events.heartbeat import ReadyState
# from gptnt.services.events.player import PlayerMessage, PlayerState
# from gptnt.services.game.context import GameServiceContext
# from gptnt.services.player.context import PlayerContext
# from gptnt.services.sessions.experiment_runner import ExperimentState, SyncExperimentRunner
# from gptnt.services.sessions.session import Session

# pytestmark = pytest.mark.anyio


# @fixture
# async def session(
#     redis_server_dsn: RedisDsn,
#     game_app_client: httpx.AsyncClient,
#     game_context: GameServiceContext,
#     defuser_player_app_client: httpx.AsyncClient,
#     defuser_player_context: PlayerContext,
#     experiment_spec: ExperimentSpec,
#     mocker: MockerFixture,
# ) -> Session:
#     await anyio.sleep(10)  # Ensure the game and player are ready
#     session = Session(
#         game=game_context.manifest,
#         defuser=defuser_player_context.manifest,
#         spec=experiment_spec,
#         redis_url=redis_server_dsn,
#     )
#     session.experiment_runner.defuser_player_client._client = defuser_player_app_client
#     session.experiment_runner.game_client._client = game_app_client
#     defuser_player_context.game_client._client = game_app_client

#     session.experiment_runner.defuser_player_client.recreate_client = mocker.Mock(
#         return_value=defuser_player_app_client
#     )
#     session.experiment_runner.game_client.recreate_client = mocker.Mock(
#         return_value=game_app_client
#     )
#     defuser_player_context.game_client.recreate_client = mocker.Mock(
#         return_value=game_app_client
#     )

#     # TODO: If we have the expert player, then we need to add a mock to the MessageManager too so
#     #       that the players communicate with one another
#     return session


# @fixture
# def experiment_runner(session: Session) -> SyncExperimentRunner:
#     assert isinstance(session.experiment_runner, SyncExperimentRunner)
#     return session.experiment_runner


# async def test_mocking_endpoints_work_as_expected(
#     defuser_player_app_client: httpx.AsyncClient, respx_mock: respx.MockRouter
# ) -> None:
#     response_route = respx_mock.post(f"{defuser_player_app_client.base_url}/reflection").mock(
#         return_value=httpx.Response(200, json={"ok": True})
#     )
#     sideeffect_route = respx_mock.get(f"{defuser_player_app_client.base_url}/state").mock(
#         side_effect=TimeoutError
#     )

#     _ = await defuser_player_app_client.get("/health")

#     _ = await defuser_player_app_client.post(
#         "/reflection", json=PlayerMessage(message="terminated-exploded").model_dump(mode="json")
#     )

#     with pytest.raises(TimeoutError):
#         _ = await defuser_player_app_client.get("/state")

#     assert response_route.called
#     assert sideeffect_route.called


# async def test_clients_can_ping_the_endpoints_successfully(
#     experiment_runner: SyncExperimentRunner,
# ) -> None:
#     # After creating the runner for the session, make sure that the clients can ping the
#     # endpoints successfully, which means that the services are running and accessible, and that
#     # the clients are visible from the session/EM.
#     assert await experiment_runner.game_client.healthcheck() is True
#     assert await experiment_runner.defuser_player_client.healthcheck() is True


# async def test_game_state_watcher_updates_state_on_external_change(
#     experiment_runner: SyncExperimentRunner, experiment_spec: ExperimentSpec
# ) -> None:
#     async with experiment_runner.game_state_watcher.run_monitor():
#         # Brief delay to let tasks start
#         await anyio.sleep(0.1)
#         # start mission from game app client
#         await experiment_runner.game_client.configure_game(spec=experiment_spec.mission_spec)
#         await experiment_runner.game_client.unpause_game()
#         await anyio.sleep(10)
#         await experiment_runner.game_client.pause_game()
#         # Force the update of the states
#         await experiment_runner.game_state_watcher.update_service_state()
#         # Verify the state is what we want
#         await anyio.sleep(1)
#         assert experiment_runner.game_state_watcher.first_lights_on_event.is_set()


# async def test_player_state_watcher_updates_state_on_external_change(
#     experiment_runner: SyncExperimentRunner, experiment_spec: ExperimentSpec
# ) -> None:
#     async with experiment_runner.defuser_state_watcher.run_monitor():
#         # Brief delay to let tasks start
#         await anyio.sleep(0.1)
#         protocol = experiment_spec.defuser_protocol
#         descriptor = experiment_runner.experiment
#         _ = await experiment_runner.defuser_player_client.configure_player(
#             player_protocol=protocol, experiment_descriptor=descriptor
#         )
#         await anyio.sleep(2)
#         await experiment_runner.defuser_state_watcher.update_service_state()

#         assert experiment_runner.defuser_state_watcher.is_first_waiting_for_turn.is_set()


# async def test_experiment_runner_configures_services_correctly(
#     experiment_runner: SyncExperimentRunner,
# ) -> None:
#     async with experiment_runner.active_state_monitors():
#         await experiment_runner.setup_experiment()
#         assert experiment_runner.game_state_watcher.lights_are_off_event.is_set()
#         assert experiment_runner.defuser_state_watcher.is_first_waiting_for_turn.is_set()


# async def test_sync_start_when_a_service_dies(
#     experiment_runner: SyncExperimentRunner, game_context: GameServiceContext
# ) -> None:
#     async with experiment_runner.experiment_exception_handler():
#         experiment_runner.state = ExperimentState.running

#         # Simulate the game client closing
#         await game_context.process_manager.terminate()
#         # Ensure that all the services are ready and synchronized before starting
#         async with (
#             experiment_runner.synchronized_experiment_start(),
#             anyio.create_task_group() as tg,
#         ):
#             tg.start_soon(experiment_runner.run_experiment_loop)

#     assert experiment_runner.is_experiment_over
#     assert experiment_runner.client_crashed_event.is_set()
#     assert experiment_runner.is_hard_crash


# async def test_player_performs_forward_pass_from_api_request(
#     experiment_runner: SyncExperimentRunner,
# ) -> None:
#     async with experiment_runner.active_state_monitors():
#         await experiment_runner.setup_experiment()
#         async with experiment_runner.synchronized_experiment_start():
#             _ = await experiment_runner.defuser_player_client.forward_pass()
#             await anyio.sleep(5)
#             assert experiment_runner.defuser_state_watcher.is_first_waiting_for_turn.is_set()


# async def test_run_a_single_sync_step(experiment_runner: SyncExperimentRunner) -> None:
#     # Run a single step of the experiment runner --- defuser, expert, game.
#     async with experiment_runner.active_state_monitors():
#         await experiment_runner.setup_experiment()
#         async with experiment_runner.synchronized_experiment_start():
#             _ = await experiment_runner.run_single_sync_step()
#             await anyio.sleep(5)
#             assert experiment_runner.defuser_state_watcher.is_first_waiting_for_turn.is_set()


# async def test_run_multiple_sync_steps(experiment_runner: SyncExperimentRunner) -> None:
#     # Run multiple (2-3) steps of the experiment runner --- defuser, expert, game.
#     async with experiment_runner.active_state_monitors():
#         await experiment_runner.setup_experiment()
#         async with experiment_runner.synchronized_experiment_start():
#             for _ in range(3):
#                 _ = await experiment_runner.run_single_sync_step()
#                 await anyio.sleep(5)
#                 assert experiment_runner.defuser_state_watcher.is_first_waiting_for_turn.is_set()


# async def test_game_over_screen_detected_by_watcher(
#     experiment_runner: SyncExperimentRunner, game_context: GameServiceContext
# ) -> None:
#     async with experiment_runner.active_state_monitors():
#         # Start the game/mission
#         await experiment_runner.setup_experiment()
#         await experiment_runner.game_client.unpause_game()

#         await experiment_runner.game_state_watcher.update_service_state()

#         # wait a bit for the lights to turn on
#         await anyio.sleep(10)

#         _ = await game_context.ktane_client.detonate_bomb()
#         await anyio.sleep(5)

#         # Force update the state watchers
#         await experiment_runner.game_state_watcher.update_service_state()

#         # then check the state watcher and events to see what it says
#         assert experiment_runner.is_experiment_over
#         assert not experiment_runner.is_hard_crash
#         assert experiment_runner.game_state_watcher.good_game_over_event.is_set()


# async def test_game_crash_is_detected_by_experiment_runner(
#     experiment_runner: SyncExperimentRunner, game_context: GameServiceContext
# ) -> None:
#     """Make sure a hard crash is detected by the game state watcher.

#     `ExperimentRunner.is_experiment_over` is True and `ExperimentRunner.is_hard_crash` is True.
#     """
#     async with experiment_runner.active_state_monitors():
#         # Start the game/mission
#         await experiment_runner.setup_experiment()
#         await experiment_runner.game_client.unpause_game()
#         await anyio.sleep(10)

#         # Kill the game process
#         await game_context.process_manager.terminate()
#         await anyio.sleep(2)

#         # Force update the state watchers
#         await game_context.send_heartbeat()
#         assert game_context.heartbeat_event().ready_state == ReadyState.not_ready
#         await experiment_runner.game_state_watcher.update_service_state()
#         await anyio.sleep(1)

#         # then check the state watcher and events to see what it says
#         assert experiment_runner.is_experiment_over
#         assert experiment_runner.is_hard_crash
#         assert not experiment_runner.game_state_watcher.good_game_over_event.is_set()


# async def test_random_game_crash_is_detected(
#     experiment_runner: SyncExperimentRunner, game_context: GameServiceContext
# ) -> None:
#     async def _crash_game_after_delay(delay: int) -> None:  # noqa: WPS430
#         await anyio.sleep(delay)
#         await game_context.process_manager.terminate()

#     # with anyio.fail_after(90):
#     async with anyio.create_task_group() as tg:
#         tg.start_soon(_crash_game_after_delay, 10)
#         tg.start_soon(experiment_runner.run_experiment)

#     assert experiment_runner.is_experiment_over
#     assert experiment_runner.is_hard_crash
#     assert not experiment_runner.game_state_watcher.good_game_over_event.is_set()


# async def test_game_crash_on_setup(
#     experiment_runner: SyncExperimentRunner, mocker: MockerFixture
# ) -> None:
#     experiment_runner.setup_experiment = mocker.AsyncMock(
#         side_effect=httpx.HTTPStatusError(
#             "Crash", request=httpx.Request("get", ""), response=httpx.Response(500)
#         )
#     )

#     await experiment_runner.run_experiment()

#     assert experiment_runner.is_experiment_over
#     assert experiment_runner.is_hard_crash
#     assert not experiment_runner.game_state_watcher.good_game_over_event.is_set()


# async def test_game_crash_on_unpause(
#     experiment_runner: SyncExperimentRunner, mocker: MockerFixture
# ) -> None:
#     experiment_runner.game_client.unpause_game = mocker.AsyncMock(
#         side_effect=httpx.HTTPStatusError(
#             "Crash", request=httpx.Request("get", ""), response=httpx.Response(500)
#         )
#     )

#     await experiment_runner.run_experiment()

#     assert experiment_runner.is_experiment_over
#     assert experiment_runner.is_hard_crash
#     assert not experiment_runner.game_state_watcher.good_game_over_event.is_set()


# async def test_reflection_happens_successfully_after_good_game_over(
#     experiment_runner: SyncExperimentRunner, game_context: GameServiceContext
# ) -> None:
#     async with experiment_runner.active_state_monitors():
#         # Start the game/mission
#         await experiment_runner.setup_experiment()
#         await experiment_runner.game_client.unpause_game()

#         await experiment_runner.game_state_watcher.update_service_state()

#         # wait a bit for the lights to turn on
#         await anyio.sleep(10)

#         _ = await game_context.ktane_client.detonate_bomb()
#         await anyio.sleep(5)

#         # Force update the state watchers
#         await experiment_runner.game_state_watcher.update_service_state()
#         experiment_runner.state = ExperimentState.post_game
#         await experiment_runner.send_reflection_request()
#         await anyio.sleep(2)
#         await experiment_runner.defuser_state_watcher.update_service_state()
#         assert experiment_runner.defuser_state_watcher.state == PlayerState.reflecting


# async def test_bomb_state_request_fail_during_reflection_doesnt_crash_experiment(
#     experiment_runner: SyncExperimentRunner, game_context: GameServiceContext, mocker: MockerFixture
# ) -> None:
#     # check this with a request fail and a response fail
#     async with experiment_runner.active_state_monitors():
#         # Start the game/mission
#         await experiment_runner.setup_experiment()
#         await experiment_runner.game_client.unpause_game()

#         await experiment_runner.game_state_watcher.update_service_state()

#         # wait a bit for the lights to turn on
#         await anyio.sleep(10)

#         _ = await game_context.ktane_client.detonate_bomb()
#         await anyio.sleep(5)

#         # Force update the state watchers
#         await experiment_runner.game_state_watcher.update_service_state()
#         experiment_runner.state = ExperimentState.post_game

#         experiment_runner.game_client.get_bomb_state = mocker.Mock(
#             side_effect=httpx.HTTPError("Simulated request failure")
#         )

#         await experiment_runner.send_reflection_request()
#         await anyio.sleep(2)
#         await experiment_runner.defuser_state_watcher.update_service_state()
#         await experiment_runner.game_state_watcher.update_service_state()

#         assert experiment_runner.is_experiment_over
#         assert not experiment_runner.is_hard_crash
#         assert experiment_runner.game_state_watcher.good_game_over_event.is_set()


# async def test_timeout_during_player_reflection_doesnt_crash_experiment(
#     experiment_runner: SyncExperimentRunner,
#     game_context: GameServiceContext,
#     mocker: MockerFixture,
#     respx_mock: respx.MockRouter,
# ) -> None:
#     # Mock the reflection endpoint to time out when its called
#     reflection_route = respx_mock.post(
#         f"{experiment_runner.defuser_player_client.base_url}/reflection"
#     ).mock(side_effect=TimeoutError)

#     original_run = experiment_runner.run_experiment_loop

#     async def _detonate_bomb_after_delay() -> None:  # noqa: WPS430
#         await anyio.sleep(10)
#         _ = await game_context.ktane_client.detonate_bomb()

#     async def _detonation_wrapper() -> None:  # noqa: WPS430
#         async with anyio.create_task_group() as tg:
#             tg.start_soon(_detonate_bomb_after_delay)
#             tg.start_soon(original_run)

#     experiment_runner.run_experiment_loop = mocker.AsyncMock(side_effect=_detonation_wrapper)
#     # TODO: because I have a try-except within the method, it's not helping when it comes to the
#     # fact that calling it is the thing that raises. I need to get the respx mock to do it instead
#     await experiment_runner.run_experiment()
#     await anyio.sleep(5)
#     await experiment_runner.game_state_watcher.update_events_from_states()

#     assert reflection_route.called
#     assert experiment_runner.is_experiment_over
#     assert not experiment_runner.client_crashed_event.is_set()
#     assert not experiment_runner.is_hard_crash


# @parametrize("endpoint", ["buffer", "timestep", "action", "state"])
# async def test_client_crashed_event_set_after_game_crash_mid_call(
#     experiment_runner: SyncExperimentRunner,
#     game_context: GameServiceContext,
#     endpoint: str,
#     respx_mock: respx.MockRouter,
#     mocker: MockerFixture,
# ) -> None:
#     """Verify experiment ends without crashing system when a game crash occurs mid-call mid-game.

#     Essentially, if we are in the middle of the request for an observation of something from the
#     game service, which is itself calling from ktane, and the game crashes, we are likely going to
#     get dominoes of errors and we need to make sure that we don't bring the entire system down, and
#     that everyone can recover gracefully.
#     """
#     # Mock the buffer endpoint to crash the game when its called
#     _ = respx_mock.get(f"{game_context.ktane_client.base_url}/{endpoint}").mock(
#         side_effect=lambda _: game_context.process_manager.terminate()
#     )

#     game_end_spy = mocker.spy(experiment_runner.game_client, "stop_game")
#     player_end_spy = mocker.spy(experiment_runner.defuser_player_client, "stop_player")

#     async with (
#         experiment_runner.active_state_monitors(),
#         experiment_runner.experiment_exception_handler(),
#     ):
#         await experiment_runner.setup_experiment()
#         experiment_runner.state = ExperimentState.running

#         async with experiment_runner.synchronized_experiment_start():
#             await anyio.sleep(5)
#             await experiment_runner.game_client.pause_game()
#             await experiment_runner.run_single_sync_step()
#             await anyio.sleep(10)

#             # assert route.called
#             assert experiment_runner.client_crashed_event.is_set()
#             assert experiment_runner.is_experiment_over
#             assert experiment_runner.is_hard_crash

#     _ = game_end_spy.assert_awaited()
#     _ = player_end_spy.assert_awaited()


# # TODO: Make sure that all services are cleaned up properly after a crash --- use a spy to make
# #       sure it's called
# # TODO: Make sure all the services are available again in the EM after the runner is over


# # Double check this, does this mean that the players/game are ready
# # What does cleaned up properly mean? And some pointers on how to check that functions-wise
# # stop game / stop player. And seeing to wandb using spy
