/* CiteWise V3 — 前端逻辑 (合并原型交互 + 后端 API) */

// ============ API Base URL (环境感知) ============
const API_BASE = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? ''  // 开发环境：同源
    : 'https://citewise-w9op.onrender.com';  // 生产环境：后端地址

// ============ State ============
let projects = [];
let currentProjectId = null;
let extractionFields = ['研究方法', '核心算法', '数据集', '主要结论'];
let currentDraftSection = null;
let chatBusy = false;
let currentDraftId = null;
let currentDraftName = '';
let currentUser = null; // { id, username, token }
let authMode = 'login'; // 'login' or 'register'

let agents = [
    { id: 'research', name: 'Research', icon: 'search', status: 'READY', color: 'blue' },
    { id: 'writing', name: 'Writing', icon: 'pen-tool', status: 'READY', color: 'purple' },
    { id: 'analyst', name: 'Analyst', icon: 'hammer', status: 'READY', color: 'slate' }
];

let skills = [
    { id: 1, title: "Abstract Polisher", desc: "摘要润色能力。", icon: "pen-tool", tag: "已安装", agent: "writing" },
    { id: 2, title: "Citation Checker", desc: "引用格式与准确性验证。", icon: "check-circle", tag: "已安装", agent: "research" },
    { id: 3, title: "Method Comparator", desc: "方法论对比分析。", icon: "git-compare", tag: "已安装", agent: "analyst" },
    { id: 4, title: "Term Normalizer", desc: "术语一致性检查。", icon: "type", tag: "已安装", agent: "writing" }
];

let tools = [
    { id: 1, title: "Statistical Plotter", desc: "自动根据文献数据绘制图表。", icon: "bar-chart-3", type: "脚本", trigger: "绘图, 画图, plot" },
    { id: 2, title: "Citation Formatter", desc: "处理引用格式。", icon: "book-open", type: "脚本", trigger: "格式, 引用, cite" }
];

let apiKeys = [
    { id: '1', name: 'Gemini 2.0 Flash', value: 'sk-xxxxxxxx', active: true }
];

// ============ Init ============
document.addEventListener('DOMContentLoaded', async () => {
    lucide.createIcons();
    renderAgentStatus();
    renderApiKeyList();
    await loadProjects();
    renderSkillLibrary();
    renderToolLibrary();
    renderFields();

    // Restore user session from localStorage
    const savedUser = localStorage.getItem('citewise_user');
    if (savedUser) {
        try {
            currentUser = JSON.parse(savedUser);
            updateAuthUI();
        } catch { currentUser = null; }
    }

    // Restore API keys (new multi-provider format)
    const savedKeys = localStorage.getItem('citewise_api_keys');
    if (savedKeys) {
        try { apiKeys = JSON.parse(savedKeys); } catch { apiKeys = []; }
    }
    // Migrate old single-key format
    if (apiKeys.length === 0) {
        const oldKey = localStorage.getItem('citewise_api_key');
        if (oldKey) {
            apiKeys = [{ provider: 'zhipu', apiKey: oldKey, baseUrl: 'https://open.bigmodel.cn/api/paas/v4/', active: true }];
            saveApiKeysToStorage(apiKeys);
        }
    }
    renderApiKeyList();

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
    if (currentUser && currentUser.token) {
        opts.headers['Authorization'] = `Bearer ${currentUser.token}`;
    }
    const resp = await fetch(`${API_BASE}/api${path}`, opts);
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
        `<div class="group flex items-center justify-between p-3 hover:bg-blue-50 cursor-pointer rounded-lg font-bold ${p.id === currentProjectId ? 'bg-blue-50 text-blue-700' : 'text-slate-700'}">
            <span onclick="selectProject('${escapeAttr(p.id)}')" class="flex-1 truncate">${escapeHtml(p.name)}</span>
            <button onclick="event.stopPropagation();confirmDeleteProject('${escapeAttr(p.id)}','${escapeJs(p.name)}')" class="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-opacity ml-2" title="删除项目">
                <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
        </div>`
    ).join('');
    lucide.createIcons();
}

