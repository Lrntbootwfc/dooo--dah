let currentUser = null;
let vFileSystem = []; 
let currentFileId = null;
let activeAttachedImageBase64 = "";
let clipboardAsset = null;

const emojiBanks = {
    faces: ["😊","😂","🤣","❤️","😍","😎","🦁","🐼","🐱","🦄","👾","🦊","🦉","🔥","💥","⭐","🌟","✨","⚡","🌌","🌈","🌦️","⛄"],
    objects: ["💻","📱","⌨️","🖥️","🖱️","📚","🖋️","☕","🍵","🍕","🧁","🎮","🎸","🎧","📷","🚗","🚀","🛸","🧭","🗺️","🔑","🔒","🛡️","📦"],
    icons: ["🎯","🎨","🎭","🎪","📍","📌","📎","📊","📈","📉","📝","🗂️","📅","📢","🔔","💭","💬","✔️","❌","⚠️","💯","🔱","🌀","🐾"]
};

const themeThemes = {
    "chai-code": { bg: "#0b0d0e", card: "rgba(19, 23, 25, 0.75)", text: "#f3f4f6", accent: "#f97316", border: "rgba(255,255,255,0.05)" },
    "futuristic": { bg: "#03050d", card: "rgba(7, 13, 30, 0.7)", text: "#00f2fe", accent: "#00f2fe", border: "rgba(0, 242, 254, 0.15)" },
    "dark": { bg: "#0c0c0e", card: "rgba(22, 22, 26, 0.75)", text: "#f7fafc", accent: "#9f7aea", border: "rgba(255,255,255,0.04)" },
    "light": { bg: "#f8f9fa", card: "rgba(255, 255, 255, 0.8)", text: "#1a202c", accent: "#6b46c1", border: "rgba(0,0,0,0.06)" },
    "minimalist": { bg: "#ffffff", card: "#ffffff", text: "#000000", accent: "#000000", border: "#111111" }
};

const wallpapers = {
    "chai-code": "#0b0d0e", "futuristic": "#03050d", "dark": "#121214", "light": "#f8f9fa", "minimalist": "#ffffff",
    "wood": "linear-gradient(rgba(0,0,0,0.15), rgba(0,0,0,0.15)), url('https://images.unsplash.com/photo-1541123437800-1bb1317badc2?q=80&width=1600') center/cover no-repeat fixed",
    "meadow": "url('https://images.unsplash.com/photo-1533038590840-1cde6e668a91?q=80&width=1600') center/cover no-repeat fixed",
    "ocean": "url('https://images.unsplash.com/photo-1505118380757-91f5f5632de0?q=80&width=1600') center/cover no-repeat fixed",
    "linen": "url('https://images.unsplash.com/photo-1545062990-4a95e8e4b96d?q=80&width=1600') center/cover no-repeat fixed",
    "cork": "url('https://images.unsplash.com/photo-1586075010923-2dd4570fb338?q=80&width=1600') center/cover no-repeat fixed",
    "sunset": "linear-gradient(135deg, #2b1055, #7597de)", "aurora": "linear-gradient(135deg, #051937, #004d7a, #008793, #00bf72, #a8eb12)",
    "cosmic": "linear-gradient(135deg, #000428, #004e92)", "blossom": "linear-gradient(135deg, #fbc2eb, #a6c1ee)", "lavender": "linear-gradient(135deg, #e0c3fc, #8ec5fc)",
    "monsoon": "linear-gradient(135deg, #2c3e50, #bdc3c7)"
};

