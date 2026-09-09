/* CarHero -- chat client (SSE streaming, 3-pane interactions). */

(() => {
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => Array.from(document.querySelectorAll(sel));

    let currentSessionId = getSidFromURL();
    let currentAgentSlug = null;
    let streaming = false;

    const AGENT_PROMPTS = readJsonScript("agent-prompts-data") || {};
    const AGENT_NAMES = readJsonScript("agent-names-data") || {};
    const AGENT_PREFIX_MAP = readJsonScript("agent-prefix-map") || {};

    function readJsonScript(id) {
        const el = document.getElementById(id);
        if (!el) return null;
        try { return JSON.parse(el.textContent); }
        catch (e) { return null; }
    }

    function getSidFromURL() {
        const p = new URLSearchParams(window.location.search);
        return p.get("sid") || "";
    }
    function setSid(sid) {
        currentSessionId = sid;
        const u = new URL(window.location);
        u.searchParams.set("sid", sid);
        history.replaceState(null, "", u);
    }

    function addBubble(role, text, agentSlug) {
        const wrap = document.createElement("div");
        wrap.className = `msg msg-${role}`;
        if (role === "assistant" && agentSlug) {
            const hdr = document.createElement("div");
            hdr.className = "msg-agent";
            const nice = AGENT_NAMES[agentSlug] || agentSlug;
            hdr.innerHTML = `<span class="msg-agent-icon">*</span><span class="msg-agent-label">${nice}</span>`;
            wrap.appendChild(hdr);
        }
        const bubble = document.createElement("div");
        bubble.className = "msg-bubble";
        bubble.textContent = text;
        wrap.appendChild(bubble);
        $("#messages").appendChild(wrap);
        scrollMessagesBottom();
        return bubble;
    }

    function appendToolLog(bubble, name, args) {
        let log = bubble.parentElement.querySelector(".tool-log");
        if (!log) {
            log = document.createElement("div");
            log.className = "tool-log";
            bubble.parentElement.appendChild(log);
        }
        const step = document.createElement("div");
        step.className = "tool-step";
        step.innerHTML = `-> <span class="tool-name">${name}</span>`;
        log.appendChild(step);
    }

    function scrollMessagesBottom() {
        const m = $("#messages");
        if (m) m.scrollTop = m.scrollHeight;
    }

    function renderMarkdownLite(text) {
        if (window.marked) return marked.parse(text);
        return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/\n/g, "<br>");
    }

    function tableToCSV(table) {
        const rows = [];
        table.querySelectorAll("tr").forEach(tr => {
            const cells = [];
            tr.querySelectorAll("th, td").forEach(td => {
                cells.push('"' + td.textContent.trim().replace(/"/g, '""') + '"');
            });
            rows.push(cells.join(","));
        });
        return rows.join("\n");
    }

    function enhanceTables(container) {
        if (!container) return;
        container.querySelectorAll("table").forEach(table => {
            if (table.dataset.enhanced) return;
            table.dataset.enhanced = "1";
            const toolbar = document.createElement("div");
            toolbar.className = "table-toolbar";
            const copyBtn = document.createElement("button");
            copyBtn.textContent = "Copy CSV";
            copyBtn.className = "table-action-btn";
            copyBtn.onclick = () => {
                navigator.clipboard.writeText(tableToCSV(table)).then(() => {
                    copyBtn.textContent = "Copied!";
                    setTimeout(() => { copyBtn.textContent = "Copy CSV"; }, 1500);
                });
            };
            const dlBtn = document.createElement("button");
            dlBtn.textContent = "Download CSV";
            dlBtn.className = "table-action-btn";
            dlBtn.onclick = () => {
                const blob = new Blob([tableToCSV(table)], { type: "text/csv" });
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = "carhero-data.csv";
                a.click();
                URL.revokeObjectURL(a.href);
            };
            toolbar.appendChild(copyBtn);
            toolbar.appendChild(dlBtn);
            table.parentNode.insertBefore(toolbar, table);
        });
    }

    // -- Thinking indicator --
    let thinker = null;
    function showThinking(bubble) {
        if (!bubble) return;
        thinker = {
            started: Date.now(),
            tool: null,
            el: document.createElement("div"),
            timerId: null,
        };
        thinker.el.className = "thinking-indicator";
        thinker.el.innerHTML = `<span class="dot"></span><span class="label">Thinking... <span class="secs">0s</span></span>`;
        bubble.parentElement.insertBefore(thinker.el, bubble);
        thinker.timerId = setInterval(updateThinking, 500);
    }
    function updateThinking() {
        if (!thinker) return;
        const secs = Math.floor((Date.now() - thinker.started) / 1000);
        const label = thinker.tool
            ? `Thinking... <span class="secs">${secs}s</span> -- calling <code>${thinker.tool}</code>`
            : `Thinking... <span class="secs">${secs}s</span>`;
        thinker.el.querySelector(".label").innerHTML = label;
    }
    function setThinkingTool(name) {
        if (!thinker) return;
        thinker.tool = name;
        updateThinking();
    }
    function hideThinking() {
        if (!thinker) return;
        clearInterval(thinker.timerId);
        if (thinker.el && thinker.el.parentElement) thinker.el.parentElement.removeChild(thinker.el);
        thinker = null;
    }

    // -- Sample cards --
    window.updateSampleCards = (slug) => {
        const row = $("#sample-cards-row");
        if (!row) return;

        let prompts = (slug && AGENT_PROMPTS[slug]) || [];
        if (!prompts.length) {
            prompts = [
                "search: BMW X5 under 40k EUR",
                "market: BMW 3 Series depreciation trends",
                "value: 2020 Mercedes C300, 45k km",
                "compare: Audi Q5 vs BMW X3 vs Volvo XC60",
                "advise: EUR 50,000 budget, family SUV",
            ];
        }
        row.innerHTML = "";
        prompts.slice(0, 6).forEach(p => {
            const b = document.createElement("button");
            b.className = "sample-card";
            b.title = p;
            const span = document.createElement("span");
            span.className = "sample-card-text";
            span.textContent = p;
            b.appendChild(span);
            b.onclick = () => { fillChat(p); sendMessage(null); };
            row.appendChild(b);
        });
    };

    window.onInputChange = (ta) => {};

    if ($("#sample-cards-row")) updateSampleCards(null);

    // -- SSE send --
    async function sendMessage(evt) {
        if (evt) evt.preventDefault();
        if (streaming) return;
        const ta = $("#chat-input");
        if (!ta) return;
        const msg = ta.value.trim();
        if (!msg) return;

        streaming = true;
        const sendBtn = $("#send-btn");
        if (sendBtn) sendBtn.disabled = true;

        const wh = $("#welcome-hero");
        if (wh) wh.style.display = "none";

        addBubble("user", msg);
        ta.value = "";
        ta.style.height = "";

        const body = new URLSearchParams({ msg, sid: currentSessionId || "" });
        const resp = await fetch("/app/chat", { method: "POST", body });
        if (!resp.ok) {
            addBubble("assistant", "Error: " + resp.status);
            streaming = false;
            if (sendBtn) sendBtn.disabled = false;
            return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let bubble = null;
        let accumulated = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            let idx;
            while ((idx = buffer.indexOf("\n\n")) !== -1) {
                const raw = buffer.slice(0, idx);
                buffer = buffer.slice(idx + 2);
                handleEvent(raw, (type, payload) => {
                    if (type === "agent_route") {
                        const nice = payload.agent || AGENT_NAMES[payload.slug] || payload.slug;
                        const label = $("#current-agent-label");
                        if (label) label.textContent = nice;
                        currentAgentSlug = payload.slug;
                        updateSampleCards(payload.slug);
                        bubble = addBubble("assistant", "", payload.slug);
                        bubble.classList.add("streaming");
                        showThinking(bubble);
                    } else if (type === "token") {
                        if (!bubble) bubble = addBubble("assistant", "", "");
                        if (accumulated === "") hideThinking();
                        accumulated += payload.text;
                        bubble.innerHTML = renderMarkdownLite(accumulated);
                        scrollMessagesBottom();
                    } else if (type === "tool_start") {
                        setThinkingTool(payload.name);
                        appendToolLog(bubble || addBubble("assistant", "", ""), payload.name, payload.args);
                    } else if (type === "tool_end") {
                        // noop
                    } else if (type === "artifact_show") {
                        showArtifact(payload);
                    } else if (type === "error") {
                        hideThinking();
                        if (!bubble) bubble = addBubble("assistant", "", "");
                        bubble.textContent = "Error: " + (payload.message || "unknown");
                    } else if (type === "session") {
                        if (payload.sid) setSid(payload.sid);
                    } else if (type === "done") {
                        hideThinking();
                        if (bubble) bubble.classList.remove("streaming");
                        enhanceTables(bubble);
                    }
                });
            }
        }
        streaming = false;
        if (sendBtn) sendBtn.disabled = false;
    }

    function handleEvent(raw, cb) {
        let type = null; let data = "";
        for (const line of raw.split("\n")) {
            if (line.startsWith("event: ")) type = line.slice(7).trim();
            else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (!type) return;
        try { cb(type, data ? JSON.parse(data) : {}); }
        catch (e) { console.error("bad sse line", raw, e); }
    }

    // -- Artifacts --
    function showArtifact(payload) {
        const body = $("#artifact-body");
        const empty = $("#artifact-empty");
        if (empty) empty.style.display = "none";
        if (body) body.style.display = "block";

        const sub = $("#artifact-subtitle");
        if (sub) sub.textContent = payload.subtitle || "";

        const card = document.createElement("div");
        card.className = "artifact-card";
        const title = payload.title || "Canvas";
        const kind = payload.kind || "note";
        card.innerHTML = `
            <div class="meta">${kind}</div>
            <h4>${title}</h4>
            <div class="body">${renderArtifactHTML(payload)}</div>
        `;
        body.prepend(card);
        enhanceTables(card);

        if (payload.kind === "chart" && payload.figure) {
            const chartDiv = card.querySelector(".body");
            const chartId = "chart-" + Math.random().toString(36).slice(2, 8);
            const plotContainer = document.createElement("div");
            plotContainer.id = chartId;
            plotContainer.style.width = "100%";
            plotContainer.style.minHeight = "300px";
            chartDiv.innerHTML = "";
            chartDiv.appendChild(plotContainer);
            if (window.Plotly) {
                Plotly.newPlot(chartId, payload.figure.data, payload.figure.layout, { responsive: true });
            }
        }

        const isMobile = window.innerWidth <= 768;
        if (!isMobile) {
            document.querySelector(".app").classList.remove("pane-closed");
            const rp = $("#right-pane");
            if (rp) rp.classList.add("open");
            const ab = $("#artifact-btn");
            if (ab) ab.classList.add("active");
        } else {
            const tog = $("#right-pane-toggle-btn");
            if (tog) tog.classList.add("has-results");
        }
    }

    function renderArtifactHTML(p) {
        if (p.kind === "chart") {
            return '<div style="color:var(--ink-muted);font-size:12px">Loading chart...</div>';
        }
        if (p.kind === "deals" && Array.isArray(p.deals)) {
            if (!p.deals.length) return '<p style="color:var(--ink-muted)">No deals found.</p>';
            return p.deals.map(d => {
                const ch = d.cheapest;
                const pr = d.priciest;
                const fmtPrice = n => "EUR " + Number(n).toLocaleString();
                const fmtKm = n => n ? Number(n).toLocaleString() + " km" : "";
                const specs = (o) => [o.variant, o.year, fmtKm(o.mileage_km), o.fuel_type, o.transmission].filter(Boolean).join(" · ");
                const badgeColor = d.savings_pct >= 15 ? "#16A34A" : d.savings_pct >= 8 ? "#F59E0B" : "#6B7280";
                return `
                <div class="deal-card">
                    <div class="deal-header">
                        <span class="deal-title">${d.make} ${d.model}</span>
                        <span class="deal-badge" style="background:${badgeColor}">Save ${d.savings_pct.toFixed(0)}%</span>
                    </div>
                    <div class="deal-row deal-priciest">
                        <div class="deal-row-label">Higher price</div>
                        <div class="deal-row-price">${fmtPrice(pr.price_eur)}</div>
                        <div class="deal-row-source">${pr.provider_label} · ${pr.country_label}</div>
                        <div class="deal-row-specs">${specs(pr)}</div>
                        ${pr.url ? `<a href="${pr.url}" target="_blank" class="deal-link">View listing &rarr;</a>` : ""}
                    </div>
                    <div class="deal-savings">
                        <span class="deal-savings-arrow">&#x2193;</span>
                        Save <strong>${fmtPrice(d.savings_eur)}</strong>
                    </div>
                    <div class="deal-row deal-cheapest">
                        <div class="deal-row-label">Lower price</div>
                        <div class="deal-row-price deal-price-good">${fmtPrice(ch.price_eur)}</div>
                        <div class="deal-row-source">${ch.provider_label} · ${ch.country_label}</div>
                        <div class="deal-row-specs">${specs(ch)}</div>
                        ${ch.url ? `<a href="${ch.url}" target="_blank" class="deal-link deal-link-good">View listing &rarr;</a>` : ""}
                    </div>
                </div>`;
            }).join("");
        }
        if (p.kind === "listings" && Array.isArray(p.listings)) {
            if (!p.listings.length) return '<p style="color:var(--ink-muted)">No listings found.</p>';
            const fmtPrice = n => n ? "EUR " + Number(n).toLocaleString() : "N/A";
            const fmtKm = n => n ? Number(n).toLocaleString() + " km" : "";
            return p.listings.map(l => {
                const specs = [l.variant, l.year, fmtKm(l.mileage_km), l.fuel_type, l.transmission].filter(Boolean).join(" · ");
                const extra = [l.power_hp ? l.power_hp + "hp" : "", l.body_type, l.steering_side === "RHD" ? "RHD" : ""].filter(Boolean).join(" · ");
                const scoreBadge = l.investment_score ? `<span class="listing-score tier-${l.tier||3}">${l.investment_score}</span>` : "";
                const favBtn = l.id ? `<button class="fav-btn" onclick="toggleFavorite(${l.id},this)" title="Save to favorites">&#9825;</button>` : "";
                const img = l.image_url ? `<img src="${l.image_url}" alt="${l.make} ${l.model}" class="listing-thumb" loading="lazy" onerror="this.style.display='none'">` : "";
                return `
                <div class="listing-card">
                    ${img}
                    <div class="listing-header">
                        <span class="listing-title">${l.make} ${l.model}</span>
                        <span style="display:flex;align-items:center;gap:6px;">${scoreBadge}<span class="listing-price">${fmtPrice(l.price_eur)}</span>${favBtn}</span>
                    </div>
                    <div class="listing-specs">${specs}</div>
                    ${l.strength_summary ? `<div class="listing-strength">${l.strength_summary}</div>` : ""}
                    ${extra ? `<div class="listing-extra">${extra}</div>` : ""}
                    <div class="listing-source">${l.provider_label} · ${l.country_label}</div>
                    ${l.url ? `<a href="${l.url}" target="_blank" class="listing-link">View listing →</a>` : ""}
                </div>`;
            }).join("");
        }
        if (p.kind === "table" && Array.isArray(p.rows)) {
            if (!p.rows.length) return '<p><em>No rows.</em></p>';
            const cols = p.columns || Object.keys(p.rows[0]);
            const head = "<tr>" + cols.map(c => `<th>${c}</th>`).join("") + "</tr>";
            const tbody = p.rows.map(r => "<tr>" + cols.map(c => `<td>${formatCell(r[c])}</td>`).join("") + "</tr>").join("");
            return `<table class="artifact-table">${head}${tbody}</table>`;
        }
        if (p.kind === "citations" && Array.isArray(p.items)) {
            return p.items.map(it => `
                <div style="margin-bottom:.6rem;">
                    <div style="color:var(--ink);font-size:.8rem;font-weight:500;">${it.title || ""}</div>
                    <div style="color:var(--ink-dim);font-size:.68rem;font-family:monospace;">${it.url ? `<a href="${it.url}" target="_blank" style="color:var(--ink-muted)">link</a>` : ""} ${it.score ? `score ${Number(it.score).toFixed(2)}` : ""}</div>
                    <div style="color:var(--ink-muted);font-size:.75rem;margin-top:.25rem;">${(it.snippet || "").replace(/\n/g,"<br>")}</div>
                </div>
            `).join("");
        }
        if (p.body_md) {
            return renderMarkdownLite(p.body_md);
        }
        return `<pre style="font-size:11px;overflow-x:auto">${JSON.stringify(p, null, 2)}</pre>`;
    }

    function formatCell(v) {
        if (v === null || v === undefined) return "--";
        if (typeof v === "number") return v.toLocaleString();
        if (typeof v === "object") return JSON.stringify(v);
        return String(v);
    }

    // -- UI helpers --
    window.toggleLeftPane = () => {
        const lp = $(".left-pane");
        const lo = $(".left-overlay");
        if (lp) lp.classList.toggle("open");
        if (lo) lo.classList.toggle("visible");
        const rp = $("#right-pane");
        if (rp && rp.classList.contains("open")) {
            rp.classList.remove("open");
            const ro = $("#right-overlay");
            if (ro) ro.classList.remove("visible");
            const app = $(".app");
            if (app) app.classList.add("pane-closed");
        }
    };
    window.toggleArtifactPane = () => {
        const r = $("#right-pane");
        const app = $(".app");
        const ro = $("#right-overlay");
        if (!r) return;
        if (r.classList.contains("open")) {
            r.classList.remove("open");
            if (app) app.classList.add("pane-closed");
            if (ro) ro.classList.remove("visible");
            const ab = $("#artifact-btn");
            if (ab) ab.classList.remove("active");
        } else {
            r.classList.add("open");
            if (app) app.classList.remove("pane-closed");
            if (ro && window.innerWidth <= 768) ro.classList.add("visible");
            const ab = $("#artifact-btn");
            if (ab) ab.classList.add("active");
        }
    };
    window.toggleGroup = (id) => {
        const el = document.getElementById(id);
        if (el) el.classList.toggle("open");
    };
    window.handleKey = (ev) => {
        if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); sendMessage(ev); }
    };
    window.autoResize = (el) => {
        el.style.height = "auto";
        el.style.height = Math.min(el.scrollHeight, 240) + "px";
    };
    window.fillChat = (text) => {
        const ta = $("#chat-input");
        if (!ta) return;
        ta.value = text;
        ta.focus();
        autoResize(ta);
        const prefix = text.trim().replace(/:.*/, "").toLowerCase();
        const slug = AGENT_PREFIX_MAP[prefix];
        if (slug) {
            currentAgentSlug = slug;
            const label = $("#current-agent-label");
            if (label) label.textContent = AGENT_NAMES[slug] || slug;
            updateSampleCards(slug);
        }
    };
    window.newChat = () => { window.location.href = "/app"; };
    const _checkSvg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
    const _shareSvg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"/><polyline points="16 6 12 2 8 6"/><line x1="12" y1="2" x2="12" y2="15"/></svg>';
    const _copySvg = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
    const _linkSvg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';

    function _flashIcon(btn, origSvg, duration) {
        btn.innerHTML = _checkSvg;
        btn.classList.add("copied");
        setTimeout(() => { btn.innerHTML = origSvg; btn.classList.remove("copied"); }, duration || 2000);
    }
    function _copyToClipboard(text, cb) {
        try {
            navigator.clipboard.writeText(text).then(cb, () => { _fallbackCopy(text); cb(); });
        } catch(e) { _fallbackCopy(text); cb(); }
    }
    function _fallbackCopy(text) {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand("copy"); } catch(e) {}
        document.body.removeChild(ta);
    }

    window.copyChat = () => {
        const msgs = document.querySelectorAll(".msg");
        const lines = [];
        msgs.forEach(m => {
            const role = m.classList.contains("msg-user") ? "You" : "CarHero";
            const bubble = m.querySelector(".msg-bubble");
            if (bubble) lines.push(`${role}: ${bubble.textContent.trim()}`);
        });
        const btn = $("#copy-chat-btn");
        _copyToClipboard(lines.join("\n\n"), () => { if (btn) _flashIcon(btn, _copySvg); });
    };
    window.shareChat = () => {
        if (!currentSessionId) return;
        const btn = $("#share-chat-btn");
        fetch("/api/share/" + currentSessionId, { method: "POST" })
            .then(r => r.json())
            .then(data => {
                if (data.url) {
                    const full = window.location.origin + data.url;
                    _copyToClipboard(full, () => { if (btn) _flashIcon(btn, _shareSvg); });
                }
            })
            .catch(() => {});
    };
    window.shareSession = (sid, btn) => {
        fetch("/api/share/" + sid, { method: "POST" })
            .then(r => r.json())
            .then(data => {
                if (data.url) {
                    const full = window.location.origin + data.url;
                    _copyToClipboard(full, () => { if (btn) _flashIcon(btn, _linkSvg); });
                }
            })
            .catch(() => {});
    };

    document.querySelectorAll(".msg-bubble").forEach(b => enhanceTables(b));

    window.toggleLangDropdown = (ev) => {
        ev.stopPropagation();
        const menu = document.getElementById("lang-dd-menu");
        if (menu) menu.classList.toggle("open");
    };
    document.addEventListener("click", () => {
        const menu = document.getElementById("lang-dd-menu");
        if (menu) menu.classList.remove("open");
    });

    // On mobile, ensure right pane starts closed
    if (window.innerWidth <= 768) {
        const rp = $("#right-pane");
        if (rp) rp.classList.remove("open");
        const app = $(".app");
        if (app) app.classList.add("pane-closed");
    }

    window.sendMessage = sendMessage;
    window.renderMarkdownLite = renderMarkdownLite;
    window.enhanceTables = enhanceTables;

    // Auto-send deal query from email deep-link (?deal_id=<uuid> or ?deal=BMW+X5)
    function autoDealSend(query) {
        const ta = $("#chat-input");
        if (!ta) return;
        ta.value = query;
        if (typeof autoResize === "function") autoResize(ta);
        sendMessage(null);
    }
    if (!getSidFromURL()) {
        const params = new URLSearchParams(window.location.search);
        const dealId = params.get("deal_id");
        const dealName = params.get("deal");
        if (dealId) {
            fetch("/api/deal/" + encodeURIComponent(dealId))
                .then(r => r.ok ? r.json() : null)
                .then(d => {
                    if (d) autoDealSend("search: show me price arbitrage deals for " + d.make + " " + d.model);
                })
                .catch(() => {});
        } else if (dealName) {
            setTimeout(() => autoDealSend("search: show me price arbitrage deals for " + dealName), 300);
        }
    }
})();

