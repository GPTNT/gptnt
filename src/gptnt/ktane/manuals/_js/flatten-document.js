() => {
	// Resolve local references before the cloned fragments leave their original frame URL.
	const absoluteUrl = (value) => {
		if (
			!value ||
			value.startsWith("#") ||
			value.startsWith("data:") ||
			value.startsWith("blob:") ||
			value.startsWith("about:")
		)
			return value;
		return new URL(value, document.baseURI).href;
	};
	// CSS url(...) references need the same treatment as HTML src and href attributes.
	const absoluteCss = (value) =>
		value.replace(
			/url\(\s*(?:(['"])(.*?)\1|([^'"\s\)]+))\s*\)/g,
			(_match, _quote, quotedUrl, unquotedUrl) =>
				`url("${absoluteUrl(quotedUrl ?? unquotedUrl)}")`,
		);
	// Work on a deep clone so cleanup cannot mutate the live source frame before validation.
	const clone = document.documentElement.cloneNode(true);
	const originals = Array.from(document.documentElement.querySelectorAll("*"));
	const copies = Array.from(clone.querySelectorAll("*"));
	// Read resolved DOM properties from the live nodes and write portable values into each copy.
	originals.forEach((original, index) => {
		const copy = copies[index];
		for (const name of ["src", "href", "poster", "data"]) {
			if (original.hasAttribute(name)) {
				copy.setAttribute(name, absoluteUrl(original.getAttribute(name)));
			}
		}
		if (original.hasAttribute("srcset"))
			copy.setAttribute("srcset", original.srcset);
		if (original.hasAttribute("style")) {
			copy.setAttribute("style", absoluteCss(original.getAttribute("style")));
		}
	});
	// Scripts have already run; removing them prevents a second execution in the flat print tree.
	clone.querySelectorAll("script").forEach((element) => element.remove());
	clone.querySelectorAll("style").forEach((element) => {
		element.textContent = absoluteCss(element.textContent);
	});
	// Return only ordered stylesheet fragments and printable sections needed by the Python printer.
	const head = Array.from(
		clone.querySelectorAll('head > link[rel~="stylesheet"], head > style'),
	).map((element) => element.outerHTML);
	const sections = Array.from(clone.querySelectorAll("body > .section"))
		.map((element) => element.outerHTML)
		.join("\n");
	return { head, sections };
};
