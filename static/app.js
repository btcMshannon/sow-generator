// static/app.js

document.addEventListener("DOMContentLoaded", () => {
    const chargerSel = document.getElementById("charger_type");
    const sowSel = document.getElementById("sow");
    const genBtn = document.getElementById("generateBtn");
    const sowContent = document.getElementById("sowContent");
    const customerSel = document.getElementById("customer");
    const pdfBtn = document.getElementById("pdfBtn");

    if (!chargerSel || !sowSel || !genBtn || !sowContent || !customerSel || !pdfBtn) {
        return;
    }
    
    // --- Initial State and Reset ---
    function resetSow() {
        sowSel.innerHTML = '<option value="">Select...</option>';
        sowSel.setAttribute("disabled", "disabled");
        genBtn.setAttribute("disabled", "disabled");
        pdfBtn.setAttribute("disabled", "disabled");
        sowContent.value = "";
    }
    resetSow();
    
    // --- Event Listeners ---
    chargerSel.addEventListener("change", async () => {
        const chargerId = chargerSel.value;
        resetSow();
        if (!chargerId) return;

        try {
            const resp = await fetch(`/api/sows?charger_type_id=${encodeURIComponent(chargerId)}`, {
                headers: { "Accept": "application/json" }
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const list = await resp.json();

            if (Array.isArray(list) && list.length) {
                list.forEach(({ id, title }) => {
                    const opt = document.createElement("option");
                    opt.value = id;
                    opt.textContent = title || `(untitled ${id})`;
                    sowSel.appendChild(opt);
                });
                sowSel.removeAttribute("disabled");
            } else {
                sowSel.innerHTML = '<option value="">No SOWs available</option>';
            }
        } catch (e) {
            console.error("Failed to load SOWs:", e);
        }
    });

    sowSel.addEventListener("change", () => {
        if (sowSel.value) {
            genBtn.removeAttribute("disabled");
            pdfBtn.removeAttribute("disabled");
        } else {
            genBtn.setAttribute("disabled", "disabled");
            pdfBtn.setAttribute("disabled", "disabled");
        }
    });
    
    // --- The new generateSOW function ---
    window.generateSOW = async function() {
        const sowId = sowSel.value;
        if (!sowId) {
            return;
        }

        try {
            const sowResp = await fetch(`/api/sows/${sowId}`);
            if (!sowResp.ok) throw new Error(`HTTP ${sowResp.status}`);
            const sowData = await sowResp.json();
            
            let content = '';
            
            content += `SOW Created [${new Date().toLocaleString()}]\n`;
            content += 'TECH SUPPORT CONTACT INFORMATION:\n';
            content += 'BTC Power Technical Support Hotline 1-855-901-1558\n\n';

            if (customerSel.value) {
                const customerResp = await fetch(`/api/customers/${customerSel.value}`);
                if (!customerResp.ok) throw new Error(`HTTP ${customerResp.status}`);
                const customerData = await customerResp.json();

                content += 'CUSTOMER CHECK-IN INFORMATION\n';
                if (customerData.check_in_contact) content += `Check-in Contact: ${customerData.check_in_contact}\n`;
                if (customerData.check_in_phone) content += `Check-in Phone: ${customerData.check_in_phone}\n`;
                if (customerData.check_in_instructions) content += `Check-in Instructions: ${customerData.check_in_instructions}\n`;
                content += '\n';
            }

            content += `Title\n${sowData.title}\n\n`;
            if (sowData.maintenance_scope) content += `MAINTENANCE SCOPE\n${sowData.maintenance_scope}\n\n`;
            if (sowData.parts) content += `PARTS\n${sowData.parts}\n\n`;
            if (sowData.tools) content += `TOOLS\n${sowData.tools}\n\n`;
            if (sowData.documents) content += `DOCUMENTS\n${sowData.documents}\n\n`;
            if (sowData.service_instructions) content += `SERVICE INSTRUCTIONS\n${sowData.service_instructions}\n\n`;

            if (customerSel.value) {
                const customerResp = await fetch(`/api/customers/${customerSel.value}`);
                const customerData = await customerResp.json();
                
                content += 'CUSTOMER CHECK-OUT INFORMATION\n';
                if (customerData.check_out_contact) content += `Check-out Contact: ${customerData.check_out_contact}\n`;
                if (customerData.check_out_phone) content += `Check-out Phone: ${customerData.check_out_phone}\n`;
                if (customerData.check_out_instructions) content += `Check-out Instructions: ${customerData.check_out_instructions}\n`;
            }

            sowContent.value = content.trim();

        } catch (e) {
            console.error("Failed to generate SOW:", e);
            sowContent.value = "Error generating SOW. Please check the console for details.";
        }
    };

    window.startOver = () => {
        chargerSel.value = "";
        customerSel.value = "";
        resetSow();
    };

    window.copyToClipboard = () => {
        if (!sowContent.value) {
            alert("No SOW content to copy!");
            return;
        }
        navigator.clipboard.writeText(sowContent.value).then(() => {
            alert("SOW content copied to clipboard!");
        }).catch(err => {
            console.error("Failed to copy:", err);
            alert("Failed to copy. Please try manually.");
        });
    };
    
    // Note: downloadPDF will be added later when that functionality is wired up
    window.downloadPDF = () => {
        alert("PDF generation is not yet implemented in this new structure.");
    };
});