async function confirmDeleteProject(id, name) {
    if (!confirm(`确定删除项目「${name}」？该操作不可恢复。`)) return;
    try {
        await api('DELETE', `/projects/${id}`);
        showToast('项目已删除', 'success');
        if (currentProjectId === id) currentProjectId = null;
        await loadProjects();
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}

async function confirmCreateProject() {
    const name = document.getElementById('newProjectTitle').value.trim();
    const topic = document.getElementById('newProjectTopic') ? document.getElementById('newProjectTopic').value.trim() : '';
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
        `<div onclick="openPaperDetail('${p.id}', '${escapeJs(p.title)}', '${escapeJs(p.authors || '')}')" class="interactive-card bg-white p-6 rounded-3xl border border-slate-100 shadow-sm animate__animated animate__fadeIn cursor-pointer">
            <div class="w-10 h-10 bg-blue-50 text-blue-600 rounded-xl flex items-center justify-center mb-4">
                <i data-lucide="file-text" class="w-5 h-5"></i>
            </div>
            <h4 class="font-bold text-slate-800 text-sm mb-1">${escapeHtml(p.title || '未命名')}</h4>
            <p class="text-[10px] text-slate-400 font-bold uppercase tracking-wider">${p.year || '?'} · ${escapeHtml((p.authors || '').substring(0, 20))}</p>
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
    xhr.open('POST', `${API_BASE}/api/papers/upload`);

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

function handlePaperSelect(e) {
    if (e.target.files[0]) showToast('文献已选择', 'success');
}

function handleDragOver(e) {
    e.preventDefault();
}

function handleDragLeave(e) {
    e.preventDefault();
}

function handleDrop(e) {
    e.preventDefault();
    if (e.dataTransfer.files[0]) showToast('解析成功', 'success');
}

async function openPaperDetail(id, title, authors) {
    safeClassAction('paperListView', 'add', 'hidden');
    safeClassAction('paperDetailView', 'remove', 'hidden');
    document.getElementById('detailPaperDisplayTitle').textContent = title;

    const abstractEl = document.getElementById('abstractContent');
    const detailEl = document.getElementById('paperDetailContent');
    const metaEl = document.getElementById('detailPaperMeta');

    if (abstractEl) abstractEl.textContent = '';
    if (detailEl) detailEl.innerHTML = '<p class="text-slate-400">加载中...</p>';
    if (metaEl) metaEl.innerHTML = '';

    try {
        const paper = await (await api('GET', `/papers/${id}`)).json();

        // Render meta info badges
        if (metaEl) {
            const badges = [];
            if (paper.year) badges.push(`<span class="inline-block px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 font-semibold">${escapeHtml(String(paper.year))}</span>`);
            if (paper.filename) badges.push(`<span class="inline-block px-2.5 py-1 rounded-full bg-slate-100 text-slate-600">${escapeHtml(paper.filename)}</span>`);
            if (paper.chunk_count) badges.push(`<span class="inline-block px-2.5 py-1 rounded-full bg-purple-50 text-purple-700">${paper.chunk_count} chunks</span>`);
            if (paper.indexed_at) badges.push(`<span class="inline-block px-2.5 py-1 rounded-full bg-green-50 text-green-700">${escapeHtml(paper.indexed_at)}</span>`);
            metaEl.innerHTML = badges.join('');
        }

        // Render sections (full article content organized by section)
        if (detailEl) {
            const sections = paper.sections || [];
            if (sections.length > 0) {
                detailEl.innerHTML = sections.map(s => {
                    const sectionClass = s.level === 'L0' ? 'bg-blue-50 border-blue-100' : 'bg-white border-slate-200';
                    const headingSize = s.level === 'L0' ? 'text-lg' : 'text-base';
                    const paragraphs = s.text.split(/\n{2,}/).filter(p => p.trim());
                    return `
                        <div class="border rounded-2xl p-6 ${sectionClass} space-y-3">
                            <h3 class="font-bold text-slate-800 ${headingSize}">${escapeHtml(s.title)}</h3>
                            ${paragraphs.map(p => `<p class="text-slate-600 leading-loose text-sm">${escapeHtml(p.trim())}</p>`).join('')}
                        </div>`;
                }).join('');
            } else {
                // Fallback: use abstract/full_text
                const content = paper.full_text || paper.abstract || '暂无内容';
                const paragraphs = content.split(/\n{2,}/).filter(p => p.trim());
                detailEl.innerHTML = paragraphs.map(p =>
                    `<p class="text-slate-600 leading-loose">${escapeHtml(p.trim())}</p>`
                ).join('');
            }
        }

        const authorsEl = document.getElementById('detailPaperAuthors');
        if (authorsEl) authorsEl.textContent = authors || '';
    } catch (e) {
        if (abstractEl) abstractEl.textContent = '加载失败';
        if (detailEl) detailEl.innerHTML = '<p class="text-slate-400">加载失败</p>';
    }
    lucide.createIcons();
}

function closePaperDetail() {
    safeClassAction('paperListView', 'remove', 'hidden');
    safeClassAction('paperDetailView', 'add', 'hidden');
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
        `<div onclick="openDraftEditor('${s.id}', '${escapeJs(s.name)}')" class="interactive-card bg-white p-6 rounded-3xl border border-slate-100 shadow-sm animate__animated animate__fadeIn cursor-pointer">
            <h4 class="font-bold text-slate-800 text-sm mb-2">${escapeHtml(s.name)}</h4>
            <p class="text-[10px] text-slate-400">最后编辑于：刚刚</p>
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

async function openDraftEditor(id, name) {
    currentDraftId = id;
    currentDraftName = name;
    safeClassAction('draftListView', 'add', 'hidden');
    safeClassAction('draftEditor', 'remove', 'hidden');
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
    safeClassAction('draftListView', 'remove', 'hidden');
    safeClassAction('draftEditor', 'add', 'hidden');
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
        const subBody = {
            message: text,
            project_id: currentProjectId,
            section_name: currentDraftName,
            content: content,
        };
        const activeKey2 = getActiveApiKey();
        if (activeKey2) {
            subBody.api_key = activeKey2.apiKey;
            subBody.base_url = activeKey2.baseUrl;
        }
        const result = await (await api('POST', '/chat/sub', subBody)).json();

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
                    <span class="text-[10px] font-bold text-indigo-600 uppercase tracking-widest">Multi-Agent 协作中</span>
                </div>
                <div class="space-y-1 text-xs text-indigo-900/70" id="${collabId}-timeline"></div>
            </div>
            <div id="${collabId}-res" class="bg-white border border-slate-200 p-6 rounded-3xl text-sm leading-relaxed hidden shadow-sm"></div>
        </div>`;
    container.appendChild(collabDiv);
    lucide.createIcons();
    scrollChat();

    // Check for tool trigger words and show tool-invocation-card
    const matchedTool = tools.find(t => t.trigger.split(', ').some(kw => text.includes(kw)));

    try {
        // Attach user API key if available
        const activeKey = getActiveApiKey();
        const chatBody = { message: text, project_id: currentProjectId };
        if (activeKey) {
            chatBody.api_key = activeKey.apiKey;
            chatBody.base_url = activeKey.baseUrl;
        }
        const response = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(chatBody),
        });

        // If a tool was matched, show the invocation card
        if (matchedTool) {
            const toolCard = document.createElement('div');
            toolCard.className = 'tool-invocation-card text-xs animate__animated animate__fadeIn';
            toolCard.innerHTML = `<div class="p-2 bg-indigo-600 text-white rounded-lg"><i data-lucide="terminal" class="w-4 h-4"></i></div><div class="flex-1"><p class="font-bold">Orchestrator: 调用固定工具</p><p class="text-slate-500">Analyst Agent 执行脚本: <b>${escapeHtml(matchedTool.title)}</b></p></div>`;
            container.appendChild(toolCard);
            lucide.createIcons();
            scrollChat();
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let events = [];
        let streamingContent = '';
        let resBox = null;

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

                    // Real-time agent timeline in collab bubble
                    if (eventType === 'agent_start' && data.agent) {
                        appendTimelineStep(collabId + '-timeline', data.agent, 'running', data.detail);
                        updateAgentStatus(data.agent, 'RUNNING');
                    }
                    if (eventType === 'agent_end' && data.agent) {
                        updateTimelineStep(collabId + '-timeline', data.agent, 'done', data.detail, data.duration_ms);
                        updateAgentStatus(data.agent, 'READY');
                    }

                    // Token-level streaming: append tokens in real-time
                    if (eventType === 'token' && data.text) {
                        if (!resBox) {
                            resBox = document.getElementById(collabId + '-res');
                            if (resBox) {
                                resBox.classList.remove('hidden');
                                resBox.innerHTML = '';
                            }
                        }
                        if (resBox) {
                            streamingContent += data.text;
                            // Use innerHTML for source-colored display
                            resBox.textContent = streamingContent;
                            scrollChat();
                        }
                    }
                }
            }
        }

        // Process remaining events for final content
        let content = '';
        for (const evt of events) {
            if (evt.type === 'content' && evt.data) {
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

        // Final render with source annotations
        if (content && resBox) {
            await streamCategorizedText(resBox, content);
        } else if (!content && streamingContent && resBox) {
            // Fallback: if no final content event, use streamed tokens
            resBox.textContent = streamingContent;
        }
    } catch (e) {
        showToast('请求失败: ' + e.message, 'error');
    }

    chatBusy = false;
}

// ---- Agent status in left sidebar ----
function updateAgentStatus(agentName, status) {
    const mapping = {
        'Supervisor': null,
        'Researcher': 'research',
        'research': 'research',
        'Responder': null,
        'Writer': 'writing',
        'writing': 'writing',
        'Analyst': 'analyst',
        'analyst': 'analyst'
    };
    const agentId = mapping[agentName];
    if (!agentId) return;
    const agent = agents.find(a => a.id === agentId);
    if (agent) {
        agent.status = status;
        renderAgentStatus();
    }
}

// ---- Agent Timeline helpers (inline collab bubble) ----
function appendTimelineStep(containerId, agent, status, detail) {
    const c = document.getElementById(containerId);
    if (!c) return;
    const stepId = containerId + '-' + agent;
    if (document.getElementById(stepId)) return; // already exists
    const colors = {
        Supervisor: 'border-indigo-500', Researcher: 'border-blue-500',
        Responder: 'border-violet-500', Writer: 'border-amber-500', Analyst: 'border-emerald-500',
    };
    const cls = status === 'running' ? 'collab-step active' : 'collab-step';
    const div = document.createElement('div');
    div.id = stepId;
    div.className = `${cls}`;
    div.style.borderLeftColor = (colors[agent] || 'border-slate-400').replace('border-', '');
    div.textContent = `${agent}: ${detail || '处理中...'}`;
    c.appendChild(div);
}

function updateTimelineStep(containerId, agent, status, detail, durationMs) {
    const stepId = containerId + '-' + agent;
    const el = document.getElementById(stepId);
    if (!el) {
        appendTimelineStep(containerId, agent, status, detail);
        return;
    }
    el.className = 'collab-step completed';
    el.textContent = `${agent}: ${detail || '完成'}${durationMs ? ` (${durationMs}ms)` : ''}`;
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
        <div class="bg-blue-600 text-white p-5 rounded-3xl rounded-tr-none text-sm max-w-[80%] shadow-md">${escapeHtml(text)}</div>`;
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
        `<div class="dimension-card relative group bg-white border border-slate-200 rounded-2xl p-4 shadow-sm text-center animate__animated animate__fadeIn">
            <div class="text-[9px] font-extrabold text-slate-300 uppercase tracking-tighter mb-1">Dimension</div>
            <div class="text-sm font-bold text-slate-700">${escapeHtml(f)}</div>
            <button onclick="extractionFields.splice(${i},1);renderFields();event.stopPropagation();" class="absolute -top-2 -right-2 w-6 h-6 bg-white border border-slate-100 rounded-full flex items-center justify-center text-slate-400 hover:text-red-500 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity">
                <i data-lucide="x" class="w-3 h-3"></i>
            </button>
        </div>`
    ).join('');
    lucide.createIcons();
}

function addField() {
    const v = document.getElementById('newFieldInput').value.trim();
    if (v && !extractionFields.includes(v)) {
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

function runCustomExtraction() {
    safeClassAction('extractionConfigView', 'add', 'hidden');
    safeClassAction('extractionResultView', 'remove', 'hidden');
    const head = document.getElementById('extractionTableHead');
    const body = document.getElementById('extractionTableBody');
    if (head && body) {
        head.innerHTML = `<tr class="border-b bg-slate-50/50 text-[10px] font-bold uppercase tracking-wider"><th class="p-6">文献</th>${extractionFields.map(f => `<th class="p-6">${escapeHtml(f)}</th>`).join('')}</tr>`;
        body.innerHTML = '<tr class="border-b text-xs text-slate-600"><td class="p-6" colspan="' + (extractionFields.length + 1) + '">正在提取中...</td></tr>';
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

// ============ Agent Status (Left Sidebar) ============
function renderAgentStatus() {
    const c = document.getElementById('agentStatusList');
    if (!c) return;
    c.innerHTML = agents.map(a => {
        const statusColor = a.status === 'RUNNING' ? 'text-amber-500' : 'text-green-500';
        return `<div class="agent-item flex items-center justify-between p-2 px-3 bg-slate-50/50 rounded-lg border border-slate-100 mb-2 text-[11px]">
            <span class="flex items-center gap-2">
                <i data-lucide="${a.icon}" class="w-3 h-3 text-${a.color}-500"></i>
                ${escapeHtml(a.name)}
            </span>
            <span class="font-bold ${statusColor} uppercase text-[9px]">${a.status}</span>
        </div>`;
    }).join('');
    lucide.createIcons();
}

function confirmCreateAgent() {
    const name = document.getElementById('agentNameIn').value.trim();
    if (!name) return;
    const icon = document.getElementById('agentIconIn').value.trim() || 'cpu';
    agents.push({
        id: Date.now().toString(),
        name: name,
        icon: icon,
        status: 'READY',
        color: 'indigo'
    });
    renderAgentStatus();
    toggleModal('createAgentModal');
    showToast('Agent 节点就绪', 'success');
}

// ============ Skill & Tool Library ============
function renderSkillLibrary() {
    const c = document.getElementById('skillListContainer');
    if (!c) return;
    c.innerHTML = skills.map(s =>
        `<div onclick="openSkillDetail(${s.id})" class="interactive-card bg-white p-6 rounded-3xl border border-slate-100 shadow-sm group animate__animated animate__fadeIn cursor-pointer">
            <div class="flex justify-between items-start mb-4">
                <div class="p-2 bg-amber-50 text-amber-600 rounded-lg">
                    <i data-lucide="${s.icon}" class="w-5 h-5"></i>
                </div>
                <span class="text-[7px] uppercase font-bold text-blue-500 mt-2">On ${escapeHtml(s.agent)} Agent</span>
            </div>
            <h4 class="font-bold text-slate-800 text-sm mb-1">${escapeHtml(s.title)}</h4>
            <p class="text-[10px] text-slate-500">${escapeHtml(s.desc)}</p>
        </div>`
    ).join('');
    lucide.createIcons();
}

function renderToolLibrary() {
    const c = document.getElementById('toolListContainer');
    if (!c) return;
    c.innerHTML = tools.map(t =>
        `<div onclick="openToolDetail(${t.id})" class="interactive-card bg-white p-6 rounded-3xl border border-slate-100 shadow-sm group animate__animated animate__fadeIn cursor-pointer">
            <div class="flex justify-between mb-4">
                <div class="p-2 bg-blue-50 text-blue-600 rounded-lg">
                    <i data-lucide="${t.icon}" class="w-5 h-5"></i>
                </div>
                <span class="px-2 py-1 bg-slate-50 text-slate-400 text-[8px] font-bold rounded">Fixed</span>
            </div>
            <h4 class="font-bold text-slate-800 text-sm mb-1">${escapeHtml(t.title)}</h4>
            <p class="text-[10px] text-slate-500">${escapeHtml(t.desc)}</p>
            <div class="mt-4 pt-3 border-t border-slate-50 text-[8px] text-slate-400 font-bold uppercase">指令词: ${escapeHtml(t.trigger)}</div>
        </div>`
    ).join('');
    lucide.createIcons();
}

function openSkillDetail(id) {
    const s = skills.find(x => x.id === id);
    if (!s) return;
    safeClassAction('skillListView', 'add', 'hidden');
    safeClassAction('skillDetailView', 'remove', 'hidden');
    const intro = document.getElementById('skillIntro');
    if (intro) intro.innerHTML = `
        <div class="p-8 bg-amber-50 rounded-3xl text-center">
            <i data-lucide="${s.icon}" class="w-10 h-10 mx-auto mb-4 text-amber-500"></i>
            <h2 class="text-2xl font-bold">${escapeHtml(s.title)}</h2>
            <p class="text-xs text-slate-400 mt-2 uppercase font-bold">Inject to ${escapeHtml(s.agent)}</p>
        </div>
        <div class="bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
            <h3 class="font-bold text-slate-700">描述</h3>
            <p class="text-slate-500 text-sm">${escapeHtml(s.desc)}</p>
        </div>
        <div class="flex gap-4">
            <button onclick="showToast('处理完成')" class="flex-1 py-4 bg-amber-500 text-white rounded-2xl font-bold shadow-lg">启动</button>
            <button onclick="deleteSkill(${s.id})" class="py-4 px-6 bg-white border border-red-200 text-red-500 rounded-2xl font-bold hover:bg-red-50 transition-all">删除</button>
        </div>
    `;
    lucide.createIcons();
}

function deleteSkill(id) {
    skills = skills.filter(s => s.id !== id);
    renderSkillLibrary();
    closeAssetDetail('skill');
    showToast('Skill 已删除');
}

function openToolDetail(id) {
    const t = tools.find(x => x.id === id);
    if (!t) return;
    safeClassAction('toolListView', 'add', 'hidden');
    safeClassAction('toolDetailView', 'remove', 'hidden');

    const code = t.code || `# CiteWise Tool: ${t.title}\n# Trigger: ${t.trigger}\n\n# ${t.desc}\n\ndef run(context):\n    """Execute this tool with the given context."""\n    # TODO: Implement tool logic\n    pass`;

    const action = document.getElementById('toolActionContent');
    if (action) action.innerHTML = `
        <div class="space-y-6 max-w-4xl mx-auto">
            <div class="p-6 bg-blue-50 rounded-3xl flex items-center gap-4">
                <div class="p-3 bg-blue-100 rounded-xl"><i data-lucide="${t.icon}" class="w-6 h-6 text-blue-600"></i></div>
                <div class="flex-1">
                    <h2 class="text-xl font-bold text-slate-800">${escapeHtml(t.title)}</h2>
                    <p class="text-xs text-slate-500">${escapeHtml(t.desc)}</p>
                </div>
            </div>
            <div class="bg-white border border-slate-200 rounded-2xl p-4">
                <div class="flex justify-between items-center mb-3">
                    <span class="text-xs font-bold text-slate-500 uppercase">脚本代码</span>
                    <span class="text-[10px] font-bold text-slate-400">指令词: ${escapeHtml(t.trigger)}</span>
                </div>
                <textarea id="toolCodeEditor" class="w-full h-64 bg-slate-900 text-green-400 p-4 rounded-xl font-mono text-xs resize-y outline-none" spellcheck="false">${escapeHtml(code)}</textarea>
            </div>
            <div class="flex gap-4">
                <button onclick="saveToolCode(${t.id})" class="flex-1 py-4 bg-blue-600 text-white rounded-2xl font-bold shadow-lg">保存修改</button>
                <button onclick="runToolScript(${t.id})" class="py-4 px-6 bg-emerald-600 text-white rounded-2xl font-bold shadow-lg">运行脚本</button>
                <button onclick="deleteTool(${t.id})" class="py-4 px-6 bg-white border border-red-200 text-red-500 rounded-2xl font-bold hover:bg-red-50">删除</button>
            </div>
        </div>
    `;
    lucide.createIcons();
}

function deleteTool(id) {
    tools = tools.filter(t => t.id !== id);
    renderToolLibrary();
    closeAssetDetail('tool');
    showToast('工具已删除');
}

function saveToolCode(id) {
    const t = tools.find(x => x.id === id);
    const editor = document.getElementById('toolCodeEditor');
    if (t && editor) {
        t.code = editor.value;
        showToast('脚本已保存');
    }
}

function runToolScript(id) {
    const t = tools.find(x => x.id === id);
    if (t) showToast(`运行 ${t.title}...`);
}

function handleToolFileSelect(e) {
    const file = e.target.files[0];
    if (!file || !file.name.endsWith('.py')) {
        showToast('请选择 .py 文件', 'error');
        return;
    }
    const up = document.getElementById('toolImportProgress');
    if (!up) return;
    up.classList.remove('hidden');

    const reader = new FileReader();
    reader.onload = function(ev) {
        const fileContent = ev.target.result;
        let v = 0;
        const timer = setInterval(() => {
            v += 10;
            const bar = document.getElementById('toolProgressBar');
            const txt = document.getElementById('toolProgressText');
            if (bar) bar.style.width = v + '%';
            if (txt) txt.innerText = v + '%';
            if (v >= 100) {
                clearInterval(timer);
                setTimeout(() => {
                    up.classList.add('hidden');
                    tools.unshift({
                        id: Date.now(),
                        title: file.name.split('.')[0],
                        desc: '导入的 Python 工具。',
                        icon: 'binary',
                        type: '本地',
                        trigger: '运行, run',
                        code: fileContent
                    });
                    renderToolLibrary();
                    showToast('工具脚本注入成功', 'success');
                }, 500);
            }
        }, 100);
    };
    reader.readAsText(file);
}

function openAddAssetModal(type) {
    const modal = document.getElementById('addAssetModal');
    if (!modal) return;
    const titleEl = document.getElementById('assetModalTitle');
    if (titleEl) titleEl.innerText = type === 'skill' ? '下载安装 Skill' : '添加工具脚本';
    const select = document.getElementById('skillAgentIn');
    if (select) select.innerHTML = agents.map(a => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join('');
    modal.classList.remove('hidden');
    lucide.createIcons();
}

function confirmCreateSkill() {
    const name = document.getElementById('skillNameIn').value.trim();
    const url = document.getElementById('skillUrlIn').value.trim();
    if (!name || !url) return;
    const box = document.getElementById('installProgress');
    const bar = document.getElementById('installBar');
    const percent = document.getElementById('installPercent');
    const btn = document.getElementById('skillConfirmBtn');
    if (!box || !bar || !percent || !btn) return;

    btn.disabled = true;
    box.classList.remove('hidden');
    let v = 0;
    const timer = setInterval(() => {
        v += 10;
        bar.style.width = v + '%';
        percent.innerText = v + '%';
        if (v >= 100) {
            clearInterval(timer);
            const agentSelect = document.getElementById('skillAgentIn');
            skills.push({
                id: Date.now(),
                title: name,
                agent: agentSelect ? agentSelect.value : 'research',
                tag: '已下载',
                icon: 'zap',
                desc: '部署的能力。'
            });
            renderSkillLibrary();
            setTimeout(() => {
                toggleModal('addAssetModal');
                btn.disabled = false;
                box.classList.add('hidden');
                bar.style.width = '0%';
                percent.innerText = '0%';
                showToast('安装成功', 'success');
            }, 500);
        }
    }, 80);
}

// ============ API Key Management ============
const PROVIDER_DEFAULTS = {
    zhipu:    { name: '智谱 (GLM)',       baseUrl: 'https://open.bigmodel.cn/api/paas/v4/' },
    deepseek: { name: 'DeepSeek',          baseUrl: 'https://api.deepseek.com/v1/' },
    openai:   { name: 'OpenAI',            baseUrl: 'https://api.openai.com/v1/' },
    moonshot: { name: 'Moonshot (Kimi)',    baseUrl: 'https://api.moonshot.cn/v1/' },
    qwen:     { name: '通义千问',          baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1/' },
    custom:   { name: '自定义',            baseUrl: '' },
};

function loadApiKeysFromStorage() {
    const saved = localStorage.getItem('citewise_api_keys');
    if (saved) {
        try { return JSON.parse(saved); } catch { /* ignore */ }
    }
    return [];
}

function saveApiKeysToStorage(keys) {
    localStorage.setItem('citewise_api_keys', JSON.stringify(keys));
}

function getActiveApiKey() {
    const keys = loadApiKeysFromStorage();
    return keys.find(k => k.active) || null;
}

function renderApiKeyList() {
    const c = document.getElementById('apiKeyListContainer');
    if (!c) return;
    const keys = loadApiKeysFromStorage();
    if (keys.length === 0) {
        c.innerHTML = '<div class="col-span-2 text-center text-slate-400 py-12">暂无 API Key 配置，点击右上角「+ 新增配置」添加</div>';
        return;
    }
    c.innerHTML = keys.map((k, i) => {
        const prov = PROVIDER_DEFAULTS[k.provider] || { name: k.provider };
        return `<div class="p-5 bg-white border border-slate-200 rounded-2xl shadow-sm cursor-pointer hover:border-blue-300 transition-all ${k.active ? 'key-card-active' : ''}" onclick="editApiKey(${i})">
            <div class="flex justify-between items-start">
                <div class="font-bold text-sm text-slate-800">${escapeHtml(prov.name)}</div>
                <span class="text-[8px] font-bold uppercase px-2 py-0.5 rounded ${k.active ? 'bg-emerald-50 text-emerald-600' : 'bg-slate-100 text-slate-400'}">${k.active ? '使用中' : '未激活'}</span>
            </div>
            <div class="text-[10px] text-slate-400 font-mono mt-1">••••${escapeHtml((k.apiKey || '').slice(-4))}</div>
            <div class="text-[9px] text-slate-300 mt-1 truncate">${escapeHtml(k.baseUrl || '')}</div>
            <div class="flex gap-2 mt-3">
                <button onclick="event.stopPropagation();activateApiKey(${i})" class="text-[9px] px-2 py-1 rounded-lg ${k.active ? 'bg-emerald-50 text-emerald-600 font-bold' : 'bg-slate-50 text-slate-500 hover:bg-blue-50 hover:text-blue-600'}">${k.active ? '当前' : '启用'}</button>
                <button onclick="event.stopPropagation();confirmDeleteApiKey(${i})" class="text-[9px] px-2 py-1 rounded-lg bg-slate-50 text-slate-400 hover:bg-red-50 hover:text-red-500">删除</button>
            </div>
        </div>`;
    }).join('');
}

function onProviderChange() {
    const sel = document.getElementById('keyProviderSelect');
    const urlInput = document.getElementById('keyBaseUrlInput');
    if (!sel || !urlInput) return;
    const provider = sel.value;
    const prov = PROVIDER_DEFAULTS[provider];
    if (prov && prov.baseUrl) {
        urlInput.value = prov.baseUrl;
    }
}

function editApiKey(index) {
    const keys = loadApiKeysFromStorage();
    if (index >= 0 && index < keys.length) {
        const k = keys[index];
        document.getElementById('keyProviderSelect').value = k.provider || 'custom';
        document.getElementById('keyValueInput').value = k.apiKey || '';
        document.getElementById('keyBaseUrlInput').value = k.baseUrl || '';
        document.getElementById('keyDeleteBtn').classList.remove('hidden');
        document.getElementById('keyDeleteBtn').onclick = () => { deleteApiKeyByIndex(index); };
    }
    const resultEl = document.getElementById('keyVerifyResult');
    if (resultEl) resultEl.classList.add('hidden');
    toggleModal('keyModal');
}

function activateApiKey(index) {
    const keys = loadApiKeysFromStorage();
    keys.forEach((k, i) => { k.active = (i === index); });
    saveApiKeysToStorage(keys);
    renderApiKeyList();
    showToast(`已切换到 ${PROVIDER_DEFAULTS[keys[index].provider]?.name || keys[index].provider}`, 'success');
}

function confirmDeleteApiKey(index) {
    const keys = loadApiKeysFromStorage();
    const prov = PROVIDER_DEFAULTS[keys[index]?.provider] || { name: '' };
    if (confirm(`确定删除「${prov.name}」的 API Key 配置？`)) {
        deleteApiKeyByIndex(index);
    }
}

function deleteApiKeyByIndex(index) {
    let keys = loadApiKeysFromStorage();
    const wasActive = keys[index]?.active;
    keys.splice(index, 1);
    if (wasActive && keys.length > 0) keys[0].active = true;
    saveApiKeysToStorage(keys);
    renderApiKeyList();
    toggleModal('keyModal');
    showToast('API Key 已删除', 'success');
}

function deleteApiKey() {
    // Legacy — now handled by deleteApiKeyByIndex
}

async function verifyAndSaveApiKey() {
    const provider = document.getElementById('keyProviderSelect')?.value || 'zhipu';
    const apiKey = document.getElementById('keyValueInput')?.value.trim() || '';
    const baseUrl = document.getElementById('keyBaseUrlInput')?.value.trim() || '';
    const resultEl = document.getElementById('keyVerifyResult');
    const btn = document.getElementById('keyVerifyBtn');

    if (!apiKey) {
        if (resultEl) { resultEl.textContent = '请输入 API Key'; resultEl.className = 'text-xs font-bold p-2 rounded-lg text-red-600 bg-red-50'; resultEl.classList.remove('hidden'); }
        return;
    }

    if (btn) { btn.disabled = true; btn.textContent = '验证中...'; }

    try {
        const resp = await fetch(`${API_BASE}/api/apikeys/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, provider, base_url: baseUrl }),
        });
        const data = await resp.json();

        if (data.valid) {
            // Save to key list
            let keys = loadApiKeysFromStorage();
            // Check if same provider already exists -> update
            const existingIdx = keys.findIndex(k => k.provider === provider);
            const newKey = {
                provider,
                apiKey,
                baseUrl: data.base_url || baseUrl || PROVIDER_DEFAULTS[provider]?.baseUrl || '',
                active: true,
            };
            if (existingIdx >= 0) {
                keys[existingIdx] = newKey;
            } else {
                keys.push(newKey);
            }
            // Only one active at a time
            keys.forEach((k, i) => {
                const isNew = (existingIdx >= 0 && i === existingIdx) || (existingIdx < 0 && i === keys.length - 1);
                k.active = isNew;
            });
            saveApiKeysToStorage(keys);
            renderApiKeyList();

            // Also save to backend if logged in
            if (currentUser) {
                try {
                    await fetch(`${API_BASE}/api/apikeys/save`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ api_key: apiKey, user_id: currentUser.id }),
                    });
                } catch { /* non-critical */ }
            }

            if (resultEl) {
                resultEl.textContent = data.message;
                resultEl.className = 'text-xs font-bold p-2 rounded-lg text-emerald-600 bg-emerald-50 border border-emerald-100';
                resultEl.classList.remove('hidden');
            }
            showToast('API Key 验证成功', 'success');
            setTimeout(() => toggleModal('keyModal'), 1200);
        } else {
            if (resultEl) {
                resultEl.textContent = data.message;
                resultEl.className = 'text-xs font-bold p-2 rounded-lg text-red-600 bg-red-50 border border-red-100';
                resultEl.classList.remove('hidden');
            }
        }
    } catch (e) {
        if (resultEl) {
            resultEl.textContent = '验证请求失败: ' + e.message;
            resultEl.className = 'text-xs font-bold p-2 rounded-lg text-red-600 bg-red-50';
            resultEl.classList.remove('hidden');
        }
    }

    if (btn) { btn.disabled = false; btn.textContent = '验证'; }
}

// ============ TTS Placeholder ============
function simulateTTS() {
    showToast('生成播报中...', 'success');
}

// ============ UI Helpers ============
function safeClassAction(id, action, className) {
    const el = document.getElementById(id);
    if (el) el.classList[action](className);
}

function closeAssetDetail(type) {
    safeClassAction(`${type}ListView`, 'remove', 'hidden');
    safeClassAction(`${type}DetailView`, 'add', 'hidden');
}

function switchView(id, btn) {
    document.querySelectorAll('.view-section').forEach(s => s.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(i => {
        i.classList.remove('active', 'bg-blue-50', 'text-blue-700');
    });
    const target = document.getElementById(id);
    if (target) target.classList.add('active');
    if (btn) btn.classList.add('active');

    closePaperDetail();
    closeDraftEditor();
    closeAssetDetail('skill');
    closeAssetDetail('tool');
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

/** Escape string for use inside JS single-quoted strings within HTML onclick attributes */
function escapeJs(str) {
    if (!str) return '';
    return str.replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

// ============ Auth Functions ============
function showAuthModal(mode) {
    authMode = mode || 'login';
    const title = document.getElementById('authModalTitle');
    const submitBtn = document.getElementById('authSubmitBtn');
    const toggleBtn = document.getElementById('authToggleBtn');
    if (authMode === 'login') {
        if (title) title.textContent = '登录';
        if (submitBtn) submitBtn.textContent = '登录';
        if (toggleBtn) toggleBtn.textContent = '没有账号？立即注册';
    } else {
        if (title) title.textContent = '注册';
        if (submitBtn) submitBtn.textContent = '注册';
        if (toggleBtn) toggleBtn.textContent = '已有账号？立即登录';
    }
    // Clear form & errors
    const errEl = document.getElementById('authError');
    if (errEl) errEl.classList.add('hidden');
    const userIn = document.getElementById('authUsername');
    const passIn = document.getElementById('authPassword');
    if (userIn) userIn.value = '';
    if (passIn) passIn.value = '';
    // Always SHOW modal (never toggle — avoids closing when switching modes)
    const modal = document.getElementById('authModal');
    if (modal) modal.classList.remove('hidden');
}

function toggleAuthMode() {
    showAuthModal(authMode === 'login' ? 'register' : 'login');
}

function closeAuthModal() {
    const modal = document.getElementById('authModal');
    if (modal) modal.classList.add('hidden');
}

async function handleAuth() {
    const username = document.getElementById('authUsername').value.trim();
    const password = document.getElementById('authPassword').value;
    const errEl = document.getElementById('authError');
    if (!username || !password) {
        if (errEl) { errEl.textContent = '请填写用户名和密码'; errEl.classList.remove('hidden'); }
        return;
    }

    const endpoint = authMode === 'login' ? '/auth/login' : '/auth/register';
    try {
        const resp = await fetch(`${API_BASE}/api${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });

        // Parse JSON safely — server may return HTML on 500
        let data;
        try { data = await resp.json(); } catch { data = {}; }

        if (!resp.ok) {
            if (errEl) {
                let msg = data.detail || `请求失败 (${resp.status})`;
                if (Array.isArray(msg)) {
                    msg = msg.map(e => e.msg || String(e)).join('; ');
                }
                errEl.textContent = msg;
                errEl.classList.remove('hidden');
            }
            return;
        }

        currentUser = { id: data.user.id, username: data.user.username, token: data.token };
        localStorage.setItem('citewise_user', JSON.stringify(currentUser));
        updateAuthUI();
        closeAuthModal();
        showToast(authMode === 'login' ? '登录成功' : '注册成功', 'success');
    } catch (e) {
        if (errEl) { errEl.textContent = '网络错误: ' + e.message; errEl.classList.remove('hidden'); }
    }
}

function logout() {
    currentUser = null;
    localStorage.removeItem('citewise_user');
    updateAuthUI();
    showToast('已登出', 'success');
}

function updateAuthUI() {
    const name = currentUser ? currentUser.username : '未登录';
    const initial = currentUser ? currentUser.username.charAt(0).toUpperCase() : '?';
    const idText = currentUser ? `用户 ID: ${currentUser.id}` : '点击登录以启用数据隔离';

    // Sidebar
    const sidebarName = document.getElementById('sidebarUsername');
    const sidebarAvatar = document.getElementById('sidebarAvatar');
    if (sidebarName) sidebarName.textContent = name;
    if (sidebarAvatar) sidebarAvatar.textContent = initial;

    // Settings page
    const settingsName = document.getElementById('settingsUsername');
    const settingsAvatar = document.getElementById('settingsAvatar');
    const settingsId = document.getElementById('settingsUserId');
    const settingsLoginBtn = document.getElementById('settingsLoginBtn');
    if (settingsName) settingsName.textContent = name;
    if (settingsAvatar) settingsAvatar.textContent = initial;
    if (settingsId) settingsId.textContent = idText;
    if (settingsLoginBtn) {
        if (currentUser) {
            settingsLoginBtn.textContent = '登出';
            settingsLoginBtn.onclick = logout;
        } else {
            settingsLoginBtn.textContent = '登录';
            settingsLoginBtn.onclick = () => showAuthModal('login');
        }
    }
}

// ============ API Key Functions moved to renderApiKeyList section above ============

function openNewKeyModal() {
    // Reset form for new key entry
    const sel = document.getElementById('keyProviderSelect');
    const keyIn = document.getElementById('keyValueInput');
    const urlIn = document.getElementById('keyBaseUrlInput');
    const delBtn = document.getElementById('keyDeleteBtn');
    const resultEl = document.getElementById('keyVerifyResult');
    if (sel) sel.value = 'zhipu';
    if (keyIn) keyIn.value = '';
    if (urlIn) urlIn.value = PROVIDER_DEFAULTS.zhipu.baseUrl;
    if (delBtn) delBtn.classList.add('hidden');
    if (resultEl) resultEl.classList.add('hidden');
    toggleModal('keyModal');
}
