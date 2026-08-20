() => {
	// Rule-seed labels are merger UI annotations, not part of the accepted handbook pages.
	document.querySelectorAll(".page-header-section-title").forEach((element) => {
		element.textContent = element.textContent.replace(
			/\s+—\s+rule seed:\s+\d+$/i,
			"",
		);
		element.classList.remove("ruleseed-seeded");
	});
	// Headers and footers supplied by the merger would otherwise duplicate printed page chrome.
	document
		.querySelectorAll(".ruleseed-header,.page-footer")
		.forEach((element) => element.remove());
};
