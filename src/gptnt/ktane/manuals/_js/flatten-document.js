() => {
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
	const absoluteCss = (value) =>
		value.replace(
			/url\(\s*(['"]?)([^'"\)]+)\1\s*\)/g,
			(_match, _quote, url) => `url("${absoluteUrl(url)}")`,
		);
	const clone = document.documentElement.cloneNode(true);
	const originals = Array.from(document.documentElement.querySelectorAll("*"));
	const copies = Array.from(clone.querySelectorAll("*"));
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
	clone.querySelectorAll("script").forEach((element) => element.remove());
	clone.querySelectorAll("style").forEach((element) => {
		element.textContent = absoluteCss(element.textContent);
	});
	const head = Array.from(
		clone.querySelectorAll('head > link[rel~="stylesheet"], head > style'),
	).map((element) => element.outerHTML);
	const sections = Array.from(clone.querySelectorAll("body > .section"))
		.map((element) => element.outerHTML)
		.join("\n");
	return { head, sections };
};
