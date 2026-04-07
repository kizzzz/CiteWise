/* CiteWise V3 — 前端逻辑 */

// ============ State ============
let projects = [];
let currentProjectId = null;
let extractionFields = ['研究方法', '核心算法', '数据集', '主要结论'];
let currentDraftSection = null;
let chatBusy = false;

// ============ Init ============
document.addEventListener('DOMContentLoaded', async () => {
    lucide.createIcons();
    await loadProjects();
    renderSkillLibrary();
    renderToolLibrary();
    renderFields();

    // Enter key for chat input
    document.getElementById('chatInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter') handleSendChat();
    });
    document.getElementById('subInput').addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSendSubChat();
        }
    });

    // Close dropdowns on click outside
    window.addEventListener('click', () => {
        document.querySelectorAll('.dropdown-menu').forEach(d => d.classList.remove('show'));
    });
});

// ============ API Client ============
async function api(method, path, body = null) {
    const opts = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);
    const resp = await fetch(`/api${path}`, opts);
    if (!resp.ok) {
        const err = await resp.text();
        throw new Error(err);
    }
    return resp;
}

// ============ Projects ============
async function loadProjects() {
    try {
        projects = await (await api('GET', '/projects')).json();
        renderProjectList();
        if (projects.length > 0 && !currentProjectId) {
            await selectProject(projects[0].id);
        }
    } catch (e) {
        console.error('Load projects failed:', e);
    }
}

async function selectProject(id) {
    currentProjectId = id;
    const proj = projects.find(p => p.id === id);
    document.getElementById('currentProjectName').textContent = proj ? proj.name : '未知项目';
    closeAllDropdowns();
    renderProjectList();
    await loadProjectData();
}

async function loadProjectData() {
    if (!currentProjectId) return;
    try {
        const state = await (await api('GET', `/projects/${currentProjectId}/state`)).json();
        // Update progress bar
        const total = state.paper_count + state.section_count + state.extraction_count;
        const pct = Math.min(100, Math.round(total / 15 * 100));
        document.getElementById('progressPercent').textContent = pct + '%';
        document.getElementById('globalProgressBar').style.width = pct + '%';

        renderPapers(state.papers || []);
        renderDrafts(state.sections_with_id || []);
    } catch (e) {
        console.error('Load project data failed:', e);
    }
}

function renderProjectList() {
    const c = document.getElementById('projectListContainer');
    if (!c) return;
    c.innerHTML = projects.map(p =>
        `<div onclick="selectProject('${escapeAttr(p.id)}')" class="p-3 hover:bg-blue-50 cursor-pointer rounded-lg font-bold ${p.id === currentProjectId ? 'bg-blue-50 text-blue-700' : 'text-slate-700'}">${escapeHtml(p.name)}</div>`
    ).join('');
    lucide.createIcons();
}

async function confirmCreateProject() {
    const name = document.getElementById('newProjectTitle').value.trim();
    const topic = document.getElementById('newProjectTopic').value.trim();
    if (!name) return;
    try {
        const resp = await (await api('POST', '/projects', { name, topic })).json();
        toggleModal('newProjectModal');
        showToast('项目创建成功', 'success');
        await loadProjects();
        await selectProject(resp.id);
    } catch (e) {
        showToast('创建失败: ' + e.message, 'error');
    }
}

// ============ Papers ============
function renderPapers(papers) {
    const c = document.getElementById('paperListContainer');
    if (!c) return;
    if (!papers || papers.length === 0) {
        c.innerHTML = '<div class="col-span-3 text-center text-slate-400 py-12">暂无文献，请上传 PDF</div>';
        return;
    }
    c.innerHTML = papers.map(p =>
        `<div onclick="openPaperDetail('${p.id}', '${escapeAttr(p.title)}', '${escapeAttr(p.authors || '')}')" class="bg-white border p-6 rounded-3xl shadow-sm hover:border-indigo-400 transition-all cursor-pointer">
            <h4 class="font-bold text-slate-800">${escapeHtml(p.title || '未命名')}</h4>
            <p class="text-xs text-slate-400 mt-2">${p.year || '?'} · ${escapeHtml((p.authors || '').substring(0, 20))}</p>
        </div>`
    ).join('');
    lucide.createIcons();
}

