// Functions to handle section toggles on '/packages/{pkgname}' routes.
"use strict";

function setSection(className) {
	// Set all headers to not be active.
	var sections = document.querySelectorAll(".sections h2");

	for (var i = 0; i < sections.length; i++) {
		sections[i].classList.remove("active");

		// If this section matches the requested class, set it to active.
		if (sections[i].classList.contains(className)) {
			sections[i].classList.add("active");
		};
	};

	const sectionContents = document.querySelector(".pages").children;

	for (var section = 0; section < sectionContents.length; section ++) {
		sectionContents[section].classList.add("hidden");

		// If the current one is for our header, show it.
		if (sectionContents[section].classList.contains(className)) {
			sectionContents[section].classList.remove("hidden");
		};
	};
};

function goToSection() {
	const curId = window.location.hash.substring(1);

	if (curId != "") {
		setSection(curId);
	}
};

function packageSections() {
	const sections = document.querySelectorAll(".sections h2");

	for (var i = 0; i < sections.length; i ++) {
		sections[i].addEventListener("click", function(e) {
			// Get the classname for our current header.
			var curClassName = null;

			for (var curClass = 0; curClass < e.target.classList.length; curClass ++) {
				if (["text", "active"].includes(e.target.classList[curClass]) === false) {
					curClassName = e.target.classList[curClass];
					window.location.hash = curClassName;
					break;
				};
			};

			setSection(curClassName);
		});
	};
};

document.addEventListener("DOMContentLoaded", packageSections);
document.addEventListener("DOMContentLoaded", goToSection);
