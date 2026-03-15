let fac;
let state = {
    mode: 'osu',
    collections: [],
    selectedCollection: null,
    selectedItem: null,
    displayedItems: [],
    sortColumn: null,
    sortDesc: false,
    columns: {},
    columnOrder: []
};

const MODES = ['osu', 'taiko', 'ctb', 'mania'];
const COLUMNS = [
    ['name_original', '名称（原语言）', true],
    ['star_rating', '难度', true],
    ['bid', 'BID', true],
    ['artist', '艺术家（原语言）', true],
    ['difficulty_name', '难度名', true],
    ['mapper', '谱师', true],
    ['mode', '模式', true],
    ['sid', 'SID', false],
    ['cs', 'CS', false],
    ['od', 'OD', false],
    ['ar', 'AR', false],
    ['hp', 'HP', false],
    ['note_count', 'Note数', false],
    ['length', '长度', false],
    ['bpm', 'BPM', false],
    ['status', '状态', false],
    ['name', '名称', false],
    ['md5', 'MD5', false]
];

async function init() {
    fac = new FastAverageColor();
    
    COLUMNS.forEach(([key, label, visible]) => {
        state.columns[key] = visible;
        state.columnOrder.push(key);
    });
    
    const modes = document.getElementById('modeButtons');
    const modeIcons = {
        osu: 'fa-extra-mode-osu',
        taiko: 'fa-extra-mode-taiko',
        ctb: 'fa-extra-mode-fruits',
        mania: 'fa-extra-mode-mania'
    };
    MODES.forEach(mode => {
        const btn = document.createElement('button');
        btn.className = 'px-3 py-1 text-xs font-bold border rounded transition ' +
            (mode === state.mode ? 'bg-blue-100 border-blue-500 text-blue-700' : 'bg-gray-100 border-gray-300 hover:bg-gray-200');
        btn.innerHTML = `<i class="${modeIcons[mode]} mr-1"></i>${mode === 'ctb' ? 'CTB' : mode.toUpperCase()}`;
        btn.onclick = () => setMode(mode);
        modes.appendChild(btn);
    });
    
    renderTableHead();
    await refreshRealm();
}

async function refreshRealm() {
    const result = await pywebview.api.refresh_detected_realm();
    const statusEl = document.getElementById('status');
    statusEl.innerHTML = `<i class="fas fa-${result.detected ? 'check-circle text-green-600' : 'info-circle text-blue-600'} mr-2"></i>${result.status}`;
    document.getElementById('loadBtn').disabled = !result.detected;
}

async function loadRealm() {
    const statusEl = document.getElementById('status');
    document.getElementById('loadBtn').disabled = true;
    statusEl.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>正在读取 realm，请稍候...';
    const result = await pywebview.api.load_realm();
    if (result.success) {
        state.collections = result.collections;
        statusEl.innerHTML = `<i class="fas fa-check-circle text-green-600 mr-2"></i>${result.status}`;
        refreshCollections();
    } else {
        alert('加载失败: ' + result.error);
        statusEl.innerHTML = `<i class="fas fa-exclamation-circle text-red-600 mr-2"></i>${result.status}`;
    }
    document.getElementById('loadBtn').disabled = false;
}

function setMode(mode) {
    state.mode = mode;
    const modeIcons = {
        osu: 'fa-extra-mode-osu',
        taiko: 'fa-extra-mode-taiko',
        ctb: 'fa-extra-mode-fruits',
        mania: 'fa-extra-mode-mania'
    };
    document.querySelectorAll('#modeButtons button').forEach((btn, i) => {
        const m = MODES[i];
        btn.className = 'px-3 py-1 text-xs font-bold border rounded transition ' +
            (m === mode ? 'bg-blue-100 border-blue-500 text-blue-700' : 'bg-gray-100 border-gray-300 hover:bg-gray-200');
        btn.innerHTML = `<i class="${modeIcons[m]} mr-1"></i>${m === 'ctb' ? 'CTB' : m.toUpperCase()}`;
    });
    refreshCollections();
}

function refreshCollections() {
    const filtered = state.collections.filter(c => c.items[state.mode] && c.items[state.mode].length > 0);
    const list = document.getElementById('collectionList');
    list.innerHTML = '';
    
    filtered.forEach((col, i) => {
        const div = document.createElement('div');
        div.className = 'p-2 cursor-pointer border-b border-gray-200 flex justify-between items-center hover:bg-gray-50 transition';
        div.innerHTML = `<span class="text-sm"><i class="fas fa-folder mr-2 text-yellow-500"></i>${col.name}</span><span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">${col.items[state.mode].length}</span>`;
        div.onclick = () => selectCollection(i, filtered);
        list.appendChild(div);
    });
    
    document.getElementById('collectionSummary').textContent = 
        `当前模式: ${state.mode} | 收藏夹数: ${filtered.length} / ${state.collections.length}`;
    
    if (filtered.length > 0) {
        selectCollection(0, filtered);
    } else {
        state.selectedCollection = null;
        state.displayedItems = [];
        refreshBeatmaps();
    }
}

