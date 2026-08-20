() => {
	// complete covers both successful and failed loads; broken-images.js distinguishes them.
	return Array.from(document.images).every((image) => image.complete);
};
