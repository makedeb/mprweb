"use strict";

// Show helper menu.
document.addEventListener("DOMContentLoaded", function() {
	document.querySelector(".install-package").addEventListener("click", function() {
		const packageInstaller = document.querySelector("#pkgdetails .helpers");
		const dimmer = document.querySelector("#dimmer");

		// Activate the dimmer.
		dimmer.classList.remove("hidden");

		// Bring up the package installer menu.
		packageInstaller.classList.remove("hidden");
	});
});

// Process helper menu selector.
document.addEventListener("DOMContentLoaded", function() {
	document.querySelector(".helpers select").addEventListener("change", function(e) {
		const value = e.target.value;
		const items = e.target.parentElement.getElementsByClassName("code-block");

		for (var i=0; i < items.length; i++) {
			if (items[i].classList.contains(value)) {
				items[i].classList.remove("hidden");
			} else {
				items[i].classList.add("hidden");
			};
		};
	});
});

// Remove the darkened background when the helper menu looses focus.
document.addEventListener("DOMContentLoaded", function() {
	const helperMenu = document.querySelector(".helpers");
	const dimmer = document.querySelector("#dimmer");

	document.addEventListener("click", function(e) {
		if (e.target.id == "dimmer") {
			helperMenu.classList.add("hidden");
			dimmer.classList.add("hidden");
		};
	});
});

// For some reason the item in 'select' doesn't reset on a page reload. This function handles that until we can find a fix.
document.addEventListener("DOMContentLoaded", function() {
	const select = document.querySelector(".helpers select")
	select.selectedIndex = 0;
});
