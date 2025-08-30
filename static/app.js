// static/app.js
// Populates the SOW dropdown when a Charger Type is selected.

document.addEventListener("DOMContentLoaded", () => {
  const chargerSel = document.getElementById("charger_type");
  const sowSel = document.getElementById("sow");
  const genBtn = document.getElementById("generateBtn");

  function resetSow() {
    if (!sowSel) return;
    sowSel.innerHTML = '<option value="">Select...</option>';
    sowSel.setAttribute("disabled", "disabled");
    if (genBtn) genBtn.setAttribute("disabled", "disabled");
  }

  // initial state
  resetSow();

  chargerSel?.addEventListener("change", async () => {
    const chargerId = chargerSel.value;
    resetSow();
    if (!chargerId) return;

    try {
      const resp = await fetch(`/api/sows?charger_type_id=${encodeURIComponent(chargerId)}`, {
        headers: { "Accept": "application/json" }
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const list = await resp.json(); // expects [{id, title}]

      if (Array.isArray(list) && list.length) {
        list.forEach(({ id, title }) => {
          const opt = document.createElement("option");
          opt.value = id;
          opt.textContent = title ?? `(untitled ${id})`;
          sowSel.appendChild(opt);
        });
        sowSel.removeAttribute("disabled");
      }
    } catch (e) {
      console.error("Failed to load SOWs:", e);
    }
  });

  sowSel?.addEventListener("change", () => {
    if (!genBtn) return;
    if (sowSel.value) genBtn.removeAttribute("disabled");
    else genBtn.setAttribute("disabled", "disabled");
  });
});
