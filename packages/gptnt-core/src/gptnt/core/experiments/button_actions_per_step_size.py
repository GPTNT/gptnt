def count_steps_to_see_digits(  # noqa: WPS231
    step_size: int, start_time: int, *, max_iterations: int = 100000
) -> int:
    """Count how many steps it will take to see digits 1, 4, and 5 in the time format MM:SS.

    Parameters:
        step_size (int): The increment in seconds for each step.

    Returns:
        int: The number of steps needed to see all three digits.
    """
    # Handle edge case: invalid step_size
    if step_size <= 0:
        raise ValueError("step_size must be greater than 0")

    # Initialize variables
    has_seen_1 = False
    has_seen_4 = False
    has_seen_5 = False
    steps = 0

    # Continue until we've seen all three digits
    while not (has_seen_1 and has_seen_4 and has_seen_5):
        steps += 1
        start_time += step_size

        # Convert total_seconds to mins:secs format
        mins = start_time // 60
        secs = start_time % 60
        time_str = f"{mins}:{secs:02d}"  # Format with leading zeros for seconds

        # Check if the target digits appear in the time string
        if "1" in time_str:
            has_seen_1 = True
        if "4" in time_str:
            has_seen_4 = True
        if "5" in time_str:
            has_seen_5 = True

        # Safety check to prevent infinite loops
        if steps >= max_iterations:
            raise RecursionError(
                "Maximum iteration count reached. Check your logic or increase `max_iterations`."
            )

    return steps


def compute_button_holding_steps(step_size: int) -> int:
    """Count the number of steps needed to see digits 1, 4, and 5 in the time format mins:secs."""
    # Use itertools to generate multiples of step_size efficiently
    max_iterations = max(
        count_steps_to_see_digits(step_size, last_digit) for last_digit in range(10)
    )
    return max_iterations - 1