const padStyles = {
    "clean-white": { bg: "#ffffff", text: "#1a202c", border: "none", shadow: "0 20px 50px rgba(0,0,0,0.1)", font: "-apple-system, sans-serif" },
    "legal-yellow": { bg: "#fefeb3", text: "#000000", border: "left: 2px solid #ff8888", shadow: "0 20px 50px rgba(0,0,0,0.06)", font: "'Georgia', serif" },
    "parchment": { bg: "#f4ecc8", text: "#4a3319", border: "none", shadow: "0 20px 40px rgba(0,0,0,0.15)", font: "'Georgia', serif" },
    "ivory-smooth": { bg: "#fafaf6", text: "#1c1917", border: "none", shadow: "0 12px 40px rgba(0,0,0,0.08)", font: "-apple-system, sans-serif" },
    "grid-graph": { bg: "#ffffff url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"20\" height=\"20\" viewBox=\"0 0 20 20\"><rect width=\"20\" height=\"20\" fill=\"none\" stroke=\"%23e2e8f0\" stroke-width=\"1\"/></svg>')", text: "#2d3748", border: "none", shadow: "0 12px 36px rgba(0,0,0,0.1)", font: "monospace" },
    "dotted-bullet": { bg: "#ffffff url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"25\" height=\"25\" viewBox=\"0 0 25 25\"><circle cx=\"2\" cy=\"2\" r=\"1\" fill=\"%23cbd5e1\"/></svg>')", text: "#1a202c", border: "none", shadow: "0 12px 36px rgba(0,0,0,0.1)", font: "-apple-system, sans-serif" },
    "vintage-ledger": { bg: "#fcfaf2 url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"100%\" height=\"24\"><line x1=\"0\" y1=\"23\" x2=\"100%\" y2=\"23\" stroke=\"%23bce3f7\" stroke-width=\"1\"/></svg>')", text: "#1c1917", border: "left: 3px double #f87171", shadow: "0 12px 36px rgba(0,0,0,0.12)", font: "'Georgia', serif" },
    "isometric-dot": { bg: "#ffffff url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"30\" height=\"17.32\" viewBox=\"0 0 30 17.32\"><circle cx=\"0\" cy=\"0\" r=\"1\" fill=\"%23cbd5e1\"/><circle cx=\"15\" cy=\"8.66\" r=\"1\" fill=\"%23cbd5e1\"/><circle cx=\"30\" cy=\"0\" r=\"1\" fill=\"%23cbd5e1\"/><circle cx=\"0\" cy=\"17.32\" r=\"1\" fill=\"%23cbd5e1\"/><circle cx=\"30\" cy=\"17.32\" r=\"1\" fill=\"%23cbd5e1\"/></svg>')", text: "#1a202c", border: "none", shadow: "0 12px 36px rgba(0,0,0,0.15)", font: "-apple-system, sans-serif" },
    "midnight-graphite": { bg: "#262626", text: "#f5f5f5", border: "none", shadow: "0 20px 45px rgba(0,0,0,0.3)", font: "-apple-system, sans-serif" },
    "corporate-navy": { bg: "#f8fafc", text: "#0f172a", border: "left: 3px solid #3b82f6", shadow: "0 12px 36px rgba(0,0,0,0.1)", font: "-apple-system, sans-serif" },
    "sage-mint": { bg: "#f0f4f1", text: "#1e293b", border: "none", shadow: "0 20px 45px rgba(0,0,0,0.05)", font: "'Georgia', serif" },
    "dark-terminal": { bg: "#0f141c", text: "#00ff66", border: "none", shadow: "0 25px 60px rgba(0,255,100,0.04)", font: "'Courier New', monospace" },
    "cyber-magenta": { bg: "#1a0b2e url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"30\" height=\"30\" viewBox=\"0 0 30 30\"><rect width=\"30\" height=\"30\" fill=\"none\" stroke=\"%234c1d95\" stroke-width=\"1\"/></svg>')", text: "#ff007f", border: "none", shadow: "0 25px 60px rgba(255,0,127,0.08)", font: "'Courier New', monospace" },
    "blueprint": { bg: "#0244a3 url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"40\" height=\"40\" viewBox=\"0 0 40 40\"><rect width=\"40\" height=\"40\" fill=\"none\" stroke=\"%230d6efd\" stroke-width=\"0.5\"/></svg>')", text: "#ffffff", border: "none", shadow: "0 25px 50px rgba(0,0,0,0.2)", font: "monospace" },
    "monochrome-noir": { bg: "#000000", text: "#ffffff", border: "none", shadow: "0 0 40px rgba(255,255,255,0.04)", font: "-apple-system, sans-serif" }
};

function openStudioDrawer(id) { document.getElementById(id).classList.add("open"); }
function closeStudioDrawer(id) { document.getElementById(id).classList.remove("open"); }

function switchRibbonTab(tabName) {
    document.querySelectorAll(".ribbon-tab-link").forEach(b => b.classList.remove("active"));
    document.getElementById(`tabLink${tabName}`).classList.add("active");
    if(tabName === 'Home') { document.getElementById('ribbonTabHome').classList.remove('hidden'); document.getElementById('ribbonTabInsert').classList.add('hidden'); }
    else { document.getElementById('ribbonTabHome').classList.add('hidden'); document.getElementById('ribbonTabInsert').classList.remove('hidden'); }
}