async function handleUploadPapers() {
    const files = document.getElementById('paperUpload').files;
    if (!files.length || !currentProjectId) {
        showToast('请先选择项目', 'error');
        return;
    }

    const prog = document.getElementById('uploadProgress');
    prog.classList.remove('hidden');
    prog.classList.add('animate__animated', 'animate__fadeIn');

    const formData = new FormData();
    for (const f of files) formData.append('files', f);
    formData.append('project_id', currentProjectId);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/papers/upload');

    xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
            const pct = Math.round(e.loaded / e.total * 100);
            document.getElementById('progressBar').style.width = pct + '%';
            document.getElementById('progressText').textContent = pct + '%';
        }
    };

    xhr.onload = () => {
        prog.classList.add('hidden');
        if (xhr.status === 200) {
            try {
                const result = JSON.parse(xhr.responseText);
                showToast(result.message, 'success');
                loadProjectData();
            } catch (e) {
                showToast('上传完成，但解析响应失败', 'error');
            }
        } else {
            showToast('上传失败', 'error');
        }
    };

    xhr.onerror = () => {
        prog.classList.add('hidden');
        showToast('网络错误', 'error');
    };

    xhr.send(formData);
}

async function openPaperDetail(id, title, authors) {
    document.getElementById('paperListView').classList.add('hidden');
    document.getElementById('paperDetailView').classList.remove('hidden');
    document.getElementById('detailPaperDisplayTitle').textContent = title;
    document.getElementById('detailPaperAuthors').textContent = authors;
    document.getElementById('abstractContent').textContent = '加载中...';

    try {
        const paper = await (await api('GET', `/papers/${id}`)).json();
        document.getElementById('abstractContent').textContent = paper.abstract || '暂无摘要';
    } catch (e) {
        document.getElementById('abstractContent').textContent = '加载失败';
    }
    lucide.createIcons();
}

function closePaperDetail() {
    document.getElementById('paperListView').classList.remove('hidden');
    document.getElementById('paperDetailView').classList.add('hidden');
}

// ============ Drafts ============
function renderDrafts(sections) {
    const c = document.getElementById('draftList');
    if (!c) return;
    if (!sections || sections.length === 0) {
        c.innerHTML = '<div class="col-span-2 text-center text-slate-400 py-12">暂无章节，点击右上角新建</div>';
        return;
    }
    c.innerHTML = sections.map(s =>
        `<div onclick="openDraftEditor('${s.id}', '${escapeAttr(s.name)}')" class="bg-white border p-6 rounded-3xl shadow-sm hover:border-indigo-400 transition-all cursor-pointer">
            <h4 class="font-bold">${escapeHtml(s.name)}</h4>
        </div>`
    ).join('');
    lucide.createIcons();
}

async function confirmCreateDraft() {
    const name = document.getElementById('newDraftTitle').value.trim();
    if (!name || !currentProjectId) return;
    toggleModal('newDraftModal');
    showToast('正在生成章节...', 'success');

    try {
        const result = await (await api('POST', '/sections', {
            project_id: currentProjectId,
            name: name
        })).json();
        showToast('章节生成完成', 'success');
        await loadProjectData();
    } catch (e) {
        showToast('生成失败: ' + e.message, 'error');
    }
}

let currentDraftId = null;
let currentDraftName = '';

async function openDraftEditor(id, name) {
    currentDraftId = id;
    currentDraftName = name;
    document.getElementById('draftListView').classList.add('hidden');
    document.getElementById('draftEditor').classList.remove('hidden');
    document.getElementById('editorTitle').textContent = name;
    document.getElementById('subChatWindow').innerHTML = '<div class="sub-bubble sub-bubble-ai">协作模式已激活。输入指令来修改章节内容。</div>';

    // Load section content
    try {
        const sections = await (await api('GET', `/sections?project_id=${currentProjectId}`)).json();
        const sec = sections.find(s => s.id === id);
        document.getElementById('editableArea').innerText = sec ? sec.content : '';
    } catch (e) {
        document.getElementById('editableArea').innerText = '加载失败';
    }
    lucide.createIcons();
}

function closeDraftEditor() {
    document.getElementById('draftListView').classList.remove('hidden');
    document.getElementById('draftEditor').classList.add('hidden');
    loadProjectData();
}