/* -- Auth functions (global, called from onclick handlers) -- */

function switchAuthTab(tab) {
    document.getElementById('auth-form-login').style.display = tab === 'login' ? '' : 'none';
    document.getElementById('auth-form-register').style.display = tab === 'register' ? '' : 'none';
    document.getElementById('auth-form-forgot').style.display = tab === 'forgot' ? '' : 'none';
    document.querySelectorAll('.auth-tab').forEach(t => t.classList.remove('active'));
    const tabEl = document.getElementById('auth-tab-' + tab);
    if (tabEl) tabEl.classList.add('active');
}

function showForgotPassword(e) {
    e && e.preventDefault();
    switchAuthTab('forgot');
}

function showSignIn() {
    document.getElementById('signin-overlay').classList.add('visible');
    switchAuthTab('login');
}

async function doLogin() {
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const errEl = document.getElementById('login-error');
    errEl.textContent = '';
    if (!email || !password) { errEl.textContent = 'Email and password required'; return; }

    const resp = await fetch('/auth/login', {
        method: 'POST',
        body: new URLSearchParams({ email, password }),
    });
    const data = await resp.json();
    if (data.ok) {
        location.reload();
    } else if (data.error === 'no_password') {
        errEl.innerHTML = 'No password set. <a href="#" onclick="showSetPassword(\'' + email + '\');return false" style="color:#000;font-weight:600;">Set one now</a>';
    } else {
        errEl.textContent = data.error || 'Login failed';
    }
}

