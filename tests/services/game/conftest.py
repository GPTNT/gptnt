# import uuid
# from pathlib import Path
# from unittest.mock import Mock

# import pytest
# from anyio.abc import Process
# from fakeredis import FakeRedis
# from pytest_mock import MockerFixture

# from gptnt.ktane.client import KtaneClient
# from gptnt.ktane.state.game import GameState
# from gptnt.services.game.process_manager import GameProcessManager
# from gptnt.services.game.state_monitor import GameStateMonitor
# from gptnt.services.game.supervisor import GameSupervisor


# @pytest.fixture
# def fake_redis() -> FakeRedis:
#     return FakeRedis()


# @pytest.fixture
# def test_uuid() -> uuid.UUID:
#     return uuid.uuid4()


# @pytest.fixture
# def mock_ktane_client(mocker: MockerFixture) -> KtaneClient:
#     """Mock KtaneClient with controllable responses."""
#     client = mocker.Mock(spec_set=KtaneClient)
#     client.get_game_state = mocker.AsyncMock(return_value=GameState.unknown)
#     client.healthcheck = mocker.AsyncMock(return_value=True)
#     client.update_url = mocker.AsyncMock()
#     client.start_mission = mocker.AsyncMock()
#     client.stop_time = mocker.AsyncMock(return_value=True)
#     return client


# @pytest.fixture
# def mock_process(mocker: MockerFixture) -> Process:
#     """Mock anyio Process with correct sync/async interface."""
#     process = mocker.Mock()
#     process.returncode = None  # Running by default
#     process.terminate = mocker.Mock()  # Sync method
#     process.kill = mocker.Mock()  # Sync method
#     process.wait = mocker.AsyncMock(return_value=0)  # Async method
#     return process


# @pytest.fixture
# def mock_ktane_settings(mocker: MockerFixture) -> Mock:
#     """Mock KtaneSettings class and instance."""
#     mock_class = mocker.patch("gptnt.services.game.process_manager.KtaneSettings")
#     mock_instance = mock_class.return_value
#     mock_instance.create_settings_files = mocker.Mock()  # Sync method
#     return mock_instance


# @pytest.fixture
# def mock_get_available_port(mocker: MockerFixture) -> Mock:
#     """Mock get_available_port function."""
#     return mocker.patch(
#         "gptnt.services.game.process_manager.get_available_port", return_value=12345
#     )


# @pytest.fixture
# def mock_get_executable_path(mocker: MockerFixture) -> Mock:
#     """Mock get_executable_path function."""
#     return mocker.patch(
#         "gptnt.services.game.process_manager.get_executable_path",
#         return_value=Path("/fake/game.exe"),
#     )


# @pytest.fixture
# def mock_open_process(mocker: MockerFixture, mock_process: Process) -> Process:
#     """Mock anyio.open_process - async function returning process."""
#     return mocker.patch(
#         "gptnt.services.game.process_manager.anyio.open_process", return_value=mock_process
#     )


# @pytest.fixture
# def process_manager(
#     mock_ktane_settings: Mock,
#     mock_get_available_port: Mock,
#     mock_get_executable_path: Mock,
#     mock_open_process: Mock,
# ) -> GameProcessManager:
#     """GameProcessManager with all dependencies mocked."""
#     # Dependencies are injected through pytest fixture dependency system
#     # They patch the imports at module level, so don't need to be used directly
#     return GameProcessManager()


# @pytest.fixture
# def state_monitor(mock_ktane_client: KtaneClient) -> GameStateMonitor:
#     """GameStateMonitor with mocked client."""
#     return GameStateMonitor(client=mock_ktane_client)


# @pytest.fixture
# def game_supervisor(
#     fake_redis: FakeRedis, test_uuid: uuid.UUID, mock_ktane_client: KtaneClient
# ) -> GameSupervisor:
#     """GameSupervisor with mocked dependencies."""
#     supervisor = GameSupervisor(url="http://localhost:8000", redis=fake_redis, uuid=test_uuid)
#     supervisor.ktane_client = mock_ktane_client
#     supervisor.state_monitor = GameStateMonitor(client=mock_ktane_client)
#     return supervisor