async function handleSendSubChat() {
    const input = document.getElementById('subInput');
    if (!input.value.trim() || !currentProjectId) return;
    const text = input.value;
    input.value = '';

    // Add user bubble
    const win = document.getElementById('subChatWindow');
    win.innerHTML += `<div class="sub-bubble sub-bubble-user">${escapeHtml(text)}</div>`;
    win.scrollTop = win.scrollHeight;

    // Add AI loading bubble
    const aiBubbleId = 'sub-ai-' + Date.now();
    win.innerHTML += `<div id="${aiBubbleId}" class="sub-bubble sub-bubble-ai">思考中...</div>`;
    win.scrollTop = win.scrollHeight;

    try {
        const content = document.getElementById('editableArea').innerText;
        const result = await (await api('POST', '/chat/sub', {
            message: text,
            project_id: currentProjectId,
            section_name: currentDraftName,
            content: content,
        })).json();

        document.getElementById(aiBubbleId).innerHTML = escapeHtml(result.content || '处理完成');

        if (result.type === 'modify' || result.content) {
            document.getElementById('editableArea').innerText = result.content;
            // Save back
            await api('PUT', `/sections/${currentDraftId}`, { content: result.content });
        }
    } catch (e) {
        document.getElementById(aiBubbleId).textContent = '错误: ' + e.message;
    }
    win.scrollTop = win.scrollHeight;
    lucide.createIcons();
}

async function smartExpand() {
    const content = document.getElementById('editableArea').innerText;
    if (!content || !currentProjectId) return;
    document.getElementById('subInput').value = `请续写「${currentDraftName}」章节，在现有内容基础上扩展`;
    handleSendSubChat();
}

// ============ Chat ============
async function handleSendChat() {
    const input = document.getElementById('chatInput');
    if (!input.value.trim() || chatBusy || !currentProjectId) return;
    const text = input.value;
    input.value = '';
    chatBusy = true;

    appendUserMessage(text);

    const container = document.getElementById('dynamicChatContent');
    const collabId = 'collab-' + Date.now();

    const collabDiv = document.createElement('div');
    collabDiv.className = 'flex gap-4 mb-8 animate__animated animate__fadeInUp';
    collabDiv.innerHTML = `
        <div class="w-10 h-10 rounded-xl bg-indigo-600 flex items-center justify-center text-white shrink-0">
            <i data-lucide="git-branch"></i>
        </div>
        <div class="flex-1 space-y-4">
            <div class="bg-indigo-50 border border-indigo-100 p-6 rounded-3xl rounded-tl-none">
                <div class="flex items-center gap-2 mb-4">
                    <span class="text-[10px] font-bold text-indigo-600 uppercase tracking-widest">协同中枢 Orchestrator 正在思考</span>
                </div>
                <div class="space-y-3 text-xs text-indigo-900/70" id="${collabId}-steps">
                    <div class="collab-step active" id="${collabId}-s1">分析学术意图并拆解子任务...</div>
                    <div class="collab-step" id="${collabId}-s2">Research Agent 正在执行多源检索...</div>
                </div>
            </div>
            <div id="${collabId}-res" class="bg-white border border-slate-200 p-6 rounded-3xl text-sm leading-relaxed hidden shadow-sm"></div>
        </div>`;
    container.appendChild(collabDiv);
    lucide.createIcons();
    scrollChat();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text, project_id: currentProjectId }),
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let events = [];

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });

            // Parse SSE events from buffer
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
                let eventType = '';
                let data = '';
                for (const line of part.split('\n')) {
                    if (line.startsWith('event: ')) eventType = line.slice(7);
                    if (line.startsWith('data: ')) data = line.slice(6);
                }
                if (eventType && data) {
                    try { data = JSON.parse(data); } catch { /* keep as string */ }
                    events.push({ type: eventType, data });
                }
            }
        }

        // Process collected events
        let content = '';
        for (const evt of events) {
            if (evt.type === 'thinking') {
                completeStep(collabId + '-s1');
            }
            if (evt.type === 'content' && evt.data) {
                completeStep(collabId + '-s1');
                completeStep(collabId + '-s2');
                content = evt.data.content || '';
            }
            if (evt.type === 'section') {
                showToast(`章节「${evt.data.section_name || ''}」已生成`, 'success');
                loadProjectData();
            }
            if (evt.type === 'error') {
                showToast('错误: ' + (evt.data.message || '未知错误'), 'error');
            }
        }

        if (content) {
            const resBox = document.getElementById(collabId + '-res');
            resBox.classList.remove('hidden');
            await streamCategorizedText(resBox, content);
        }
    } catch (e) {
        showToast('请求失败: ' + e.message, 'error');
    }

    chatBusy = false;
}