function switchStickerGroup(catName) {
    document.querySelectorAll("#stickerPalletDrawer .ribbon-tab-link").forEach(b => b.classList.remove("active"));
    if(window.event) window.event.target.classList.add("active");
    const grid = document.getElementById("infiniteStickerContainer"); grid.innerHTML = "";
    emojiBanks[catName].forEach(emoji => {
        const item = document.createElement("div"); item.className = "sticker-item"; item.innerText = emoji;
        item.onclick = () => injectSticker(emoji); grid.appendChild(item);
    });
}

function applyOuterWallpaper(val) { 
    document.getElementById("workspaceScrollerNode").style.background = wallpapers[val] || val; 
    const themeNode = themeThemes[val] || themeThemes["chai-code"];
    if(themeNode) {
        document.documentElement.style.setProperty('--bg', themeNode.bg);
        document.documentElement.style.setProperty('--card', themeNode.card);
        document.documentElement.style.setProperty('--text', themeNode.text);
        document.documentElement.style.setProperty('--accent', themeNode.accent);
        document.documentElement.style.setProperty('--border', themeNode.border);
    }
}

function applyPadStyle(val) {
    const conf = padStyles[val];
    if(conf) {
        document.documentElement.style.setProperty('--pad-bg', conf.bg);
        document.documentElement.style.setProperty('--pad-text', conf.text);
        document.documentElement.style.setProperty('--pad-border', conf.border);
        document.documentElement.style.setProperty('--pad-shadow', conf.shadow);
        document.documentElement.style.setProperty('--pad-font', conf.font);
    }
}

