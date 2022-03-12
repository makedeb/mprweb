// Automatic package listings for search bar in MPR-specific navigation menu.
"use strict";

let searchResultItemClass = "search-result-item";

async function makeRequest(url) {
	const response = await fetch(url);
	return response.json();
};

async function findPackages(e) {
	var data = e.target.value;

	if (data == "") {
		return;
	}
	
	var response = await makeRequest(window.location.protocol + "//" + window.location.host + "/rpc/?v=5&type=search&arg=".concat(data));
	var results = response["results"].slice(0,10);
	var pkgnames = [];
	
	// We only want the first 10 items.
	for (var i = 0; i < results.length; i++) {
		pkgnames.push(results[i]["Name"]);
	}

	const searchResults = document.querySelector(".navbar-search .search-results");

	searchResults.innerHTML = "";

	// Hide the search results div if we got no results.
	if ( results.length === 0) {
		searchResults.style.display = "none";
		return;
	};

	// Otherwise make sure the div is shown and generate the results.
	searchResults.style.display = "inherit";

	for (var i = 0; i < pkgnames.length; i++) {
		searchResults.innerHTML += `<a class="${searchResultItemClass}" href="/packages/${pkgnames[i]}"><p>${pkgnames[i]}</p></a>`;
	};
}

document.addEventListener("DOMContentLoaded", function() {
	// Package searches.
	document.querySelector(".search-box").addEventListener("input", findPackages);

	// Make sure to hide the generated div if the search box looses focus AND we didn't click a link in the search results.
	document.addEventListener("click", function(e) {
		if (! e.target.classList.contains(searchResultItemClass)) {
			document.querySelector(".navbar-search .search-results").style.display = "none";
		};
	});
});
