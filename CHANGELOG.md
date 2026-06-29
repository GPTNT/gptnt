## Unreleased

### Fix

- **wandb**: ensure wandb is optional for non-wandb pathways (#1)

### Refactor

- **cli**: split cleanup from reconciling with wandb (#2)
- **statics**: flatten evaluation package up into statics
- **statics**: self-contain evaluation constants

## v0.13.2 (2026-06-28)

### Feat

- add `results` command to see mission results

## v0.13.1 (2026-06-25)

### Feat

- use parquet for saving records
- **statics**: split state recognition datasets
- make KTANE music, SFX, and language configurable

### Refactor

- cleanup the versioning


- collapse back to a single `src/gptnt` dir

## v0.13.0 (2026-06-23)

### Feat

- simplify onboarding using yaml files
- **statics**: add "how do you do" test
- mod now supports modded modules
- replace MIT with Apache
- **configs/qwen35**: remove image resizing

### Fix

- **cli**: update entrypoint for `status`
- **configs**: target for wandb recorder
- **configs**: use the wandb recorder
- **configs**: set timelimit to null for single async
- **statics**: score keypad for defuser-vqa-mcq
- **statics**: need unique task name for expert-vqa-no-manual

### Refactor

- separate codebase using uv workspaces
- cleanup startx.py

## v0.12.1 (2026-04-17)

### Feat

- **statics**: support expert-vqa without the manual

### Fix

- **app/extract**: dont unwrap if we are unwrapping a dict
- **app/extract**: unwrap single-value field extractions from list

## v0.12.0 (2026-04-14)

### Feat

- **app**: export fields as a parquet and dont collate steps
- **app**: enforce jsonable python before converting to dataframe
- **statics**: test expert ocr with both image and text

### Fix

- **app**: pass db context when deserialising step records from DuckDB
- ocr to have the correct module names and fix scorer
- **statics/prompt**: be more precise in the OCR prompt
- **app/connection**: use lightweight cursor to improve query execution
- **app/data**: improve query handling and session ID mapping
- **hydra**: separate load hydra config into a function for better handling
- **configs**: do not exclude simon/morse from solo player

## v0.11.3 (2026-04-07)

### Feat

- **db**: improve ingestion speed by going through parquets first
- **app**: add sql explorer
- **db**: make more properties computed fields so they stay

### Fix

- **experiments**: remove the model validator on experiment descriptor
- **duckdb**: fix varchar serialization and validation
- **records**: auto-handle missing expert capabilities
- **cli/send**: cleanup wandb before sending experiments

### Refactor

- **cli**: move wandb cleaners into separate func

## v0.11.2 (2026-03-24)

### Feat

- **records**: add `PlayerCapabilities` to the experiment outputs
- **build-db**: stream step records individually through bounded queue

## v0.11.1 (2026-03-22)

### Feat

- **cli**: run statics from the `cli`
- **cli**: simplify output cleanup and db creation
- **cli**: mark wandb as old if we dont have the json outputs
- **app/extractor**: download extracted fields as JSON (and not CSV)
- **configs**: add anthropic foundry provider
- **app**: add filter for defuser having the manual
- adds lottery solver python side

### Fix

- **configs**: update target for playerprotocol
- **tests**: correct typo in mock patch
- **configs**: update target for playercapabilities
- **cli**: increase timeout when getting runs for db creation
- **experiment-configs**: strips back random baseline configs

### Refactor

- improve imports and file structures
- **cli**: migrate `generate` and `throw_experiments` to cli
- move types to `common/`

## v0.11.0 (2026-03-09)

### Feat

- support multiple attempts per experiment
- **app**: merge dialogue viewer and selector into a single page
- adds scratching lottery tickets to the mod
- **app**: add field extracting page
- buffer just drank a speed II potion
- **records**: support lightweight loading with pydantic context
- **app**: support filtering by the custom tags
- **cli**: command to delete invalid experiment outputs
- **app**: improve the streamlit app
- **models**: swap qwen3vl for qwen3.5
- ensure async stop quickly on game end

### Fix

- **app**: add explicit hash for scanned experiment
- **exception-recovery**: handle and capture invalid responses
- **tokens**: fix qwen35 token estimate
- **mission-configs**: remove unused and update number of seeds
- **statics**: support `model@provider` for model names
- **exceptions**: ensure responses have some text after exceeding max tokens

### Refactor

- **cli**: rename `cli/experiments.py` -> `cli/status.py`

### Perf

- **som**: optimise antialiasing removal from segmentation mask

## v0.10.1 (2026-02-24)

### Feat

- **app**: create streamlit dialogue viewer
- **exp-runner**: connect async runner so we can run async
- add a script to find and set wandb runs to old
- **client**: log when we do a retry
- **client**: tweak the retries to not go over 600s
- add `524` to list of errors to retry for
- **observability**: support aggressively limiting traces
- **solo-reflection**: implement separate reflection prompt for solo …
- **solo-reflection**: implement separate reflection prompt for solo defuser and player
- **cli**: add status command to check how experiments are going
- add retrying client for google providers
- **exception**: crash the run if we hit the request quota
- **observability**: add tail sampling onto otel collector
- **logging**: set faststream logging to warning or higher

### Fix

- **recovery**: handle `HttpStatusErrors` in recovery
- **configs**: incorrect nesting for player override
- **cli**: make the status table 1-indexed
- **cli**: use progress bar when collating runs
- **configs**: multiple_modules_n needs a time limit even though it gets replaced later
- **otel**: update filters for Twitch and Unity errors
- **instrumentation**: always run instrumentation
- **otel-collector**: hide the pointless spans
- **cli**: its `model/provider`
- **cli**: give providers as the override when spawning players

### Refactor

- **cli**: use existing functions to check for invalid/valid runs
- rename `BaseClient` -> `ManagedHttpClient`
- **configs**: collate and explicit-ify the config/experiment dir

## v0.10.0 (2026-02-19)

### Feat

- support different providers per model
- **logging**: set faststream to warning
- **statics-results**: download, aggregate and HF upload/export Latex the statics results
- **records**: parallelise observation loading and offload deserialisation to thread
- **wandb**: ensure invalid runs are marked as old when throwing
- expand heartbeat failure information
- **cli**: support interactive throwing

### Fix

- update default player list
- **exception-recovery**: support new variations of invalid prompt errors
- capture session id from logs into collector
- **entrypoints/throw**: properly calculate which experiments need to be thrown
- **services/player**: properly init the `PlayerServiceContext`
- **services/game**: make sure we init the game service context
- **services/game**: dont do a recursive lifespan
- **entrypoints/throw**: improve counting wandb runs/experiments
- make token accountant more obvious
- add event for expected death

### Refactor

- simplify func param to not use *
- try to simplify the test infra
- only configure logging/logfire when the entrypoint module is the script

## v0.9.2 (2026-02-13)

### Feat

- **cli**: simplify throwing with a cli
- **observability**: track session id and player role on spans
- **observability**: filter out some unnecessary faststream spans
- **models**: switch to gpt 5.2
- adds session id to logs in the game
- **image-resizer**: support overriding the resample method from the method
- **metrics**: don't assert if there are no player records
- log the binary mask for coordinate grounding missions
- patch BinaryContent when printing ExperimentStepRecord
- **statics/scorers**: instrument scorers with weave
- **statics**: include preview images where possible
- **image-resizer**: update default resampling method to LANCZOS
- **image-resizer**: update default resampling method to BICUBIC
- **tests**: test coordinate validator scorers
- **records**: save all experiments in one `throw.sh` to the same dir

### Fix

- **token-acc**: estimate from the model capabilities
- **tokens**: improve image estimate per model
- **models**: set qwen model length to 128k
- incorrect target in player.yaml
- **messages**: handle received feedback separately to messages
- set usage limits for open boxes
- **redis**: only instantiate redis and redisbroker
- **observability**: disable arg extraction in the wandb recorder
- error logs for timestep timeout
- **som/ordering**: filter out non-existent regions
- **observability**: remove `self` from observability instrument
- **observations**: apply SoM before resizing images
- **observability**: try to remove the messages from the step records in logfire
- **statics**: resizing arrays were the wrong way around
- convert the binary mask from a numpy array to a pillow image
- **statics**: remove image resizer instantiating within post_init
- **statics**: resize images to follow the correct aspect ratio for the image type
- **model-configs**: add coordinate mode for normalising coords for ge…
- **model-configs**: add coordinate mode for normalising coords for gemini
- **configs**: set coordinate mode to normalised for internvl35 and qwen3vl
- **image-resizer**: update default resampling method to HAMMING
- **scorers**: string ground truth responses need to be lowercased
- **postprocess**: correct variable access for normalized coordinates
- **experiment-runner**: explicitly update the game state before advancing game time
- **records**: add custom field validator for input messages
- **recorder**: make sure the output folder exists
- use `anyio.Path` for saving player records to disk
- **prompts**: update coordinate prompt for interactive games to align…
- **prompts**: update coordinate prompt for interactive games to align with the one used for statics

### Refactor

- **errors**: clarify that models exceed the max output tokens
- rename `*Controller` and `*Supervisor` classes

## v0.9.1 (2026-02-05)

### Feat

- support normalised coordinates
- migrate base64 -> pybase64
- remove empty directories for experiment recorder outputs
- add scorer to validate coordinates
- absolute distance score
- **configs/models**: add gpt5.2-chat for openai
- **parser**: Parse edge cases resulting from model reproducing (parts of) placeholders
- **statics**: log instructions for statics in dataset
- **statics**: separate exceptions from response errors
- **records**: track input and output messages per step
- replace gpt5 -> gpt5.1chat
- **statics/scorers/keypad**: compare against all embeddings instead of the average
- log and keep exceptions from running statics

### Fix

- **configs**: add thinking model to dummy models
- compute max distance based on image dims
- ensure player records save correctly
- update the grounding prompts
- **model-configs**: update gpt 5.2 model name and remove reasoning pa…
- **model-configs**: update gpt 5.2 model name and remove reasoning params
- track response error types in exceptions
- **prompts**: remove redundant and confusing placeholder references
- typo in reasoning_prompt
- **static/scorer**: check keypad with exact match first
- **configs**: set max tokens for all models
- **observability**: remove repeated instrument calls during obs cleaning
- **parser**: fix missing `>` in tags
- **models**: strongly encourage gemini-3 to not think
- **statics**: update model_predict and predict method signatures to include args and kwargs
- **input-builder**: remove double-y adding the manual
- **scorers**: correct output embedding processing in similarity check
- **throw-script**: update gemini model to gemini-3
- **scorers**: catch json validation errors when parsing non-coords
- **model-configs**: update claude45 model name
- **model-configs**: update claude45 model name and disable thinking and top_p
- **prompts**: account for structured output / inner monologue in reflection, statics and schema suffix
- keypad descriptions with expanded unicode characters
- **static/vqa-oe**: keyerror when preprocessing the instances

### Refactor

- split `PlayerDeps` from `gptnt.players.specification`

## v0.9.0 (2026-01-30)

### Feat

- add multiple reasoning parsers and switch to ReAct
- **instructions**: support manually including schema in instructions for any output mode

### Fix

- update model temprature and top_p
- **message-history**: remove assertion ensuring input tokens > 0

### Refactor

- **nobf**: remove import/dependence on `gptnt.services`

## v0.8.0 (2026-01-26)

### Feat

- **message-history**: support preserving last observation for n turns and truncations
- **statics**: support `--limit-instances` option when running
- add defuser state change data generation
- improve exception handling from agent runs
- **nobf**: implement feedback on naughty output behaviour of models
- adds post processor for expert ocr
- finalize expert ocr
- **configs/models**: add usage_limits target in `player.yaml`
- **config/models**: add token limits for closed models
- **configs/models**: add gemini-3-flash
- **configs**: make all closed models use `PromptedOutput`
- **evaluation/scorer**: support providing model output string cleaning func
- **evaluation/scorers**: support different comparison methods to compute score
- provide weave scorers when instantiating `RunEvaluation`
- **eval**: resize every image for every instance per model before running
- use env var for game height/width for image resizer if it exists

### Fix

- default values for grounding scorers
- grounding coord scorers
- **statics**: resize numpy arrays in statics
- **statics**: resize numpy arrays from statics
- logger saying the number of manual pages we are loading
- make all reflection just a `str` response
- **statics**: separate output folders for defuser grounding location types
- **nobf**: fix nobf wording
- **messages**: do not give model do nothings from exceptions
- pause the game once the lights turn on
- predict_method input should only be the model input
- **defuser statics**: simplify grounding groundtruth and unify vqa format
- **typo**: forgot the `.` in the filename
- **evaluation/static**: ensure distance scorers have unique names
- Separate instructions for defuser oe, grounding-som, grounding-c…
- **eval**: remove the double pre-processing of instances

### Refactor

- simplify logic for truncation to be clearer
- move `async_typer` to `common/`
- rename `run_evaluation.py` to `run_statics.py`
- move span for truncate message history
- Defuser static data generation

## v0.7.1 (2025-12-29)

### Feat

- **eval**: overhaul and simplify static evaluation running
- only pauses the game when all module elements have emerged
- create box warmup-er
- **prompts**: thinking formatting instructions for open-source models
- **observability**: log the step number at the start
- stop google's `Validation on Part Failed`
- set temperature to 0 for evaluation runs

### Fix

- ensure only one model response when pretending to do nothing
- **thinking**: Thoughts format and thinking budget in prompts
- **prompts**: pronouns and thinking tweaks
- **obs**: do not apply som if capabilities do not ask for it
- **observability**: move the `Stop Player` span
- **observability**: remove the track step from recorder
- **observability**: ensure agent run is being sent to logfire
- **configs**: incorrect key for providing image dimensions per model
- **configs**: remove `framework` key from `experiment_generator.yaml`
- **prompts**: remove unused thoughts prompts and include section on reasoning in line with ReAct
- **prompts**: resolve the issue around the agent not getting pronouns
- **prompts**: resolve the issue around the agent not knowing who 'you' and 'I' are

### Refactor

- reorganise and simplify logs and spans
- **observability**: track role and model name with forward pass
- **player/client**: move redis rpc timeout to `ServiceTimeouts`

## v0.7.0 (2025-12-18)

### Feat

- remove thoughts from actions
- use player image dimension for prompts
- support absolute coordinate predictions for interact locations
- **instructions**: also support solo player, not just solo defuser
- adds experiments for multimodule oracle and dummy
- **instructions**: branch paths for instructions based on interaction location method
- **reflection-prompt**: make natural language reflection prompt
- **protocol**: add `interaction_location_method` in the protocol
- add a start time for ExperimentDescriptor
- **actions**: `MagicGameAction` only expects a 'magic' action string
- **metrics**: use classmethod to house logic for collating `ExperimentPlayerRecord`
- **bombstate**: use discriminator union to simplify model validating
- simplify actions for `PromptedOutput`
- adds a script to generate data for statics
- create compose profile for running otel with noop exporter
- **output**: support `PromptedOutput` from pydantic-ai
- adds isEmerged to some bomb state modules
- delay the lights on until bomb is picked up

### Fix

- **model-configs**: update temperature and Qwen model name
- **model-configs**: update temperature and Qwen model name to support thinking models
- **instructions**: remove thoughts logic/prompt references
- **instructions**: remove thoughts logic/prompt references from instruction loading
- make `PlayerCapabilities` hashable
- loading role for instructions (that i messed up)
- only exclude messages if we are playing alone/messages are none
- rotate to include right side
- **actions**: `MagicGameAction` needs a unique title to be available in the scheme
- **modules**: update discriminator value retrieval for serializing
- **models**: update `kind` in result to validate correctly
- **metrics**: sort all step records by timestamp when collating
- **record**: dont show Observation in repr
- use a safer path format for the timestamp
- only make the output dir when we are using it
- **som**: provide correct image shape when calculating region height
- **wandb**: keys for filtering and collating runs
- **wandb**: filter for deleting unneeded
- default none if its an empty string too
- bug in rotation preventing clicks on opposite side
- bug in rotation thats been there unoticed for ages

### Refactor

- **wandb**: automatically use `WANDB_PROJECT` from envvar
- lil fixes to ensure we dont remove the manual and the first obs, only the first obs

## v0.6.0 (2025-12-08)

### Feat

- **metrics**: use disk storage and consolidate wandb uploads
- make all models use NativeOutput

### Fix

- correctly track failed agent runs

## v0.5.1 (2025-12-04)

### Feat

- migrate to PydanticAI's new output format (so everyone supports structured outputs)
- adds magic action and magic defuser
- resize all images if desired by the model
- adds a magic solver endpoint to the mod
- goated magic solver
- **scripts**: merge the open-source models into the `throw.sh` script
- **otel**: include path to logs from outside the container
- adds script for annotating manual for element grounding expert
- **models**: add support for gemini3 pro
- simplify generating experiments for players
- track token usage with wandb (instead of just weave)
- send to logfire via otel collector
- force using CPU torch
- bind player state to the log outputs
- Historical token usage and turn durations from experiments 1.0
- **configs**: (attempt to) disable GPT-5's reasoning
- adds the observations and bomb states to the tracker

### Fix

- **scripts/throw**: make sure we are cleaning up properly
- **player-default**: change open source names
- **model-configs**: update internvl port
- add timeout for stopping the game
- **tokens**: tokens per image in gemini is 258
- if we have the number of image tokens in the usage, just use that
- **tracker**: deep copy the usage when tracking
- **configs**: exclude multi-frame missions from e3
- button emerge on memory and whosonfirst
- remove extra logs from the game
- remove health log
- segm shows only current face modules
- changes the throw script to use gpt5 instead of 4o

### Refactor

- defuser static eval data generation
- **configs**: rely less on `e_`
- adds more spans
- add comments for why tracking obs are done that way

## v0.5.0 (2025-10-28)

### Feat

- make all service communication go through redis
- only gen 5 seeds per mission for single module (e1)
- send traces from ktane to logfire
- **log**: add span to the episode tracker step
- **som**: guard against bbox being outside of the image
- send logs from ktane to logfire
- monkey-patch `BinaryContent.__repr__` to have smaller exceptions
- **prompt**: just warn if the prompt cache has not been initialised
- **script**: add throw script that includes open source models
- restrict manual pages further
- restrict which pages from the manual we use further
- use json repair to attempt to structure string outputs

### Fix

- **deps**: limit wandb to `<0.22.1`
- runusage variable names
- **state-watcher**: do not try to parse state if we know it is invalid
- update throw experiments endpoint to use the new project
- remove typo from gpt-5 name

### Refactor

- move asyncclient creator to the file its used in
- mark `until` as deprecated
- simplify complex nested func
- rename `BaseClient.reset` to `clear_client_url`
- cleanup and improve docs for Event and AsyncValue

## v0.4.1 (2025-10-09)

### Feat

- use the new non-squished manual images
- **configs**: cleanup models and add new ones
- add images for 640 height
- adds game resolution script for comparison
- add o4-mini
- **models**: add claude45

### Fix

- removing the first observation from prompt in single player setting
- removes segmentation mask when bomb is rotated
- logic for detecting content in message history
- use lru_cache when counting tokens from text
- **configs**: update player name for claude 4.5

## v0.4.0 (2025-10-03)

### Feat

- **api**: overhaul the async implementation style
- adds detonating and solving endpoints to the mod
- **seeds**: set single-module num seeds to 10
- **analysis**: add timeout option for pulling from wandb
- Analysis fixes
- **wandb**: centralise run filtering and throwing
- **eval**: support running defuser vqa
- find the best player for e1

### Fix

- intervl token estimate
- **observation**: catch weird binascii error
- **tokens**: check for qwen lowercase
- **config**: make sure we override in case the default changes
- **run-eval**: add dataclass decorator to defuser vqa
- click actions without SOM and dialogue view with defuser only
- preprocess som image for grounding
- preprocess som image for grounding
- **eval**: use a filter for the task type when loading from hf
- adds sleeps when throwing
- position of overlapping wire_seq som labels
- adjusted wire sequence set of marks letter locations
- order regions for wire sequence based on left coords

### Refactor

- mod structure and update client to match new layout
- get rid of caching for results analysis and instead prioritise saving to/loading from disk

## v0.3.2 (2025-06-05)

### Feat

- **results-analysis**: streamlit app for quantitative and qualitative results analysis.
- **expert-vqa**: add more options to the ground truth list
- support trying to convert coordinates back to marks
- **api**: provide communication style in the ExperimentDescriptor
- **configs**: add gpt4o mini
- **eval**: include instruction for mcq questions
- **eval**: ensure expert-vqa runs
- **eval/scorers**: add hallucination scorer
- catch failed wandb run.finish

### Fix

- avoids overlapping click location som for wire sequence
- **som**: reset mark-to-coordinate mapping when a new observation is handled
- flipped the x and y coordinates
- **player/spec**: a solo player does not _need_ a manual
- **prompts**: connect the idea of zooming in to activating the module
- **entrypoints**: missing task name
- **eval/scorer**: update keypad scorer name
- **scorers**: consistent naming and logging of outputs
- **eval/scorers**: keypad wasnt calc'd correctly
- **som**: increase step in value for wire sequence  click point
- increase step in value
- **throw**: also ensure all games are finished
- **throw**: we need to check for at least one game that is valid of all the experiments
- **throw**: update logic to filtering done runs
- **ktane**: reset ktane settings before starting a new game
- **room**: disable the raising when generator exit

### Refactor

- **eval/scorers**: account for trick questions and group results differently
- **eval/scorers**: sentence transformer is not a global
- **eval**: move the skipping outside the step

## v0.3.1 (2025-06-03)

### Feat

- support throwing expert vqa
- **som**: Send click actions to viable leftmost point of selectable rather than the centroid
- use typer to run evaluation in one file
- **api**: catch validation errors from failed observation pulls
- **configs**: allow generating of closed-models only
- **script**: update throw.sh script for new setup
- make spec throwing more efficient
- remove any empty messages from the history
- **logfire**: instrument different player action methods
- **weave**: try adding weave back to the forward pass
- add logs when the player takes too long to respond
- try to make rabbitmq and api more stable
- finish evaluation logger to use HF datasets and to be throwable
- **player**: stop experiment after 5 sequential guard violations
- **rabbitmq**: add exception handler middleware to all services
- cleanup disconnected services
- support deleting uneeded experiments
- **analysis-script**: add analysis script for quantitative analysis …
- **players**: cache the prompt files

### Fix

- we need to exclude the old tag
- we need to exclude the old tag
- **observation**: send correct num frames to the models
- **ai-player**: catch invalid mark locations
- **rabbit**: catch when the api queue doesnt exist and it raises an exception
- ensure the game_id sent to wandb is the experiment ID
- change seeds for human eval
- tool name for dummy defuser return
- remove aiomonitor
- remove debug log point
- changes to get ai-ai to work
- **som**: Do not consider overlapping wire sequence wires as being on the same row
- **player**: send to agent in a different thread to try protect against blocking
- **reflection**: give the reflection message an output type
- try to catch generatorexit exceptions
- **messages**: prevent duplicate messages when removing the empty
- **output-type**: modify the name of the class to remove the bad characters
- remove unsupposed characters from the model name
- **wandb**: send to the correct project
- multiple mod issues
- light glow no longer with segmentation mask, and fixes simon solve progress
- **rabbitmq**: raise exceptions when the player handles from rabbit
- cache the prompts for the tests
- **prompts**: more toning-down of wording
- **prompts**: further remove bomb-related words
- **configs**: incorrect keys for gemini's safety settings
- **prompts**: say the word "bomb" less

### Refactor

- change severity of log levels
- take modules in api out of dirs
- make less log warnings
- **analysis-script**: fix issues flagged by precommit

## v0.3.0 (2025-05-28)

### Feat

- overhaul the entire backend
- create entrypoint to run evaluation
- vqa grounding hf dataset
- make simon says defuser / observation collector script

### Fix

- another fix for module isSolved field
- last memory module change hopefully
- **som**: fix the ordering of wire sequence som labels
- changes the wireSequence state to allow 5 panels
- changes the wireSequence to allow 5 panels

## v0.2.8 (2025-05-26)

### Feat

- **vqa**: Use similarity metrics to compare keypad symbol descriptions to ground truth

## v0.2.7 (2025-05-22)

### Feat

- setup evaluation run with weave
- **ktane**: extend module/widget state and defuser handling

### Fix

- **ktane**: added list of modules on bomb to json

### Refactor

- promote `experiments/` as one of the main packages

## v0.2.6 (2025-05-12)

### Feat

- **ktane**: difficulty ratings for bomb
- **ktane**: calculate difficulty ratings
- **experiments-pairings**: update with_best pairing logic to support different best defuser and best expert
- **configs**: add gemini2.5pro
- **experiment-configs**: update e_4's to reference repeated_modules_4 and make with_self version of e's 4-6
- find the next best seed (and faster)
- add script for checking if there are any duplicate experiments
- **system-promtpts**: create variant of defuser prompt for parallel
- remove cost calc from wandb metrics
- set stop experiment timeout to 300secs
- default to do nothing if the ai goes wrong
- **system-prompts**: Prompt variants (solo defuser) and some tweaks to defuser base
- **configs**: set buffer length to 16
- restructure how we coerce agent outputs
- Better time limits
- only give several observations when zoomed in to a module that wants it
- only give several observations when zoomed in
- make custom InvalidMarkLocationError exception
- catch error if mark_id doesn't exist and do nothing action
- comment out Available rooms / available players debug log

### Fix

- **experiment-configs**: fix typo in pairing
- **config**: output types for experts
- seconds per action -> 3
- **configs**: update player name for gemini2.5 pro
- **prompt/defuser-solo**: set to 4 seconds
- **prompt/defuser**: set to 4 seconds
- experiment names for multi-module settings
- set default seconds per sequential step to the constant
- Make number of button actions dependent on step size
- **ktane/states**: update expected max stage on WhosOnFirst module to match mod
- fix max stage for whos on first
- **ai**: attempt to catch gemini's validation response errors
- handle errors stemming from a borked set of marks location
- set the seconds per action to 4
- switch the wandb ending back to sync
- sh script bs!
- provide information on back placement when generating
- Update the time limits
- remove unnecessary spans

## v0.2.5 (2025-05-08)

### Feat

- improve the prompts
- remove top and bottom som labels for wires
- order set of marks by reading order
- **players/ai**: set the num observations depending on if the mission requires it
- add scripts for throwing
- explicitly track player lifecycle for easier resetting
- **prompt**: coerce the reflection output to avoid sending another request
- disable timeout on stop player experiment, until better idea
- tracks of 'do_nothing' actions in WandB
- **metrics**: track guardrail violations
- **experiment-gen**: remove storing the pairing type, we dont need it
- **configs/experiments**: split e1 into 3 yamls for easier throwing
- **manual**: skip loading of needy manual pages
- **metrics**: track the cost per request and the overall game
- **wandb**: skip runs that have definitely finished
- stop ai after 5 consecutive do-nothing's
- **ai**: remove safety settings for gemini
- **ktane/settings**: create progression.xml if it doesn't exist
- **experiments**: add reasonable turn numbers per module
- **experiment-gen**: support calculating time limits depending on modules
- implement function to check if there are several sequential "do nothings" in the room
- disable automatically readding experiments
- fail after several simultaneous endpoint failures
- add a busy wait interval when loading the game
- adds the side of the bomb to the bomb side
- **metrics**: log step, total tokens, and the number of times truncated
- **metrics**: log tokens per step
- **config**: save defuser window som images
- set httpx limits to numbers and not none
- **wandb**: pass through when finished due to crashed room
- **logfire/metrics**: track finished experiments too
- **logfire/metrics**: add counter when experiment fails
- **logfire/metrics**: track dead and active players separately too
- **logfire/metrics**: add more counters for room deaths
- **logfire**: add metric for player death
- **logfire**: add metrics to watch room health more carefully
- **logfire**: add some system metrics to em/rooms
- **logfire**: track the remaining and running experiments
- **logfire**: add metrics for rooms and players
- **room**: update the settings file on room start

### Fix

- tab spaces in scripts
- Change the output type of open-source models to 'gemini'
- **gemini**: config for model settings for gemini
- clear do nothing and reflections on reset
- **metrics**: track original token counts
- connecting to/from the dialogue space as a watcher/non-player
- **reflections**: claude needs tool outputs for the reflection
- remove `eu.` prefix from claude when determining cost
- **config/claude**: model name for claude on bedrock
- Update time limits calculation
- **experiment**: correctly detect room state
- handle broken imports and tests
- **experiment-gen**: add extra turns for rotating the bomb
- **wandb**: disallow automatic resuming of previous runs
- **ai**: update width/height to better estimate tokens
- **mod**: fix state when zoomed into a module then rotating
- **reflection**: prevent the validation issue with the reflection output
- recursion error
- **prompt**: even more declarative about clicking on modules
- **wandb/metric**: calc step properly
- **prompt**: be more declarative with needing to zoom before clicking
- remove resume time before advancing time
- **prompt**: make a mention about not using a location for release
- guard against needing wandb init before log
- **client**: catch aiohttp exceptions
- catch model name for gpt4o
- **metrics**: log when we know the end is caused by a hard crash
- **configs**: target model for bedrock claude
- **api/player**: remove the timeout when `run-for-turn`
- **config**: use env var to set wandb project
- **ktane**: skip logging while waiting for the game to boot
- **client/ktane**: tests and init-ing that i missed
- send flag when run is crashed
- **reflection**: update init args for ktane client
- **config**: set window length to 12
- **config**: hydra for ai defuser player
- **clients**: automatically create a new client if the old one is closed
- set default httpx timeout to 5
- **sequential**: wait for 3 seconds before running the next step
- Minor fix to match model name with token number for Qwen and InternVL3
- **logfire/metrics**: logic for computing active players/rooms
- **logfire/metrics**: logic for counting rooms/players in an experiment

### Refactor

- player metrics into multiple files
- move the `do nothing` sentinal constant

## v0.2.4 (2025-05-03)

### Feat

- remove older messages when the context is too long
- **experiment_manager**: send final message to dialogue manager
- **metrics**: track invalid format (IF) in wandb
- **ktane**: set game settings on game start
- **em**: prepare for running in production with environment variables
- instansiate httpx's AsyncClient using httpx-aiohttp instead
- **mission_spec**: update time_step_size to 3000 milliseconds across configurations
- **client/player**: try httpx explicit timeout
- **ai/defuser**: use partial structured outputs for gemini
- **wandb**: run wandb.finish in a separate thread
- adds functionality for observation buffer
- **ai/dummy**: make the defuser start from the top for each mission
- **model-configs**: add open source model configs and update player names in player configs
- **config**: set request limit to 1000
- **observability**: more experiment spans
- **observability**: add metaadata when a player dies
- **observability**: update spans in the dialogue space
- **observability**: add spans for the 2 different stop experiment times
- **em**: do not use gather when stopping experiment clients
- **em/sequential**: run defuser first in sequential
- **observability**: add more spans to room manager
- **observability**: add spans to room manager
- **experiment-manager**: make filtering experiments with wandb toggleable, off by default
- **ai/defuser**: add ability to change how long we run game time in sequential mode
- **configs/experiment**: set e1 timelimit to 270
- **player**: put starting experiment inside an `await`
- **sequential**: set waiting for 3 seconds
- **experiment-manager**: Only add experiment specifications to experiment manager if not on wandb
- **configs**: default model to test defuser
- **configs**: remove all usage limits on the ai models by default
- **ai/reflection**: always reflect by default

### Fix

- **models**: remove llama 3.2 from model list due to multi-image restrictions
- **system-prompts**: fix action format in defuser solo prompt
- **defuser**: remove unnecessary asyncio sleep in agent output handling
- Allow image upscaling with no warning
- Add image_resizer to default defuser config
- **ai**: do not send usage in the message
- **gradio**: run human players
- **settings**: path to default settings
- **ai/usage**: only check the token limits
- **ktane/settings**: hopefully use the settings as desired by ktane
- **em**: ensure missions are not configured when the room is in a done state
- fixes state issues and zooming when game is paused
- **client/ktane**: do not raise exceptions while waiting for bomb to start
- **observability**: more span fixes
- **observability**: remove span that makes things confusing in logfire
- **em**: raise exception if we can't configure the experiment
- **api/player/client**: increase timeout when stopping experiment
- **wandb**: use the global wandb instead of the run
- **wandb**: disable checking wandb specs
- removes the bomb zoom-in bug on mission start
- **ai**: reset usage when we reset message history
- **ai/defuser**: remove the healthcheck since we just do it in get state
- **configs/ai**: disable reflection for dummy models
- **configs**: usage limits for models
- **ai/dummy**: make the dummy expert finally work

### Refactor

- allows getting the observation buffer when the game is over

## v0.2.3 (2025-04-30)

### Feat

- **ai/reflection**: support asking for a reflection on the game at the end
- **reflection-prompts**: combine prompts and provide template for output
- **mod**: adds an observation buffer endpoint
- **configs**: add e0 level for stress testing with the dummy players
- **api/room**: log exception when we can't reset the room
- **observability**: add span when running experiment
- **observability**: add more spans
- **state**: add more bomb state properties
- **player**: separate run player methods for parallel and sequential
- **model**: temperature=0, top_p=1
- **system-prompts**: update prompts
- **processors/som**: Change venn module wire labels to be multi-coloured in som
- **state**: add `is_timed_out` property
- **reflection-prompts**: add txt files with automated response to return for the 3 different cases
- **gemini**: add hack to support gemini
- Update experiment definitions
- **observability**: add log when player is connected
- **observability**: add spans to a running experiment
- **som**: update params for som painter
- **scripts/som**: print region colors to help
- **som**: keep white/black colors white/black
- **som**: add anti-aliasing to everything drawn
- **som**: add AA to drawn text
- **experiment-manager**: Fixed player/room disconnect behaviour.
- fixes dummy defuser for testing
- som touchup for zoomed_out and wires sequence
- **processors/som**: increase hsv value of color dependent module masks for greater clarity
- increase hsv value on color dependent modules for clarity
- Password som
- **observability**: add spans during experiment startup
- **client**: get url from supervised clients
- adds wandb tracking, logging to a log file, and updates mod
- **wandb**: remove the `experiment_spec` top level key in the config
- **wandb**: add experiment name to init config
- **wandb**: update init kwargs
- **processors/som**: use alphabet letters for som marks
- Wires som
- Moved common asyncio waits into common/async_ops.py
- Moved common asyncio waits into common/async_ops.py. All healthchecks and busy waits now configured here.
- **experiments**: Added proper UUID4 to players, and added wandb to gitignore
- **processors/som**: Change the colour of the mask for wire sequence buttons if they have the same colour as a wire
- **processsors/som**: use contrast to decide text colour in labels rather than luminence
- use contrast to decide text colour rather than luminence
- make memory module som dynamic
- **processsors/som**: Allow the mask of color dependent modules to be brightened by a factor

### Fix

- **ai/message-history**: do not send previous observations with messages
- **player/ai**: reset message history on connect
- **api/room-manager**: catch timeout errors when supervising ktane client
- **api/connect-room**: handle re-connecting reset rooms
- **api/em**: guard again failures in resetting the room
- **api/player**: when joining, first try to disconnect from the previous room
- **ktane/state**: catch request errors that request when the room is dead
- **experiment/flow**: stop player first, then stop room
- **room/restart-loop**: reset/shutdown order to resume time first before anything else
- **player**: create method to run things on experiment stop
- fix complicated wire color type formatting
- fix complicated wire colour type
- **ai/dummy**: make dummy expert work properly
- **ktane/state**: fix simon says expected beep length
- fix simon says expected beep length
- **player**: run sequential in asyncio task
- **wandb**: call finish at end of player lifespan
- **room/reset**: need to resume the time before resetting the game
- **ktane/state**: Update state to ensure json parses correctly
- **wandb**: use wandb.finish and hope that kills it
- **ktane**: only send action and location to game
- **experiment-generation**: fix for issue with bomb state
- **prompt/defuser**: remove numeric IDs from som
- **prompt/defuser**: update to use letters for SOM
- **config**: output type for gemini 2
- **defuser**: need to run the super `__post_init__`
- **sequential**: increase timeout when running sequential turn
- **state**: remove nones from wires list
- make loads of fixes to make it finally work
- **processors/som**: Move maze som labels so they do not cover buttons
- Move maze labels to not cover buttons
- **metrics**: suppress attribute error
- **player/tracker**: reset instead of reinstantiation
- **experiment-spec**: remove the `__` from the experiment name
- use a different colour for wire sequence buttons if it is the same as a wire colour

### Refactor

- **som**: improve performance and remove redundant code
- **types**: we know its uuid4
- **bomb-state**: use property to get zoomed in component

### Perf

- **test/som**: make images smaller for testing

## v0.2.2 (2025-04-27)

### Feat

- **metrics**: Added metrics to players
- **matchmaking**: Re-added room availability check to matchmaking
- **matchmaking**: Re-added room availability check to matchmaking system.
- complex wires SoM
- **api**: add more logs to the experiment manager api
- **observability**: instrument sending results to wandb
- **processors/som**: Update som to swap text and background colour
- **matchmaking**: Added matchmaking based on player metadata and generate_experiments.py
- **observability**: add more instrumentation to the ai player
- **configs**: add model configurations
- **observability**: add more spans and disable scrubbing
- **observability**: send all pydantic failures to logfire
- **ai/test**: create dummy defuser model for stress tests
- **scripts**: add set of mark viewer to the scripts
- fix SoM to use new labels
- **matchmaking**: Added matchmaking logic impl and ai-ai tests.
- entrypoint for adding experiments
- **logfire**: add spans to get observation
- **player/ai**: support saving images during running to help debugging
- **models**: add gemini to the hydra

### Fix

- **configs**: update pairing names
- **ktane/client**: ensure we do not send thoughts to the ktane client
- asyncio sleep needs awaiting
- type error
- **prompt**: tell defuser about set of marks locations
- **bomb-state**: sequence needs to be a string
- **prompts**: typo in action names
- **actions**: use the subclass for actions when sending
- **api/player**: use the new method to update the client
- **ktane/client**: we need to re-instrument the client
- **playerapi**: ensure only the ktane asyncclient is updated
- **configs-system-prompts**: update the action description to conform with game action types
- **room**: logic to ensure rooms are ready
- **em**: set em port for uvicorn
- **player/ai**: parse action enum from name too
- **api/em**: selecting manager from app.state

### Refactor

- **matchmaking**: make the logic a bit clearer
- **observability**: remove unnecessary instruments
- **metadata**: facilitate instantiating players with metadata
- rename module to prep
- experiment manager api

## v0.2.1 (2025-04-24)

### Feat

- **experiments**: Find best seed to use for experiments

### Fix

- import errors

### Refactor

- **api**: move structures into `api/`

## v0.2.0 (2025-04-24)

### Feat

- add player/room/experiment managers
- **system-prompts**: add system prompt configs and tests

## v0.1.2 (2025-04-23)

### Feat

- **som**: implement labelling and outlining of module selectables from observation and segmentation mask images
- **instrumentation**: add a metaclass with instrumentation mixin
- send additional game metrics sent to wandb
- logging observations into wandb
- player episode tracker
- **ai/defuser**: send actions to the game
- **ktane/executable**: Append instance port number to log filename to allow parallel games
- Black and white SoM, and dilate masks
- **pydantic-ai**: support thoughts in actions
- **ktaneclient**: add image resizer to ktaneclient and add image type conversion processors
- add `no new messages` sentinel token when dialogue space has nothing new
- Set of MASKS
- **ktane/client**: Provide state information when sending action in client
- **ktane/client**: Add methods which allow control of in-game time.
- **ktane/states**: Add module locations to state information
- **ai/expert**: provide manual as user prompt on first message
- get screenshot with segmentation from the endpoint
- **players**: add observation window for the defuser player
- **processors**: add image resizer
- **ktane**: simplify running the game across systems
- sends reset command to reset to main menu
- added reset function to connect to reset endpoint

### Fix

- **logger**: set httpx to warning
- **ktane/states**: update BombState class to include reason for strikes
- **ktane/observation**: revert back to PIL for loading images
- **ktane/client**: Resize segmentation mask to match image size
- **player/ai**: provide output type to pydantic ai
- **view**: fix defuser js observation endpoint not formatting
- **player**: fix human player not connecting to ds
- **ktane/states**: Adjust class structure to fit mod-side structure
- hydra for gradio players
- remove ds pulled message log
- **ktane**: check for alpha chanel on SoM images and discard if necesary

### Refactor

- **players/ai**: output types into their own file
- **pydantic-ai**: rename `result` to `output` since they also changed that in v0.1.0
- **players**: put gradio/ai players under the same interfaces

## v0.1.1 (2025-04-14)

### Feat

- procedural generation of experiment specifications
- **ktane/app**: formatting of ktaneclient baseurl into gradio observations script
- **ktane/app**: ktane baseurl parsed into gradio observation handler
- add set of marks functionality
- add reset method for dialogue space server
- adds reset method for dialogue space server.
- **ktane/states**: Create structure for game state information
- **ktane**: Auto update playerSettings.xml

### Fix

- **app**: mouse leaving bounding box cancels user hold action
- **ktane**: change action endpoint to be correct

### Refactor

- `som/` to `processors/`

## v0.1.0 (2025-04-09)

### Feat

- successful first test of MVP-UI execution
- MVP-UI BABYYYY
- **ktane**: raise InvalidGameError when failed to get observation
- **gradio**: dump conversation history on button click
- **actions**: send actions to mod over http
- **gradio_observations**: Added send observations to gradio
- **gradio/defuser**: add discrete actions
- **app**: add relative click coordinates and ktane client to gradio
- **logging**: only allow configuring logging to run once
- add observations to client, and example file that saves screens…
- **app**: polling of unpulled messages from dialogue space
- add the ktane manual
- **entrypoint**: create entrypoint to start missions
- **settings/paths**: add paths to the local and remote manual
- **settings**: create Pydantic settings for constant paths
- **logging**: improve logging while running things
- **hydra**: disable hydra logging overrides
- **config**: scaffold initial hydra configs
- add Defuser player
- scaffold Ktane client skeleton
- **ui**: add gradio interface for human experiments
- **player**: explicitly track message history for `Player`
- **dialogue-space**: Added entry point for dialogue space
- add base `Player` and `ExpertPlayer`
- **dialogue-space**: add property to know if websocket client is connected
- **dialogue-space**: add dialogue space (server and client)
- **dialogue**: Added basic websocket server and client
- **logger**: add `structlog` and `rich`

### Fix

- **app**: move `gradio_chats` to `storage/outputs`
- **config**: add ktane client to ai/defuser player
- **config**: add game_client target to ai defuser player
- **gradio/chatmessage**: ensure default timezone is UTC
- **gradio_app**: Removed unused method for handling user messages
- resolved minor issue in _async_typer.py preventing start_mission…
- resolved minor issue in _async_typer.py preventing start_mission.py from running
- **entrypoints**: type error for asynctyper commands
- **ktane**: update component list from the README in the mod repo
- pulling own messages from dialogue space server
- **ruff**: tell ruff that WPS exists
- **gitignore**: permit the `packages/` folder at the root of the repo
- **gitignore**: ignore `mise.toml` correctly

### Refactor

- define api spec for sending actions to the game
- use `model_dump` over `dict`
- **app**: rename classes for player views
- **dialogue-space**: make server starting its own method
- rename `packages/environments` to `packages/ktane`


- remove workspaces