async function handleLogin() {
    const username = document.getElementById("authUsername").value.trim();
    const password = document.getElementById("authPassword").value.trim();
    try {
        const res = await fetch(`${API_BASE}/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
        const data = await res.json();
        if(!res.ok) return alert(data.error);
        currentUser = data.username; vFileSystem = data.fs_tree;
        document.getElementById("authScreen").classList.add("hidden");
        document.getElementById("appInterface").classList.remove("hidden");
        document.getElementById("drawerTriggerDeck").classList.remove("hidden");
        switchStickerGroup('faces'); renderTreeGrid(); applyOuterWallpaper("chai-code"); applyPadStyle("clean-white");
    } catch(e) { alert("Cannot reach server database volume context engine!"); }
}

async function handleSignup() {
    const username = document.getElementById("authUsername").value.trim();
    const password = document.getElementById("authPassword").value.trim();
    try {
        const res = await fetch(`${API_BASE}/signup`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }) });
        const data = await res.json(); alert(data.message || data.error);
    } catch(e) { alert("Server pipeline connection failure."); }
}

async function syncWithServer() {
    const avatar_desc = document.getElementById("avatarConfig").value;
    await fetch(`${API_BASE}/save`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username: currentUser, fs_tree: vFileSystem, avatar_desc }) });
}

function executeRichFormat(command, value = null) { document.execCommand(command, false, value); updateMetadataCounters(); }
function updateMetadataCounters() {
    const text = document.getElementById("editorEngine").innerText.trim();
    document.getElementById("charCount").innerText = `Characters: ${text.length}`;
    document.getElementById("wordCount").innerText = `Words: ${text === "" ? 0 : text.split(/\s+/).length}`;
}

function handleImageAttachment(event) {
    const file = event.target.files[0]; if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
        activeAttachedImageBase64 = e.target.result;
        document.getElementById("mediaUploadBox").classList.remove("hidden");
        document.getElementById("attachedImagePreview").src = activeAttachedImageBase64;
    };
    reader.readAsDataURL(file);
}

function removeAttachedImage() {
    activeAttachedImageBase64 = ""; document.getElementById("mediaUploadBox").classList.add("hidden");
    document.getElementById("attachedImagePreview").src = ""; document.getElementById("localImagePicker").value = "";
}

function injectSticker(emojiChar) {
    if(!currentFileId) return alert("Select an active file from your ledger system directory first!");
    const pad = document.getElementById("journalPadSheet");
    const node = document.createElement("div");
    node.className = "sticker-node"; node.style.left = "160px"; node.style.top = "240px";
    node.innerHTML = `${emojiChar}<div class="delete-sticker" onclick=\"this.parentElement.remove(); syncStickersToData();\">×</div>`;
    setupDraggableElement(node);
    node.ondblclick = () => {
        let currentScale = node.style.transform ? parseFloat(node.style.transform.replace("scale(", "").replace(")", "")) : 1;
        let nextScale = currentScale >= 2.5 ? 0.8 : currentScale + 0.3;
        node.style.transform = `scale(${nextScale})`; syncStickersToData();
    };
    pad.appendChild(node); syncStickersToData();
}

function setupDraggableElement(elmnt) {
    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
    elmnt.onmousedown = (e) => {
        if(e.target.className === "delete-sticker") return;
        e.preventDefault(); pos3 = e.clientX; pos4 = e.clientY;
        document.onmouseup = () => { document.onmouseup = null; document.onmousemove = null; syncStickersToData(); };
        document.onmousemove = (ev) => {
            ev.preventDefault(); pos1 = pos3 - ev.clientX; pos2 = pos4 - ev.clientY;
            pos3 = ev.clientX; pos4 = ev.clientY;
            elmnt.style.top = (elmnt.offsetTop - pos2) + "px"; elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
        };
    };
}

function syncStickersToData() {
    if(!currentFileId) return; const doc = findNodeRecursive(vFileSystem, currentFileId);
    if(doc) {
        const collection = [];
        document.querySelectorAll(".sticker-node").forEach(node => {
            collection.push({ char: node.childNodes[0].textContent, top: node.style.top, left: node.style.left, transform: node.style.transform });
        });
        doc.stickers = collection;
    }
}

function renderTreeGrid() {
    const container = document.getElementById("treeView"); container.innerHTML = "";
    container.appendChild(buildRecursiveDOM(vFileSystem));
}

function buildRecursiveDOM(nodes) {
    const wrapper = document.createElement("div");
    nodes.forEach(node => {
        const block = document.createElement("div"); block.className = "node-block";
        const row = document.createElement("div"); row.className = `node-row ${currentFileId === node.id ? 'active' : ''}`;
        if(node.type === "folder") row.setAttribute("data-folder-id", node.id);
        
        const titleSpan = document.createElement("span");
        titleSpan.innerHTML = node.type === "folder" ? `📁 <b>${node.name}</b>` : `📄 ${node.name}`;
        
        if(node.type === "file") { 
            titleSpan.onclick = () => openDocument(node.id); 
        } else { 
            titleSpan.onclick = () => { 
                document.querySelectorAll('[data-folder-id]').forEach(f=>f.classList.remove('active')); 
                row.classList.add('active'); row.setAttribute('id', 'selectedFolderTarget'); 
            }; 
                }
        row.appendChild(titleSpan);

        const dots = document.createElement("span");
        dots.className = "dots-menu-btn"; dots.innerText = " ⋮";
        dots.onclick = (e) => { e.stopPropagation(); closeAllContextMenus(); menuBox.style.display = "block"; };
        row.appendChild(dots);

        const menuBox = document.createElement("div");
        menuBox.className = "context-menu";
        if(node.type === "folder") {
            menuBox.innerHTML = `
                <div onclick="addChildFile('${node.id}')">+ New File</div>
                <div onclick="addChildFolder('${node.id}')">+ Sub-Folder</div>
                <div onclick="renameNode('${node.id}')">Rename</div>
                <div onclick="pasteNode('${node.id}')">Paste here</div>
                <div onclick="deleteNode('${node.id}')" style="color:#ef4444;">Delete</div>
            `;
        } else {
            menuBox.innerHTML = `
                <div onclick="cutNode('${node.id}')">Cut File</div>
                <div onclick="renameNode('${node.id}')">Rename</div>
                <div onclick="deleteNode('${node.id}')" style="color:#ef4444;">Delete</div>
            `;
        }
        row.appendChild(menuBox); block.appendChild(row);
        if(node.type === "folder" && node.children && node.children.length > 0) { 
            const subTree = buildRecursiveDOM(node.children); subTree.className = "file-list"; block.appendChild(subTree); 
        }
        wrapper.appendChild(block);
    });
    return wrapper;
}

function closeAllContextMenus() { document.querySelectorAll('.context-menu').forEach(m => m.style.display = "none"); }

function addRootFolder() {
    const t = prompt("Name root folder:"); if(!t) return;
    vFileSystem.push({ id: "fold_" + Date.now(), type: "folder", name: t, children: [] });
    renderTreeGrid(); syncWithServer();
}

function addChildFile(parentFolderId) {
    const t = prompt("File name:"); if(!t) return;
    const parent = findNodeRecursive(vFileSystem, parentFolderId);
    const stamp = new Date().toLocaleString();
    const newFile = { id: "file_" + Date.now(), type: "file", name: t, content: "Start writing...", mood: "😊", created: stamp, edited: stamp, comic: "" };
    if(!parent.children) parent.children = [];
    parent.children.push(newFile); renderTreeGrid(); syncWithServer(); openDocument(newFile.id);
}

function addChildFolder(parentFolderId) {
    const t = prompt("Folder name:"); if(!t) return;
    const parent = findNodeRecursive(vFileSystem, parentFolderId);
    if(!parent.children) parent.children = [];
    parent.children.push({ id: "fold_" + Date.now(), type: "folder", name: t, children: [] });
    renderTreeGrid(); syncWithServer();
}

function renameNode(id) {
    const target = findNodeRecursive(vFileSystem, id);
    const n = prompt("Rename:", target.name);
    if(n) { target.name = n; renderTreeGrid(); syncWithServer(); if(currentFileId === id) document.getElementById("openTitle").innerText = "📄 " + n; }
}

function deleteNode(id) {
    if(confirm("Delete item?")) {
        removeNodeRecursive(vFileSystem, id);
        if(currentFileId === id) {
            currentFileId = null;
            document.getElementById("openTitle").innerText = "No File Selection Active";
            document.getElementById("editorEngine").innerHTML = "";
            document.getElementById("comicBoard").classList.add("hidden");
        }
        renderTreeGrid(); syncWithServer();
    }
}

function cutNode(id) {
    clipboardAsset = removeNodeRecursive(vFileSystem, id);
    document.getElementById("clipboardStatus").innerText = `Moving: [${clipboardAsset.name}]`;
    renderTreeGrid();
}

function pasteNode(targetFolderId) {
    if(!clipboardAsset) return;
    const targetParent = findNodeRecursive(vFileSystem, targetFolderId);
    if(!targetParent.children) targetParent.children = [];
    targetParent.children.push(clipboardAsset); clipboardAsset = null;
    document.getElementById("clipboardStatus").innerText = "";
    renderTreeGrid(); syncWithServer();
}

function findNodeRecursive(nodes, id) {
    for(let node of nodes) {
        if(node.id === id) return node;
        if(node.type === "folder" && node.children) {
            let found = findNodeRecursive(node.children, id); if(found) return found;
        }
    } return null;
}

// Fixed structural splice routine to ensure hierarchy array manipulation stability
function removeNodeRecursive(nodes, id) {
    for(let i=0; i<nodes.length; i++) {
        if(nodes[i].id === id) return nodes.splice(i, 1)[0];
        if(nodes[i].type === "folder" && nodes[i].children) {
            let removed = removeNodeRecursive(nodes[i].children, id); if(removed) return removed;
        }
    } return null;
}

function openDocument(id) {
    currentFileId = id; const doc = findNodeRecursive(vFileSystem, id);
    if(doc) {
        document.getElementById("openTitle").innerText = doc.name;
        document.getElementById("editorEngine").innerHTML = doc.content;
        document.getElementById("timestampBox").innerText = `Created: ${doc.created} | Revised: ${doc.edited || doc.created}`;
        document.getElementById("docMood").value = doc.mood || "😊";
        updateMetadataCounters();
        
        if(doc.attached_image) {
            activeAttachedImageBase64 = doc.attached_image;
            document.getElementById("mediaUploadBox").classList.remove("hidden");
            document.getElementById("attachedImagePreview").src = activeAttachedImageBase64;
        } else { removeAttachedImage(); }

        document.querySelectorAll(".sticker-node").forEach(n => n.remove());
        (doc.stickers || []).forEach(stk => {
            const node = document.createElement("div"); node.className = "sticker-node"; node.style.top = stk.top; node.style.left = stk.left; node.style.transform = stk.transform || "";
            node.innerHTML = `${stk.char}<div class="delete-sticker" onclick=\"this.parentElement.remove(); syncStickersToData();\">×</div>`;
            setupDraggableElement(node); node.ondblclick = () => { let currentScale = node.style.transform ? parseFloat(node.style.transform.replace("scale(", "").replace(")", "")) : 1; let nextScale = currentScale >= 2.5 ? 0.8 : currentScale + 0.3; node.style.transform = `scale(${nextScale})`; syncStickersToData(); };
            document.getElementById("journalPadSheet").appendChild(node);
        });

        if(doc.comic) {
            document.getElementById("comicBoard").classList.remove("hidden");
            document.getElementById("comicFrameTarget").src = doc.comic;
        } else { document.getElementById("comicBoard").classList.add("hidden"); }
    } renderTreeGrid();
}

async function saveActiveDocumentServer() {
    if(!currentFileId) return alert("Select a document first!");
    syncStickersToData(); const doc = findNodeRecursive(vFileSystem, currentFileId);
    if(doc) {
        doc.content = document.getElementById("editorEngine").innerHTML;
        doc.attached_image = activeAttachedImageBase64;
        doc.mood = document.getElementById("docMood").value;
        doc.edited = new Date().toLocaleString();
    }
    await syncWithServer(); renderTreeGrid(); alert("Notebook committed permanently to database!");
}

async function renderAICohesiveComicServer() {
    if(!currentFileId) return alert("Select a document first!");
    const rawContent = document.getElementById("editorEngine").innerText;
    const avatarDescription = document.getElementById("avatarConfig").value.trim();
    const integrationStyle = document.getElementById("artIntegrationStyle").value;
    const currentMood = document.getElementById("docMood").value;
    const img = document.getElementById("comicFrameTarget");
    
    if(!rawContent.trim()) return alert("Write down text before generating images.");
    document.getElementById("comicBoard").classList.remove("hidden");
    img.src = "https://images.squarespace-cdn.com/content/v1/5bde1447a977868019fb0ee7/1559867451375-GR32T0K0S5UVD8B5S7X1/loading-buffering.gif";

    let integrationText = "";
    if(activeAttachedImageBase64 && integrationStyle === "interact") {
        integrationText = "The character is actively holding, inspecting, or working with an external item matching the text details. ";
    } else if(activeAttachedImageBase64 && integrationStyle === "background") {
        integrationText = "An item matching the text details is resting visible in the room background environmental scenery decor layers. ";
    }

    let avatarStr = avatarDescription ? `Recurring character: ${avatarDescription}. ` : "";
    const finalPrompt = `Sequential 4-panel indie graphic novel comic book page layout cells. High contrast clean crisp black and white ink sketch illustration style. ${avatarStr}${integrationText}Scene story description with mood expression ${currentMood}: ${rawContent}. Absolutely no text lettering or speech bubbles inside the panels.`;

    try {
        const res = await fetch(`${API_BASE}/render-comic`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username: currentUser, prompt: finalPrompt, image_seed: activeAttachedImageBase64 })
        });
        const data = await res.json();
        if(data.image_data_url) {
            img.src = data.image_data_url;
            const doc = findNodeRecursive(vFileSystem, currentFileId);
            if(doc) doc.comic = data.image_data_url;
            await syncWithServer();
        }
    } catch(e) { alert("Art processing server error."); }
}

