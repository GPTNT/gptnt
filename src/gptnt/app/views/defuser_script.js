function setupClick() {
	const video = document.getElementById("video_feed");
	if (!video) {
		console.log("Video element not found.");
		return;
	}

	const outputBox = document.querySelector("#real_box textarea");

	let mouseDownTimer = null;

	function handleMouseEvent(event) {
		const boundingBox = document
			.getElementById("img_tag")
			.getBoundingClientRect();
		const relativeX = (event.clientX - boundingBox.left) / boundingBox.width;
		const relativeY = (event.clientY - boundingBox.top) / boundingBox.height;

		if (event.type === "mousedown") {
			// Start a delay before sending the mousedown message
			mouseDownTimer = setTimeout(() => {
				// Math.random is to prevent .change from having the same message and not actually changing
				const message = `Mousedown at X: ${relativeX} Y: ${relativeY} Random: ${Math.random()}`;
				outputBox.value = message;
				outputBox.dispatchEvent(new Event("input"));
				mouseDownTimer = null;
			}, 125);
		} else if (event.type === "mouseup") {
			// If mousedown message hasn't been sent yet, cancel it
			if (mouseDownTimer) {
				clearTimeout(mouseDownTimer);
				mouseDownTimer = null;
			}
			// Math.random is to prevent .change from having the same message and not actually changing
			const message = `Mouseup at X: ${relativeX} Y: ${relativeY} Random: ${Math.random()}`;
			outputBox.value = message;
			outputBox.dispatchEvent(new Event("input"));
		}
	}

	video.addEventListener("mousedown", handleMouseEvent);
	video.addEventListener("mouseup", handleMouseEvent);

	// Observations
	const img = document.getElementById("img_tag");
	const poll_observation = () => {
		if (img) {
			observation = fetch(
				{ observation_endpoint },
				{
					mode: "cors",
				},
			).then((res) => {
				res.text().then((observation) => {
					img.src = `data:image/png;base64, ${observation}`;
				});
			});
		}
	};

	setInterval(poll_observation, 250);
}
