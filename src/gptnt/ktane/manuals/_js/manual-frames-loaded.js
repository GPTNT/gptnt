(count) => {
	// The merger appends one iframe for every module token in the uploaded profile.
	return document.querySelectorAll(".manuals > iframe").length === count;
};
