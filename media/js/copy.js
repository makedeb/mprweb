// Functions to automatically copy the given text to the clipboard.
"use strict";

document.addEventListener("DOMContentLoaded", function() {
	const copyItems = document.querySelectorAll(".copy");

	for (var item = 0; item < copyItems.length; item ++) {
		copyItems[item].addEventListener("click", function(e) {
			navigator.clipboard.writeText(e.target.textContent);
		});
	};
});