async function streamCategorizedText(target, fullText) {
    // Parse [KB]/[WEB]/[AI] source annotations from backend
    const parts = [];
    const lines = fullText.split('\n');
    let currentType = 'ai';
    let currentText = '';

    for (const line of lines) {
        if (line.startsWith('[KB]')) {
            if (currentText.trim()) parts.push({ type: currentType, text: currentText });
            currentType = 'kb';
            currentText = line.slice(4).trimStart() + '\n';
        } else if (line.startsWith('[WEB]')) {
            if (currentText.trim()) parts.push({ type: currentType, text: currentText });
            currentType = 'web';
            currentText = line.slice(5).trimStart() + '\n';
        } else if (line.startsWith('[AI]')) {
            if (currentText.trim()) parts.push({ type: currentType, text: currentText });
            currentType = 'ai';
            currentText = line.slice(4).trimStart() + '\n';
        } else {
            currentText += line + '\n';
        }
    }
    if (currentText.trim()) parts.push({ type: currentType, text: currentText });
    if (parts.length === 0) parts.push({ type: 'ai', text: fullText });

    for (const part of parts) {
        const span = document.createElement('span');
        span.className = `txt-${part.type} animate__animated animate__fadeIn`;
        target.appendChild(span);
        const chars = part.text.trim();
        for (let i = 0; i < chars.length; i++) {
            span.textContent += chars[i];
            if (i % 3 === 0) scrollChat();
            await new Promise(r => setTimeout(r, 8));
        }
        await new Promise(r => setTimeout(r, 50));
    }
}

function appendUserMessage(text) {
    const c = document.getElementById('dynamicChatContent');
    const d = document.createElement('div');
    d.className = 'flex gap-4 flex-row-reverse mb-8 animate__animated animate__fadeInUp';
    d.innerHTML = `
        <div class="w-10 h-10 rounded-xl bg-slate-800 flex items-center justify-center text-white shrink-0 shadow-lg">
            <i data-lucide="user"></i>
        </div>
        <div class="bg-blue-600 text-white p-5 rounded-3xl rounded-tr-none text-sm max-w-[80%]">${escapeHtml(text)}</div>`;
    c.appendChild(d);
    lucide.createIcons();
    scrollChat();
}

function completeStep(id) {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.classList.contains('completed')) return;
    el.classList.add('completed');
    el.classList.remove('active');
    if (el.nextElementSibling) el.nextElementSibling.classList.add('active');
    lucide.createIcons();
}

// ============ Extraction ============
function renderFields() {
    const c = document.getElementById('fieldContainer');
    if (!c) return;
    c.innerHTML = extractionFields.map((f, i) =>
        `<div class="field-pill active">${escapeHtml(f)} <button onclick="removeField(${i})" class="ml-1 hover:text-red-500">&times;</button></div>`
    ).join('');
}

function addField() {
    const v = document.getElementById('newFieldInput').value.trim();
    if (v) {
        extractionFields.push(v);
        document.getElementById('newFieldInput').value = '';
        renderFields();
    }
}

function removeField(i) {
    extractionFields.splice(i, 1);
    renderFields();
}