function selectCollection(index, filtered) {
    state.selectedCollection = filtered[index];
    document.querySelectorAll('#collectionList > div').forEach((el, i) => {
        el.className = 'p-2 cursor-pointer border-b border-gray-200 flex justify-between items-center hover:bg-gray-50 transition ' +
            (i === index ? 'bg-blue-100' : '');
    });
    refreshBeatmaps();
}

function refreshBeatmaps() {
    if (!state.selectedCollection) {
        document.getElementById('itemSummary').textContent = '';
        document.getElementById('tableBody').innerHTML = '';
        document.getElementById('exportBtn').disabled = true;
        return;
    }
    
    let items = state.selectedCollection.items[state.mode] || [];
    if (state.sortColumn) {
        items = [...items].sort((a, b) => {
            const av = a[state.sortColumn];
            const bv = b[state.sortColumn];
            if (av == null) return 1;
            if (bv == null) return -1;
            const cmp = av < bv ? -1 : av > bv ? 1 : 0;
            return state.sortDesc ? -cmp : cmp;
        });
    }
    
    state.displayedItems = items;
    const missing = items.filter(i => i.missing).length;
    document.getElementById('itemSummary').textContent = 
        `收藏夹: ${state.selectedCollection.name} | 显示 ${items.length} 项 | 缺失 ${missing} 项`;
    
    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';
    const visibleCols = state.columnOrder.filter(k => state.columns[k]);
    
    items.forEach((item, i) => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-gray-50 cursor-pointer transition ' + (item.missing ? 'text-rose-700' : '');
        tr.onclick = () => selectBeatmap(i);
        tr.ondblclick = () => openDetail(item);
        
        visibleCols.forEach(col => {
            const td = document.createElement('td');
            td.className = 'p-1.5 border border-gray-100';
            td.textContent = item[col] || '-';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    
    document.getElementById('exportBtn').disabled = items.length === 0;
    if (items.length > 0) selectBeatmap(0);
}

function selectBeatmap(index) {
    state.selectedItem = state.displayedItems[index];
    document.querySelectorAll('#tableBody tr').forEach((el, i) => {
        const isSelected = i === index;
        const isMissing = state.displayedItems[i].missing;
        el.className = 'hover:bg-gray-50 cursor-pointer transition ' +
            (isSelected ? 'bg-blue-100 ' : '') +
            (isMissing ? 'text-rose-700' : '');
    });
    loadPreview(state.selectedItem);
}

async function loadPreview(item) {
    const preview = document.getElementById('preview');
    if (!item || item.missing) {
        preview.style.backgroundColor = '';
        preview.style.color = '';
        preview.innerHTML = `<span class="text-gray-400 text-sm"><i class="fas fa-${item ? 'exclamation-triangle' : 'image'} mr-2"></i>${item ? '该条目缺少本地谱面信息' : '选择谱面后显示背景图'}</span>`;
        return;
    }
    preview.innerHTML = '<i class="fas fa-spinner fa-spin text-gray-400"></i>';
    const result = await pywebview.api.get_cover(item.beatmap_set_id);
    if (result.success) {
        const img = document.createElement('img');
        img.className = 'max-w-full max-h-full rounded';
        img.src = result.path;
        img.onload = () => {
            if (fac) {
                fac.getColorAsync(img)
                    .then(color => {
                        preview.style.backgroundColor = color.rgba;
                        preview.style.color = color.isDark ? '#fff' : '#000';
                    })
                    .catch(e => console.log(e));
            }
        };
        preview.innerHTML = '';
        preview.appendChild(img);
    } else {
        preview.style.backgroundColor = '';
        preview.innerHTML = '<span class="text-gray-400 text-sm"><i class="fas fa-image-slash mr-2"></i>暂无可用图片</span>';
    }
}

function renderTableHead() {
    const thead = document.getElementById('tableHead');
    const tr = document.createElement('tr');
    const visibleCols = state.columnOrder.filter(k => state.columns[k]);
    
    visibleCols.forEach(col => {
        const th = document.createElement('th');
        th.className = 'p-1.5 border border-gray-300 cursor-pointer hover:bg-gray-200 transition text-left';
        const label = COLUMNS.find(c => c[0] === col)[1];
        const sortIcon = state.sortColumn === col ? (state.sortDesc ? '<i class="fas fa-sort-down ml-1"></i>' : '<i class="fas fa-sort-up ml-1"></i>') : '';
        th.innerHTML = label + sortIcon;
        th.onclick = () => toggleSort(col);
        tr.appendChild(th);
    });
    thead.innerHTML = '';
    thead.appendChild(tr);
}

function toggleSort(col) {
    if (state.sortColumn === col) {
        state.sortDesc = !state.sortDesc;
        if (state.sortDesc && state.sortColumn === col) {
            state.sortColumn = null;
            state.sortDesc = false;
        }
    } else {
        state.sortColumn = col;
        state.sortDesc = false;
    }
    renderTableHead();
    refreshBeatmaps();
}

async function openDetail(item) {
    document.getElementById('modalTitle').textContent = item.name_original || '-';
    const fields = document.getElementById('modalFields');
    fields.innerHTML = '';
    
    const data = [
        ['名称', item.name],
        ['艺术家（原语言）', item.artist],
        ['谱师', item.mapper],
        ['难度名', item.difficulty_name],
        ['模式', item.mode],
        ['状态', item.status],
        ['难度', item.star_rating],
        ['长度', item.length],
        ['BPM', item.bpm],
        ['Note数', item.note_count],
        ['BID', item.bid],
        ['SID', item.sid],
        ['CS', item.cs],
        ['AR', item.ar],
        ['OD', item.od],
        ['HP', item.hp],
        ['MD5', item.md5]
    ];
    
    data.forEach(([label, value]) => {
        const div = document.createElement('div');
        div.innerHTML = `<label class="text-gray-500 text-xs block">${label}</label><div class="text-sm mt-0.5">${value || '-'}</div>`;
        fields.appendChild(div);
    });
    
    const cover = document.getElementById('modalCover');
    const modal = document.getElementById('detailModal');
    if (!item.missing) {
        const result = await pywebview.api.get_cover(item.beatmap_set_id);
        if (result.success) {
            cover.src = result.path;
            cover.classList.remove('hidden');
            cover.onload = () => {
                if (fac) {
                    fac.getColorAsync(cover)
                        .then(color => {
                            modal.querySelector('.modal-content-inner').style.backgroundColor = color.rgba;
                            modal.querySelector('.modal-content-inner').style.color = color.isDark ? '#fff' : '#000';
                        })
                        .catch(e => console.log(e));
                }
            };
        } else {
            cover.classList.add('hidden');
        }
    } else {
        cover.classList.add('hidden');
    }
    
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeModal() {
    const modal = document.getElementById('detailModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    modal.querySelector('.modal-content-inner').style.backgroundColor = '';
    modal.querySelector('.modal-content-inner').style.color = '';
}

function openSettings() {
    const settings = document.getElementById('columnSettings');
    settings.innerHTML = '';
    
    COLUMNS.forEach(([key, label]) => {
        const div = document.createElement('div');
        div.className = 'flex items-center';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'mr-2 w-4 h-4 cursor-pointer';
        checkbox.checked = state.columns[key];
        checkbox.onchange = () => {
            state.columns[key] = checkbox.checked;
            renderTableHead();
            refreshBeatmaps();
        };
        const labelEl = document.createElement('label');
        labelEl.className = 'text-sm cursor-pointer';
        labelEl.textContent = label;
        labelEl.onclick = () => checkbox.click();
        div.appendChild(checkbox);
        div.appendChild(labelEl);
        settings.appendChild(div);
    });
    
    const modal = document.getElementById('settingsModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closeSettingsModal() {
    const modal = document.getElementById('settingsModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

function resetColumns() {
    COLUMNS.forEach(([key, , visible]) => {
        state.columns[key] = visible;
    });
    openSettings();
    renderTableHead();
    refreshBeatmaps();
}

async function exportView() {
    if (!state.selectedCollection || state.displayedItems.length === 0) {
        alert('无法导出：请先选择一个收藏夹。');
        return;
    }
    
    const result = await pywebview.api.export_view(
        state.selectedCollection.name,
        state.mode,
        state.displayedItems,
        state.columnOrder.filter(k => state.columns[k])
    );
    
    if (result.success) {
        alert('导出成功: ' + result.path);
    } else {
        alert('导出失败: ' + result.error);
    }
}

// 导出函数到全局作用域
window.init = init;
window.refreshRealm = refreshRealm;
window.loadRealm = loadRealm;
window.openSettings = openSettings;
window.closeSettingsModal = closeSettingsModal;
window.resetColumns = resetColumns;
window.exportView = exportView;
window.closeModal = closeModal;

window.addEventListener('pywebviewready', init);
