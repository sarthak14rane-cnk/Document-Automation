/*
 * Add/Edit client form page.
 * Sends all six business keys on every submit (the API's PUT contract
 * requires every key; POST is sent with the same payload shape so
 * add/edit behaviour stays symmetrical).
 */
(function () {
    "use strict";

    const form = document.getElementById("client-form");
    if (!form) {
        return;
    }

    const errorBanner = document.getElementById("form-error");
    const FIELD_NAMES = [
        "client_name",
        "client_short_name",
        "client_industries",
        "client_spoc_name",
        "client_spoc_email",
        "list_of_entities",
    ];

    const mode = form.dataset.mode || "create";
    const clientId = form.dataset.clientId || "";

    function fieldInput(field) {
        return form.querySelector('[name="' + field + '"]');
    }

    function fieldFeedback(field) {
        return form.querySelector('[data-error-for="' + field + '"]');
    }

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

    function clearErrors() {
        for (const field of FIELD_NAMES) {
            const input = fieldInput(field);
            if (input) input.classList.remove("is-invalid");
            const feedback = fieldFeedback(field);
            if (feedback) feedback.textContent = "";
        }
        hideError();
    }

    function applyInlineErrors(field, messages) {
        const input = fieldInput(field);
        const feedback = fieldFeedback(field);
        if (input && feedback) {
            input.classList.add("is-invalid");
            feedback.textContent = messages;
            return true;
        }
        return false;
    }

    /*
     * Maps a DRF error payload ({"field": [msg]} or {"detail": msg}) onto the
     * form: keys matching form fields get inline errors, everything else
     * (including the "detail" key) lands in the banner.
     */
    function applyApiErrors(payload) {
        let applied = false;
        const bannerMessages = [];
        for (const field of Object.keys(payload)) {
            const raw = payload[field];
            const text = Array.isArray(raw) ? raw.join(" ") : String(raw);
            if (applyInlineErrors(field, text)) {
                applied = true;
            } else {
                bannerMessages.push(text);
            }
        }
        if (bannerMessages.length > 0) {
            showError(bannerMessages.join(" "));
            applied = true;
        }
        return applied;
    }

    function showClientSideValidationError() {
        let firstInvalid = null;
        for (const field of FIELD_NAMES) {
            const input = fieldInput(field);
            if (!input) continue;
            input.classList.remove("is-invalid");
            const feedback = fieldFeedback(field);
            if (feedback) feedback.textContent = "";
            if (!input.checkValidity()) {
                input.classList.add("is-invalid");
                if (feedback) feedback.textContent = input.validationMessage;
                if (!firstInvalid) firstInvalid = input;
            }
        }
        form.classList.add("was-validated");
        if (firstInvalid) firstInvalid.focus();
    }

    function parseList(value) {
        return String(value)
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function buildPayload() {
        return {
            client_name: fieldInput("client_name").value,
            client_short_name: fieldInput("client_short_name").value,
            client_industries: parseList(fieldInput("client_industries").value),
            client_spoc_name: fieldInput("client_spoc_name").value,
            client_spoc_email: fieldInput("client_spoc_email").value,
            list_of_entities: parseList(fieldInput("list_of_entities").value),
        };
    }

    async function prefill() {
        try {
            const response = await fetch("/clients/" + clientId + "/", {
                headers: { "Accept": "application/json" },
            });
            if (response.status === 404) {
                // Inactive or unknown id — the API contract for detail reads.
                showError("Client not found or no longer active.");
                for (const field of FIELD_NAMES) {
                    const input = fieldInput(field);
                    if (input) input.disabled = true;
                }
                const submitButton = form.querySelector('button[type="submit"]');
                if (submitButton) submitButton.disabled = true;
                return;
            }
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            const client = await response.json();
            if (!client || typeof client !== "object") {
                throw new Error("Malformed client payload");
            }
            fieldInput("client_name").value = client.client_name ?? "";
            fieldInput("client_short_name").value = client.client_short_name ?? "";
            fieldInput("client_industries").value = Array.isArray(client.client_industries)
                ? client.client_industries.join(", ")
                : "";
            fieldInput("client_spoc_name").value = client.client_spoc_name ?? "";
            fieldInput("client_spoc_email").value = client.client_spoc_email ?? "";
            fieldInput("list_of_entities").value = Array.isArray(client.list_of_entities)
                ? client.list_of_entities.join(", ")
                : "";
        } catch (error) {
            console.error(error);
            showError("Unable to load client details for editing. Please try again later.");
        }
    }

    async function submitForm(event) {
        event.preventDefault();
        clearErrors();
        form.classList.remove("was-validated");

        if (!form.checkValidity()) {
            showClientSideValidationError();
            return;
        }

        const isEdit = mode === "edit" && clientId !== "";
        const url = isEdit ? "/clients/" + clientId + "/" : "/clients/";
        const method = isEdit ? "PUT" : "POST";

        try {
            const response = await fetch(url, {
                method: method,
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body: JSON.stringify(buildPayload()),
            });

            if (response.status === 200 || response.status === 201) {
                window.location.href = "/";
                return;
            }

            let apiPayload = null;
            try {
                apiPayload = await response.json();
            } catch (parseError) {
                // Non-JSON error body — fall through with apiPayload null.
            }
            if (apiPayload && applyApiErrors(apiPayload)) {
                console.error("Save failed", response.status, apiPayload);
            } else {
                console.error("Save failed", response.status, apiPayload);
                showError("Unexpected error while saving (HTTP " + response.status + "). Please try again.");
            }
        } catch (error) {
            console.error(error);
            showError("Network error while saving. Is the server running?");
        }
    }

    form.addEventListener("submit", submitForm);

    if (mode === "edit" && clientId !== "") {
        prefill();
    }
})();
