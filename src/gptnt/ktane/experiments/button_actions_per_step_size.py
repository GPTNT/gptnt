from itertools import islice


def count_steps_to_see_digits(step_size: int, start_time: int) -> int:
    """Count how many steps it will take to see digits 1, 4, and 5 in the time format mins:secs.

    Parameters:
        step_size (int): The increment in seconds for each step.

    Returns:
        int: The number of steps needed to see all three digits.
        -1: If step_size is invalid (≤ 0).
        -2: If maximum iteration count is reached (safety measure).
    """
    # Handle edge case: invalid step_size
    if step_size <= 0:
        return -1

    # Initialize variables
    seen_1 = False
    seen_4 = False
    seen_5 = False
    steps = 0
    max_iterations = 100000  # Safeguard against infinite loops

    # Continue until we've seen all three digits
    while not (seen_1 and seen_4 and seen_5):
        steps += 1
        start_time += step_size

        # Convert total_seconds to mins:secs format
        mins = start_time // 60
        secs = start_time % 60
        time_str = f"{mins}:{secs:02d}"  # Format with leading zeros for seconds

        # Check if the target digits appear in the time string
        if "1" in time_str:
            seen_1 = True
        if "4" in time_str:
            seen_4 = True
        if "5" in time_str:
            seen_5 = True

        # Safety check to prevent infinite loops
        if steps >= max_iterations:
            return -2

    return steps


def compute_button_holding_steps(step_size: int) -> int:
    """Count the number of steps needed to see digits 1, 4, and 5 in the time format mins:secs."""
    # Use itertools to generate multiples of step_size efficiently
    multiples = islice((multiplier * step_size for multiplier in range(1, 11)), 10)
    last_digits = {multiple % 10 for multiple in multiples}
    max_iterations = max(
        count_steps_to_see_digits(step_size, last_digit) for last_digit in last_digits
    )
    return max_iterations - 1
