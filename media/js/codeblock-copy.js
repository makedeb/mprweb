"use strict";

document.addEventListener("DOMContentLoaded", function() {
	const icons = document.querySelectorAll(".clipboard-icon");

	for (var i = 0; i < icons.length; i++) {
		icons[i].addEventListener("click", function(e) {
			var clipboardIcon;

			// If we clicked the <path> item, go to the parent.
			if (e.target.tagName === "path") {
				clipboardIcon = e.target.parentElement;
			} else {
				clipboardIcon = e.target;
			};
			
			const checkIcon = clipboardIcon.parentElement.getElementsByClassName("check-icon")[0]
			const codeContent = clipboardIcon.parentElement.parentElement.getElementsByTagName("code")[0].textContent;
			navigator.clipboard.writeText(codeContent);

			// Temporarily replace the clipboard icon with the checkmark icon.
			clipboardIcon.style.display = "none";
			checkIcon.style.display = "inline";

			setTimeout(function() {
				clipboardIcon.style.display = "inline";
				checkIcon.style.display = "none";
			}, 1000);
		});
	};
});
