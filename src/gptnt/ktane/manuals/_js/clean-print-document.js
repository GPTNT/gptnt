() => {
	document.querySelectorAll(".page-header-section-title").forEach((element) => {
		element.textContent = element.textContent.replace(
			/\s+—\s+rule seed:\s+\d+$/i,
			"",
		);
		element.classList.remove("ruleseed-seeded");
	});
	document
		.querySelectorAll(".ruleseed-header,.page-footer")
		.forEach((element) => element.remove());
};
