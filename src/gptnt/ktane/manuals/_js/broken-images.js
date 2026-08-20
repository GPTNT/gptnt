() =>
	Array.from(document.images)
		.filter((image) => !image.naturalWidth)
		.map((image) => image.src);
