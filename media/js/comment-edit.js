// Function to handle swapping between showing a comment and bringing up the edit form.
"use strict";

function commentEdit() {
	let editIcons = document.querySelectorAll(".pencil-icon");
	for (var i = 0; i < editIcons.length; i++) {
		editIcons[i].addEventListener("click", function(e) {
			var target = e.target
			var classes = target.classList;
	
			// We target an SVG for the toggle, but if the user hits the '<path>' element inside of the SVG, it won't register. Likewise, we should go up one element if we hit the '<path>' element.
			if (target.localName == "path") {
				var target = target.parentNode;
				var classes = target.classList;
			};

			// Find the comment header containing our comment ID.
			while (target.id.match(/^comment-/) === null) {
				var target = target.parentNode;
			}
			
			// Get the parent of our match so we can find the position of our current target.
			var targetParent = target.parentNode;

			// Find the position of the target in the target's parent.
			var pos;

			for (i = 0; i < targetParent.children.length; i++) {
				if (targetParent.children[i].id == target.id) {
					var pos = i;
				};
			};

			// The next element is going to be the content of the comment. The one after that will be the form.
			var content = targetParent.children[pos+1];
			var form = targetParent.children[pos+2];
			
			// Reverse showing of the content and form.
			if (content.style.display != "none") {
				content.style.display = "none";
				form.style.display = "inline";
			} else {
				content.style.display = "inline";
				form.style.display = "none";
			};
		});
	};
};

document.addEventListener("DOMContentLoaded", commentEdit);