async function runExtraction() {
    if (!currentProjectId || extractionFields.length === 0) {
        showToast('请先选择项目并设置字段', 'error');
        return;
    }

    document.getElementById('extractionConfigView').classList.add('hidden');
    document.getElementById('extractionResultView').classList.remove('hidden');
    document.getElementById('extractionLoader').classList.remove('hidden');
    document.getElementById('extractionResultContent').classList.add('hidden');

    try {
        const results = await (await api('POST', '/extraction', {
            project_id: currentProjectId,
            fields: extractionFields,
        })).json();

        document.getElementById('extractionLoader').classList.add('hidden');
        document.getElementById('extractionResultContent').classList.remove('hidden');

        // Build table
        const head = document.getElementById('extractionTableHead');
        const body = document.getElementById('extractionTableBody');

        head.innerHTML = `<tr class="border-b bg-slate-50/50"><th class="p-6 font-bold">文献标题</th>${extractionFields.map(f => `<th class="p-6 font-bold">${escapeHtml(f)}</th>`).join('')}</tr>`;
        body.innerHTML = results.map(r =>
            `<tr class="border-b"><td class="p-6 font-bold">${escapeHtml(r.paper_title || '')}</td>${extractionFields.map(f => `<td class="p-6 text-slate-500 italic">${escapeHtml(r[f] || '—')}</td>`).join('')}</tr>`
        ).join('');

    } catch (e) {
        document.getElementById('extractionLoader').classList.add('hidden');
        showToast('提取失败: ' + e.message, 'error');
    }
    lucide.createIcons();
}

