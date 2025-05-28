import asyncio

from gptnt.api.api import APIQueues, APIRoutes
from gptnt.api.commands import ConfigureGameCommand, ConfigurePlayerCommand
from gptnt.api.experiment_manager.experiment_descriptor import ExperimentDescriptor


async def set_experiment_bindings(
    experiment: ExperimentDescriptor, api_queues: APIQueues, api_routes: APIRoutes
) -> None:
    """Sets up the queue bindings for this experiment.

    Defined to here to keep this in one place in-case both EM and Room need to set/remove bindings.
    """
    # Messages route
    to_expert = api_routes.game_messages(
        game_uuid=experiment.game_uuid, role="defuser"
    ).routing_key
    to_defuser = api_routes.game_messages(
        game_uuid=experiment.game_uuid, role="expert"
    ).routing_key

    await api_queues.player_messages(player_uuid=experiment.defuser_uuid).bind(to_defuser)
    if experiment.expert_uuid:
        await api_queues.player_messages(player_uuid=experiment.expert_uuid).bind(to_expert)

    # Observations route
    game_obs = api_routes.game_observations(game_uuid=experiment.game_uuid).routing_key
    await api_queues.player_observations(player_uuid=experiment.defuser_uuid).bind(game_obs)


async def remove_experiment_bindings(
    experiment: ExperimentDescriptor, api_queues: APIQueues
) -> None:
    """Removes the queue bindings for this experiment.

    Defined here to keep this in one place in-case both EM and Room need to set/remove bindings.
    """
    # Message route
    await api_queues.player_messages(player_uuid=experiment.defuser_uuid).unbind()
    if experiment.expert_uuid:
        await api_queues.player_messages(player_uuid=experiment.expert_uuid).unbind()

    # Observation route
    await api_queues.player_observations(player_uuid=experiment.defuser_uuid).unbind()


async def configure_experiment_services(
    *, experiment: ExperimentDescriptor, api_queues: APIQueues, fail_after: float
) -> bool:
    """Configure the TODO: should this be here?"""
    configure_game = api_queues.game_command(experiment.game_uuid).route.publish_with_ack(
        ConfigureGameCommand(mission_spec=experiment.experiment_spec.mission_spec),
        fail_after=fail_after,
    )

    configure_defuser = api_queues.player_command(experiment.defuser_uuid).route.publish_with_ack(
        ConfigurePlayerCommand(
            player_spec=experiment.experiment_spec.defuser_player_spec,
            experiment_descriptor=experiment,
        ),
        fail_after=fail_after,
    )

    if experiment.expert_uuid and experiment.experiment_spec.expert_player_spec:
        configure_expert = api_queues.player_command(
            experiment.expert_uuid
        ).route.publish_with_ack(
            ConfigurePlayerCommand(
                player_spec=experiment.experiment_spec.expert_player_spec,
                experiment_descriptor=experiment,
            ),
            fail_after=fail_after,
        )
        return all(await asyncio.gather(configure_game, configure_defuser, configure_expert))
    return all(await asyncio.gather(configure_game, configure_defuser))