async function doRegister() {
    const name = document.getElementById('reg-name').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;
    const errEl = document.getElementById('reg-error');
    const okEl = document.getElementById('reg-success');
    errEl.textContent = ''; okEl.textContent = '';
    if (!email || !password) { errEl.textContent = 'Email and password required'; return; }

    const resp = await fetch('/auth/register', {
        method: 'POST',
        body: new URLSearchParams({ email, password, name }),
    });
    const data = await resp.json();
    if (data.ok) {
        okEl.textContent = data.message || 'Check your email to verify';
    } else {
        errEl.textContent = data.error || 'Registration failed';
    }
}

async function doForgot() {
    const email = document.getElementById('forgot-email').value.trim();
    const msgEl = document.getElementById('forgot-msg');
    msgEl.textContent = '';
    if (!email) { msgEl.textContent = 'Enter your email'; msgEl.style.color = '#DC2626'; return; }

    const resp = await fetch('/auth/forgot', {
        method: 'POST',
        body: new URLSearchParams({ email }),
    });
    const data = await resp.json();
    msgEl.style.color = '#16A34A';
    msgEl.textContent = data.message || 'Reset link sent if account exists';
}

function showSetPassword(email) {
    const form = document.getElementById('auth-form-login');
    form.innerHTML = '<p style="font-size:13px;color:#4B5563;margin-bottom:12px;">Set a password for <strong>' + email + '</strong></p>'
        + '<input type="password" id="set-pw-input" placeholder="New password (min 6 chars)" style="width:100%;padding:8px 12px;border:1px solid #E5E7EB;border-radius:6px;font-size:14px;margin-bottom:12px;">'
        + '<div id="set-pw-error" style="color:#DC2626;font-size:12px;margin-bottom:8px;"></div>'
        + '<button onclick="doSetPassword(\'' + email + '\')" style="padding:8px 16px;background:#000;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Set Password</button>';
}

async function doSetPassword(email) {
    const password = document.getElementById('set-pw-input').value;
    const errEl = document.getElementById('set-pw-error');
    if (!password || password.length < 6) { errEl.textContent = 'Min 6 characters'; return; }

    const resp = await fetch('/auth/set-password', {
        method: 'POST',
        body: new URLSearchParams({ email, password }),
    });
    const data = await resp.json();
    if (data.ok) location.reload();
    else errEl.textContent = data.error || 'Failed';
}

function signOut() {
    fetch('/auth/logout', { method: 'POST' }).then(() => location.reload());
}

async function toggleFavorite(listingId, btn) {
    const resp = await fetch('/api/favorites', {
        method: 'POST',
        body: new URLSearchParams({ listing_id: listingId }),
    });
    if (resp.ok) {
        btn.innerHTML = '&#9829;';
        btn.style.color = '#DC2626';
    }
}

/* Legacy compat */
function doSignIn() { doLogin(); }
