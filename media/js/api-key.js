// Functions to add and remove API keys.
"use strict";

// Show API key creation menu.
document.addEventListener("DOMContentLoaded", function() {
	const addApiKeyButton = document.querySelector(".add-new-api-key");

	addApiKeyButton.querySelector("input").addEventListener("click", function() {
		addApiKeyButton.classList.add("hidden");

		const addApiKeyMenu = document.querySelector(".api-key-menu");
		addApiKeyMenu.classList.remove("hidden");
	});
});

// Create API key.
document.addEventListener("DOMContentLoaded", function() {
	document.querySelector(".add-new-api-key-button").addEventListener("click", async function() {
		const apiKeyNote = document.querySelector(".add-new-api-key-note").value;
		const apiKeyExpirationDate = Date.parse(
			document.querySelector(".add-new-api-key-expiration-date").value
		) / 1000;
		const apiKeyData = {note: apiKeyNote, expirationDate: apiKeyExpirationDate};

		// If the user didn't enter a valid date, abort.
		if (Number.isNaN(apiKeyExpirationDate)) {
			return;
		}

		// Create the new API key.
		const response = await fetch("/api-keys/create", {
			method: "POST",
			body: JSON.stringify(apiKeyData)
		});

		// If the request failed, don't do anything.
		// TODO: Add a proper error message for the user.
		if (response.status != 200) {
			return;
		}

		// Otherwise, show the secret to the user.
		const secret = await response.text();
		const addApiKeyButton = document.querySelector(".add-new-api-key");
		const addApiKeyMenu = document.querySelector(".api-key-menu");
		const newApiKey = document.querySelector(".new-api-key");

		addApiKeyMenu.classList.add("hidden");
		addApiKeyButton.classList.remove("hidden");

		newApiKey.innerHTML = "<hr>";
		newApiKey.innerHTML += `<p>New API Key: <code>${secret}</code></p>`;
		newApiKey.innerHTML += "<p class=\"comment\"><em>Make sure this key is recorded wherever it's needed, as it won't be shown again.</em></p>";
		newApiKey.classList.remove("hidden");
	});
});

// Delete function.
document.addEventListener("DOMContentLoaded", function() {
	const apiKeys = document.querySelectorAll(".api-key-delete");

	for (var i = 0; i < apiKeys.length; i++) {
		apiKeys[i].addEventListener("click", async function(e) {
			var target = e.target;
			var classList = Array.from(target.classList);

			// Get the ID for this current item.
			var apiKeyID = classList.filter(word => word != "api-key-delete")[0].replace("id-", "");

			// Delete the API key from the server.
			var response = await fetch(`/api-keys/delete/${apiKeyID}`, {method: "POST"});

			// If we succesfully deleted the API key, remove it from the currently shown list.
			if (response.status == 200) {
				target.parentElement.parentElement.parentElement.remove();
			};
		});
	};
});
