from gptnt.core.common.typer import AsyncTyper
from gptnt.interactive.cli.generate_experiment_specs import generate_experiment_specs
from gptnt.interactive.cli.kill import force_kill
from gptnt.interactive.cli.send_experiments import send_experiment_specs_to_em
from gptnt.interactive.cli.throw import throw

interactive_app = AsyncTyper(
    name="interactive", help="Interactive commands.", no_args_is_help=True
)

_ = interactive_app.command("throw", rich_help_panel="Interactive", no_args_is_help=True)(throw)
_ = interactive_app.command("generate", rich_help_panel="Interactive")(generate_experiment_specs)
_ = interactive_app.command("submit", rich_help_panel="Interactive")(send_experiment_specs_to_em)
_ = interactive_app.command("kill", rich_help_panel="Interactive")(force_kill)


if __name__ == "__main__":
    interactive_app()
