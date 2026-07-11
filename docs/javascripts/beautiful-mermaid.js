// Renders ```mermaid fences as SVG with beautiful-mermaid.
//
// Zensical emits each fence as <pre class="beautiful-mermaid">...source...</pre>
// (see the superfences custom_fences block in zensical.toml). The class is
// deliberately not "mermaid": the theme bundle renders .mermaid blocks with its
// own stock mermaid.js, so a distinct class keeps those two off each other and
// lets this renderer own the fences. This module reads the fence source,
// renders a self-contained SVG, and swaps it in. No build step: the
// library is an ESM bundle pulled from esm.run, which inlines its elkjs and
// entities dependencies. Pinned to a version because the bundle is generated
// on the fly, so subresource integrity hashes do not apply.
import {
	renderMermaidSVG,
	THEMES,
} from "https://esm.run/beautiful-mermaid@1.1.3";

// beautiful-mermaid theme per Zensical colour scheme. "slate" is the dark
// palette configured under [[project.theme.palette]].
const LIGHT = "github-light";
const DARK = "github-dark";

function themeFor() {
	const scheme = document.body.dataset.mdColorScheme;
	return THEMES[scheme === "slate" ? DARK : LIGHT];
}

function render() {
	const theme = themeFor();
	for (const el of document.querySelectorAll(".beautiful-mermaid")) {
		// Keep the original source on the element so a palette toggle can re-render
		// from it rather than from the already-injected SVG.
		const source = (el.dataset.mermaidSource ??= el.textContent.trim());
		try {
			el.innerHTML = renderMermaidSVG(source, { ...theme, transparent: true });
		} catch (error) {
			// Isolate one unsupported diagram: leave its source on screen and report
			// it, rather than blanking the block or aborting the whole page.
			console.error("beautiful-mermaid failed to render a diagram", error);
		}
	}
}

// document$ emits on first load and on every instant navigation (navigation.instant
// is enabled), so diagrams render on client-side page changes too. Fall back to a
// one-shot listener if the theme does not expose it.
if (window.document$?.subscribe) {
	window.document$.subscribe(render);
} else {
	document.addEventListener("DOMContentLoaded", render);
}

// Re-render when the reader flips the light/dark palette toggle.
new MutationObserver(render).observe(document.body, {
	attributes: true,
	attributeFilter: ["data-md-color-scheme"],
});
