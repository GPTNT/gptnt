() => {
	// Printing must wait until the browser has resolved every requested web font.
	return document.fonts.status === "loaded";
};
