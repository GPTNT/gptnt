() => {
	// A completed image with no natural width failed to decode or load its source.
	return Array.from(document.images)
		.filter((image) => !image.naturalWidth)
		.map((image) => image.src);
};