function exportExtraction() {
    // Simple CSV export
    const table = document.querySelector('.academic-table');
    if (!table) return;
    let csv = '';
    for (const row of table.querySelectorAll('tr')) {
        const cells = [];
        for (const cell of row.querySelectorAll('th, td')) {
            cells.push('"' + cell.textContent.trim().replace(/"/g, '""') + '"');
        }
        csv += cells.join(',') + '\n';
    }
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'extraction_results.csv';
    a.click();
    URL.revokeObjectURL(url);
}

// ============ AgentEval Dashboard ============
async function loadEvalDashboard() {
    const days = parseInt(document.getElementById('evalDaysSelect').value) || 7;
    try {
        const [metrics, trends] = await Promise.all([
            (await api('GET', `/eval/metrics?days=${days}&project_id=${currentProjectId || ''}`)).json(),
            (await api('GET', `/eval/trends?days=${days}&project_id=${currentProjectId || ''}`)).json(),
        ]);

        // Fill metric cards
        document.getElementById('metricSuccessRate').textContent = metrics.success_rate + '%';
        document.getElementById('metricSuccessCount').textContent = metrics.success_count;
        document.getElementById('metricTotal').textContent = metrics.total_tasks;
        document.getElementById('metricAccuracy').textContent = metrics.avg_accuracy || 0;
        document.getElementById('metricHallucRate').textContent = metrics.hallucination_rate + '%';
        document.getElementById('metricHallucCount').textContent = metrics.hallucination_count;
        document.getElementById('metricResponseTime').textContent = Math.round(metrics.avg_response_time_ms);
        document.getElementById('metricCost').textContent = metrics.avg_cost;
        document.getElementById('metricTotalCost').textContent = metrics.total_cost;

        // Color code based on thresholds
        colorMetricCard('metricSuccessRate', metrics.success_rate, 85, true);
        colorMetricCard('metricHallucRate', metrics.hallucination_rate, 10, false);

        // Render trend chart (CSS bars)
        renderTrendChart(trends);

        // Render suggestions
        const sugBox = document.getElementById('evalSuggestions');
        if (metrics.suggestions && metrics.suggestions.length > 0) {
            sugBox.innerHTML = metrics.suggestions.map(s =>
                `<div class="p-3 rounded-xl text-xs font-semibold leading-relaxed ${s.includes('✅') ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' : 'bg-amber-50 text-amber-700 border border-amber-100'}">${escapeHtml(s)}</div>`
            ).join('');
        } else {
            sugBox.innerHTML = '<div class="text-slate-400 text-center py-8">暂无建议</div>';
        }

    } catch (e) {
        console.error('Eval load failed:', e);
        showToast('评估数据加载失败: ' + e.message, 'error');
    }
    lucide.createIcons();
}

function colorMetricCard(elId, value, threshold, higherIsBetter) {
    const el = document.getElementById(elId);
    if (!el) return;
    if (value === 0 && elId.includes('Halluc')) return; // 0 hallucination is good
    const good = higherIsBetter ? value >= threshold : value <= threshold;
    el.classList.remove('text-red-600', 'text-emerald-600');
    el.classList.add(good ? 'text-emerald-600' : 'text-red-600');
}

function renderTrendChart(trends) {
    const box = document.getElementById('evalTrendChart');
    if (!trends || trends.length === 0) {
        box.innerHTML = '<div class="flex-1 flex items-center justify-center text-slate-400 text-sm">暂无趋势数据，发送消息后自动采集</div>';
        document.getElementById('trendDateStart').textContent = '-';
        document.getElementById('trendDateEnd').textContent = '-';
        return;
    }
    const maxTotal = Math.max(...trends.map(t => t.total), 1);
    box.innerHTML = trends.map(t => {
        const h = Math.max(4, (t.total / maxTotal) * 100);
        const successPct = t.total > 0 ? Math.round((t.successes / t.total) * 100) : 0;
        return `<div class="flex-1 flex flex-col items-center gap-1 group relative">
            <div class="w-full rounded-t-md bg-blue-500 transition-all hover:bg-blue-600 cursor-default" style="height:${h}%" title="${escapeAttr(t.date)}: ${escapeAttr(String(t.total))}次 / ${successPct}%成功"></div>
            <span class="text-[9px] text-slate-400 font-medium">${t.date.slice(5)}</span>
        </div>`;
    }).join('');
    document.getElementById('trendDateStart').textContent = trends[0].date;
    document.getElementById('trendDateEnd').textContent = trends[trends.length - 1].date;
}

// ============ Skill & Tool Library ============
function renderSkillLibrary() {
    const c = document.getElementById('skillListContainer');
    if (!c) return;
    const skills = [
        { name: 'Abstract Polisher', desc: '摘要润色与学术化', icon: 'zap', color: 'amber' },
        { name: 'Citation Checker', desc: '引用格式与准确性验证', icon: 'check-circle', color: 'green' },
        { name: 'Method Comparator', desc: '方法论对比分析', icon: 'git-compare', color: 'blue' },
        { name: 'Term Normalizer', desc: '术语一致性检查', icon: 'type', color: 'purple' },
    ];
    c.innerHTML = skills.map(s =>
        `<div class="bg-white border p-6 rounded-3xl shadow-sm hover:border-indigo-400 transition-all cursor-pointer">
            <div class="p-2 bg-${s.color}-50 text-${s.color}-600 rounded-lg w-fit mb-4"><i data-lucide="${s.icon}"></i></div>
            <h4 class="font-bold">${s.name}</h4>
            <p class="text-xs text-slate-400 mt-1">${s.desc}</p>
        </div>`
    ).join('');
    lucide.createIcons();
}

function renderToolLibrary() {
    const c = document.getElementById('toolListContainer');
    if (!c) return;
    const tools = [
        { name: 'Data Plotter', desc: '数据可视化图表生成', icon: 'bar-chart-2', color: 'blue' },
        { name: 'PDF Parser', desc: '高级 PDF 解析与表格提取', icon: 'file-text', color: 'red' },
        { name: 'Web Search', desc: '联网学术搜索', icon: 'globe', color: 'green' },
        { name: 'Export Engine', desc: 'Word/Markdown/Excel 导出', icon: 'download', color: 'indigo' },
    ];
    c.innerHTML = tools.map(t =>
        `<div class="bg-white border p-6 rounded-3xl shadow-sm hover:border-indigo-400 transition-all cursor-pointer">
            <div class="p-2 bg-${t.color}-50 text-${t.color}-600 rounded-lg w-fit mb-4"><i data-lucide="${t.icon}"></i></div>
            <h4 class="font-bold">${t.name}</h4>
            <p class="text-xs text-slate-400 mt-1">${t.desc}</p>
        </div>`
    ).join('');
    lucide.createIcons();
}

// ============ UI Helpers ============
function switchView(id, btn) {
    document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(i => {
        i.classList.remove('active', 'bg-blue-50', 'text-blue-700');
    });
    document.getElementById(id).classList.add('active');
    if (btn) btn.classList.add('active');
    closeAllDropdowns();
}

function toggleModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle('hidden');
    if (id === 'summaryModal') renderFields();
}

function toggleDropdown(id, e) {
    if (e) e.stopPropagation();
    const el = document.getElementById(id);
    if (el) el.classList.toggle('show');
}

function closeAllDropdowns() {
    document.querySelectorAll('.dropdown-menu').forEach(d => d.classList.remove('show'));
}

function scrollChat() {
    const win = document.getElementById('chatWindow');
    if (win) win.scrollTo({ top: win.scrollHeight, behavior: 'smooth' });
}

function showToast(msg, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escapeAttr(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/'/g, '&#39;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/`/g, '&#96;');
}