function extractAllFilesFromBranch(node) {
    let collector = []; if(!node) return collector;
    if(node.type === "file") collector.push(node);
    if(node.type === "folder" && node.children) {
        node.children.forEach(child => { collector = collector.concat(extractAllFilesFromBranch(child)); });
    }
    return collector;
}

function compileSelectedFolderPDF() {
    const selectedRow = document.getElementById("selectedFolderTarget");
    if(!selectedRow) return alert("Select a folder in your tree directory to target it for compilation!");
    
    const folderId = selectedRow.parentElement.getAttribute("data-folder-id");
    const targetedFolderNode = findNodeRecursive(vFileSystem, folderId);
    const activeComicFiles = extractAllFilesFromBranch(targetedFolderNode).filter(file => file.comic && file.comic !== "");
    
    if(activeComicFiles.length === 0) return alert(`No active generated comic panel frames found under the path: "${targetedFolderNode.name}"`);

    const { jsPDF } = window.jspdf; const pdf = new jsPDF('p', 'mm', 'a4');
    activeComicFiles.forEach((file, index) => {
        if (index > 0) pdf.addPage();
        pdf.rect(10, 10, 190, 277); pdf.setFillColor(22, 26, 30); pdf.rect(10, 10, 190, 15, 'F');
        pdf.setTextColor(255,255,255); pdf.setFontSize(11); 
        pdf.text(`VOLUME: ${targetedFolderNode.name.toUpperCase()} | NODE REF: ${file.name.toUpperCase()}`, 15, 19);
        try { 
            pdf.addImage(file.comic, 'PNG', 15, 35, 180, 180); 
        } catch(e) { 
            pdf.setTextColor(0,0,0); pdf.text("[Visual Panel Static Asset Layer Bound]", 45, 120); 
        }
    });
    pdf.save(`Volume_Book_Compilation_${targetedFolderNode.name.replace(/\s+/g, '_')}.pdf`);
}

function logout() { location.reload(); }