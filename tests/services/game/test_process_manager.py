# from collections.abc import Callable
# from unittest.mock import Mock

# import anyio
# import pytest

# from gptnt.services.game.process_manager import GameProcessManager


# @pytest.mark.anyio
# async def test_start_process_success(
#     process_manager: GameProcessManager, mock_get_available_port: Callable[..., int]
# ) -> None:
#     """Test successful process start returns port."""
#     port = await process_manager.start()

#     assert port == mock_get_available_port()
#     assert process_manager.port == mock_get_available_port()
#     assert process_manager.is_alive is True


# @pytest.mark.anyio
# async def test_start_when_already_running(process_manager: GameProcessManager) -> None:
#     """Test starting when process already running raises error."""
#     _ = await process_manager.start()
#     with pytest.raises(RuntimeError, match="Game process already running"):
#         _ = await process_manager.start()


# @pytest.mark.anyio
# async def test_calling_terminate_without_start_does_nothing(
#     process_manager: GameProcessManager,
# ) -> None:
#     """Test calling terminate without starting does nothing."""
#     await process_manager.terminate(shutdown_time=0.1)
#     assert process_manager._process is None
#     assert process_manager._port is None


# @pytest.mark.anyio
# async def test_terminate_graceful_shutdown(
#     process_manager: GameProcessManager, mock_process: Mock
# ) -> None:
#     """Test graceful process termination."""
#     _ = await process_manager.start()

#     # Simulate graceful shutdown: wait() succeeds and process dies
#     async def _mock_wait() -> int:  # noqa: WPS430
#         # Process has exited
#         mock_process.returncode = 0
#         return 0

#     mock_process.wait.side_effect = _mock_wait
#     await process_manager.terminate(shutdown_time=0.1)

#     mock_process.terminate.assert_called_once()
#     mock_process.wait.assert_called_once()
#     assert process_manager._process is None
#     assert process_manager._port is None


# @pytest.mark.anyio
# async def test_terminate_force_kill(
#     process_manager: GameProcessManager, mock_process: Mock
# ) -> None:
#     """Test force kill when graceful termination fails."""
#     _ = await process_manager.start()

#     # First wait() hangs, second wait() completes
#     mock_process.wait.side_effect = [anyio.sleep_forever, 0]

#     await process_manager.terminate(shutdown_time=0.1)

#     mock_process.terminate.assert_called_once()
#     mock_process.kill.assert_called_once()


# @pytest.mark.anyio
# async def test_waiting_without_process_raises_error(process_manager: GameProcessManager) -> None:
#     """Test waiting for process without starting raises error."""
#     with pytest.raises(RuntimeError, match="No process to wait for?"):
#         _ = await process_manager.wait()


# def test_is_alive_with_running_process(
#     process_manager: GameProcessManager, mock_process: Mock
# ) -> None:
#     """Test is_alive property with running process."""
#     # Set up mock process to simulate running state
#     # Note: `returncode` is None when process is running
#     process_manager._process = mock_process
#     mock_process.returncode = None

#     assert process_manager.is_alive is True


# def test_is_alive_with_dead_process(
#     process_manager: GameProcessManager, mock_process: Mock
# ) -> None:
#     """Test is_alive property with dead process."""
#     # Set up mock process to simulate dead state
#     # Note: `returncode` is not None when process has exited
#     process_manager._process = mock_process
#     mock_process.returncode = 1

#     assert process_manager.is_alive is False


# def test_is_alive_with_no_process(process_manager: GameProcessManager) -> None:
#     """Test is_alive property with no process."""
#     assert process_manager.is_alive is False
