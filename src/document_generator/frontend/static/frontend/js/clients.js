/*
 * Clients list page.
 * Fetches GET /clients/ and renders the table rows.
 *
 * Security rule: every value coming from the API is user-entered data, so
 * DOM nodes are built with document.createElement and populated via
 * textContent only. Never interpolate API strings through innerHTML.
 */
(function () {
    "use strict";

    const tbody = document.getElementById("clients-tbody");
    const errorBanner = document.getElementById("clients-error");

    function showError(message) {
        if (!errorBanner) return;
        errorBanner.textContent = message;
        errorBanner.classList.remove("d-none");
    }

    function hideError() {
        if (!errorBanner) return;
        errorBanner.textContent = "";
        errorBanner.classList.add("d-none");
    }

    function buildCell(text, className) {
        const td = document.createElement("td");
        if (className) td.className = className;
        td.textContent = text;
        return td;
    }

    function fullRow(message, className) {
        const td = buildCell(message, className);
        td.colSpan = 4;
        const tr = document.createElement("tr");
        tr.appendChild(td);
        return tr;
    }

    function buildActionsCell(clientId) {
        const td = document.createElement("td");
        td.className = "table-column-actions";

        const group = document.createElement("div");
        group.className = "btn-group btn-group-sm";

        const editLink = document.createElement("a");
        editLink.className = "btn btn-sm btn-outline-primary";
        editLink.href = "/clients/" + clientId + "/edit/";
        editLink.textContent = "Edit";

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "btn btn-sm btn-outline-danger";
        deleteButton.textContent = "Delete";
        deleteButton.addEventListener("click", () => deleteClient(clientId));

        group.appendChild(editLink);
        group.appendChild(deleteButton);
        td.appendChild(group);
        return td;
    }

    function buildRow(client) {
        const tr = document.createElement("tr");
        tr.appendChild(buildCell(client.client_name));
        tr.appendChild(buildCell(client.client_short_name || "—"));
        tr.appendChild(buildCell(client.client_spoc_name));
        tr.appendChild(buildActionsCell(client.client_id));
        return tr;
    }

    function renderRows(clients) {
        tbody.textContent = "";
        if (!Array.isArray(clients) || clients.length === 0) {
            tbody.appendChild(fullRow("No clients yet — add your first client.", "text-muted"));
            return;
        }
        for (const client of clients) {
            tbody.appendChild(buildRow(client));
        }
    }

    function showLoadingRow() {
        tbody.textContent = "";
        tbody.appendChild(fullRow("Loading clients…", "text-muted"));
    }

    async function loadClients() {
        showLoadingRow();
        try {
            const response = await fetch("/clients/", {
                headers: { "Accept": "application/json" },
            });
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            const clients = await response.json();
            hideError();
            renderRows(clients);
        } catch (error) {
            console.error(error);
            showError("Unable to load clients. Please check the server and try again.");
            tbody.textContent = "";
            tbody.appendChild(fullRow("Unable to load clients.", "text-muted"));
        }
    }

    async function deleteClient(clientId) {
        const confirmed = window.confirm(
            "Delete this client? The client will be deactivated."
        );
        if (!confirmed) return;

        try {
            const response = await fetch("/clients/" + clientId + "/", {
                method: "DELETE",
            });
            if (response.status === 204) {
                await loadClients(); // re-fetch for a consistent view
            } else if (response.status === 404) {
                // Client was already deactivated (or never existed) — the API
                // treats inactive ids as 404 on every endpoint.
                showError("Client no longer active — the list has been refreshed.");
                await loadClients();
            } else {
                const bodyText = await response.text();
                console.error("Delete failed", response.status, bodyText);
                showError("Unexpected error while deleting the client (HTTP " + response.status + ").");
            }
        } catch (error) {
            console.error(error);
            showError("Network error while deleting the client. Is the server running?");
        }
    }

    loadClients();
})();
