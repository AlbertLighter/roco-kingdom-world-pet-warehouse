// 放生推荐页面 JS 逻辑
let currentPage = 1;
const pageSize = 20;
let allSpeciesData = [];
let allFilteredSpecies = [];
let natureMap = {};
let talentSkillMap = {};
let currentConfigSpeciesId = null;

// ====== 初始化 ======
document.addEventListener('DOMContentLoaded', async function () {
    await loadNatureMap();
    await loadTalentSkillMap();
    await loadRecommendations();

    document.getElementById('refreshBtn').addEventListener('click', () => {
        currentPage = 1;
        loadRecommendations();
    });

    document.getElementById('configBtn').addEventListener('click', openConfigModal);

    document.getElementById('prevBtn').addEventListener('click', () => {
        if (currentPage > 1) { currentPage--; renderPage(); }
    });

    document.getElementById('nextBtn').addEventListener('click', () => {
        const totalPages = Math.ceil(allFilteredSpecies.length / pageSize);
        if (currentPage < totalPages) { currentPage++; renderPage(); }
    });

    document.getElementById('speciesFilter').addEventListener('change', () => { currentPage = 1; applyFilters(); });
    document.getElementById('minScoreFilter').addEventListener('input', () => { currentPage = 1; applyFilters(); });
    document.getElementById('displayFilter').addEventListener('change', () => { currentPage = 1; applyFilters(); });

    // 配置弹窗事件
    document.getElementById('closeModalBtn').addEventListener('click', closeConfigModal);
    document.getElementById('cancelConfigBtn').addEventListener('click', closeConfigModal);
    document.getElementById('saveConfigBtn').addEventListener('click', saveAllConfigs);

    // 单品种配置弹窗事件
    document.getElementById('closeSpeciesModalBtn').addEventListener('click', closeSpeciesConfigModal);
    document.getElementById('cancelSpeciesConfigBtn').addEventListener('click', closeSpeciesConfigModal);
    document.getElementById('saveSpeciesConfigBtn').addEventListener('click', saveSingleConfig);

    // 点击弹窗外部关闭
    document.getElementById('configModal').addEventListener('click', function (e) {
        if (e.target === this) closeConfigModal();
    });
    document.getElementById('speciesConfigModal').addEventListener('click', function (e) {
        if (e.target === this) closeSpeciesConfigModal();
    });
});

async function loadNatureMap() {
    try {
        // 从后端获取性格列表
        const res = await fetch('/api/pets?pageSize=1');
        // 性格是固定的，直接硬编码30种
        natureMap = {
            1: "大胆", 2: "固执", 3: "调皮", 4: "勇敢", 5: "逞强",
            6: "稳重", 7: "天真", 8: "懒散", 9: "悠闲", 10: "坦率",
            11: "聪明", 12: "专注", 13: "偏执", 14: "冷静", 15: "理性",
            16: "警惕", 17: "温顺", 18: "害羞", 19: "慎重", 20: "焦虑",
            21: "胆小", 22: "急躁", 23: "开朗", 24: "莽撞", 25: "热情",
            26: "沉默", 27: "忧郁", 28: "平和", 29: "粗心", 30: "踏实"
        };
        // 性格按加成属性分组（同属性排一列，每种属性恰好 5 个）
        window.NATURE_GROUPS = [
            { label: '生命', ids: [26, 27, 28, 29, 30] },
            { label: '物攻', ids: [1, 2, 3, 4, 5] },
            { label: '物防', ids: [6, 7, 8, 9, 10] },
            { label: '魔攻', ids: [11, 12, 13, 14, 15] },
            { label: '魔防', ids: [16, 17, 18, 19, 20] },
            { label: '速度', ids: [21, 22, 23, 24, 25] },
        ];
    } catch (e) {
        console.error('加载性格映射失败:', e);
    }
}

async function loadTalentSkillMap() {
    try {
        const res = await fetch('/api/config/talent_skills');
        if (res.ok) {
            const data = await res.json();
            talentSkillMap = data;
        }
    } catch (e) {
        console.error('加载特长映射失败:', e);
    }
}

function getNatureName(id) {
    return natureMap[id] || ('未知(' + id + ')');
}

function getTalentSkillName(id) {
    if (!id) return '';
    return (talentSkillMap[id] && talentSkillMap[id].name) || '';
}

// ====== 数据加载 ======
async function loadRecommendations() {
    const summaryArea = document.getElementById('summaryArea');
    summaryArea.innerHTML = '<div class="summary-loading">正在计算放生推荐...</div>';
    document.getElementById('releaseList').innerHTML = '';

    try {
        const res = await fetch(`/api/release_recommendations?page=1&page_size=5000`);
        if (!res.ok) {
            summaryArea.innerHTML = `<div class="summary-loading" style="color:#e74c3c;">加载失败: ${res.status}</div>`;
            return;
        }
        const data = await res.json();
        allSpeciesData = data;
        renderSummary(data.summary);
        buildSpeciesFilter(data.species_groups);

        // 展平所有品种用于筛选
        allFilteredSpecies = [...data.species_groups];
        applyFilters();
    } catch (e) {
        summaryArea.innerHTML = `<div class="summary-loading" style="color:#e74c3c;">加载失败: ${e.message}</div>`;
    }
}

// ====== 渲染概览统计 ======
function renderSummary(summary) {
    const area = document.getElementById('summaryArea');
    if (!summary) {
        area.innerHTML = '<div class="summary-loading">暂无数据</div>';
        return;
    }
    area.innerHTML = `
        <div class="summary-stat">
            <span class="summary-icon">📊</span>
            <span class="summary-label">精灵总数</span>
            <span class="summary-value">${summary.total_active_pets}</span>
        </div>
        <div class="summary-stat recommended">
            <span class="summary-icon">❌</span>
            <span class="summary-label">建议放生</span>
            <span class="summary-value">${summary.total_recommended}</span>
        </div>
        <div class="summary-stat kept">
            <span class="summary-icon">🔒</span>
            <span class="summary-label">特长保留</span>
            <span class="summary-value">
                慈悲为怀 ${summary.kept_by_mercy}
                | 同乘 ${summary.kept_by_ride}
                | 爱分享 ${summary.kept_by_share}
            </span>
        </div>
    `;
}

// ====== 品种筛选 ======
function buildSpeciesFilter(speciesGroups) {
    const select = document.getElementById('speciesFilter');
    const currentVal = select.value;
    select.innerHTML = '<option value="">全部品种</option>';
    speciesGroups.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.base_id;
        opt.textContent = g.species_name;
        select.appendChild(opt);
    });
    if (currentVal) select.value = currentVal;
}

function applyFilters() {
    const speciesFilter = document.getElementById('speciesFilter').value;
    const minScore = parseFloat(document.getElementById('minScoreFilter').value) || 0;
    const displayFilter = document.getElementById('displayFilter').value;

    let filtered = [...allSpeciesData.species_groups];

    // 品种筛选
    if (speciesFilter) {
        filtered = filtered.filter(g => g.base_id == speciesFilter);
    }

    // 评分筛选 & 显示筛选
    filtered = filtered.map(g => {
        let pets = g.pets;
        if (displayFilter === 'recommended') {
            pets = pets.filter(p => p.is_recommended);
        } else if (displayFilter === 'kept') {
            pets = pets.filter(p => p.is_kept);
        }
        if (minScore > 0) {
            pets = pets.filter(p => p.score <= minScore);
        }
        return { ...g, pets };
    }).filter(g => g.pets.length > 0);

    allFilteredSpecies = filtered;
    currentPage = 1;
    renderPage();
}

// ====== 渲染分页 ======
function renderPage() {
    const container = document.getElementById('releaseList');
    const totalPages = Math.ceil(allFilteredSpecies.length / pageSize);

    document.getElementById('prevBtn').disabled = currentPage <= 1;
    document.getElementById('nextBtn').disabled = currentPage >= totalPages;
    document.getElementById('pageInfo').textContent = `第 ${currentPage} 页 / 共 ${totalPages} 页`;

    const start = (currentPage - 1) * pageSize;
    const pageData = allFilteredSpecies.slice(start, start + pageSize);

    if (pageData.length === 0) {
        container.innerHTML = '<div style="text-align:center;padding:40px;color:#95a5a6;">没有符合条件的品种</div>';
        return;
    }

    container.innerHTML = pageData.map(g => renderSpeciesGroup(g)).join('');
}

// ====== 渲染品种分组 ======
function renderSpeciesGroup(group) {
    const keptCount = group.pets.filter(p => p.is_kept).length;
    const recCount = group.pets.filter(p => p.is_recommended).length;

    // 展示家族内所有形态名称（多于一个形态时才显示）
    let memberHtml = '';
    if (group.member_species && group.member_species.length > 1) {
        memberHtml = `<div class="species-member-list">包含形态: ${group.member_species.map(m => escapeHtml(m.name)).join(' · ')}</div>`;
    }

    return `
        <div class="species-group">
            <div class="species-group-header">
                <span class="species-group-title">
                    ${escapeHtml(group.species_name)}
                    <span class="species-group-count">
                        (共 ${group.total_count} 只 · 
                        <span class="text-kept">保留 ${group.keep_count} 只</span> · 
                        <span class="text-recommended">建议放生 ${group.recommended_count} 只</span>)
                    </span>
                </span>
                <button class="config-species-btn" onclick="openSpeciesConfig(${group.base_id}, '${escapeHtml(group.species_name)}')">配置此品种</button>
            </div>
            ${memberHtml}
            <div class="species-pet-grid">
                ${group.pets.map(p => renderPetCard(p, group.species_name)).join('')}
            </div>
        </div>
    `;
}

// ====== 渲染宠物卡片 ======
function renderPetCard(pet, speciesName) {
    const genderSymbol = ['', '♂', '♀'][pet.gender] || '';
    const genderClass = pet.gender === 1 ? 'male' : (pet.gender === 2 ? 'female' : '');
    const talentNames = { 1: '普通', 2: '良好', 3: '优秀', 4: '极品' };
    const talentName = talentNames[pet.talent_rank] || '';

    const talentSkillName = getTalentSkillName(pet.talent_skill);
    const mutationBadge = pet.mutation ? `<span class="badge" style="background:#fce4ec;color:#c62828;">异色</span>` : '';

    // 评分颜色
    let scoreClass = 'score-low';
    if (pet.score >= 60) scoreClass = 'score-high';
    else if (pet.score >= 30) scoreClass = 'score-mid';

    const reasonsHtml = pet.reasons && pet.reasons.length > 0
        ? `<div class="release-reasons">${pet.reasons.map(r => `<span>${escapeHtml(r)}</span>`).join('')}</div>`
        : '';

    return `
        <div class="release-pet-card ${pet.is_recommended ? 'recommended' : 'kept'} ${genderClass}">
            <div class="release-card-badge ${pet.is_recommended ? 'badge-rec' : 'badge-keep'}">
                ${pet.is_recommended ? '❌ 建议放生' : '✅ 保留'}
            </div>
            <div class="release-card-header">
                <span class="pet-sn">#${pet.serial_num}</span>
                <span class="pet-level">Lv.${pet.level}</span>
            </div>
            <div class="release-card-score ${scoreClass}">${pet.score}</div>
            <div class="release-card-name">
                ${genderSymbol ? `<span class="${genderClass === 'male' ? 'gender-male' : 'gender-female'}">${genderSymbol}</span>` : ''}
                ${escapeHtml(pet.name)}
            </div>
            <div class="badge-row" style="justify-content:center;">
                <span class="badge badge-talent-${pet.talent_rank}">${talentName}</span>
                ${pet.nature_name ? `<span class="badge" style="background:#e8f5e9;color:#2e7d32;">${escapeHtml(pet.nature_name)}</span>` : ''}
                ${talentSkillName ? `<span class="badge badge-talent-skill">⭐ ${escapeHtml(talentSkillName)}</span>` : ''}
                ${mutationBadge}
            </div>
            <div class="release-card-stats">
                天赋: ${pet.total_talent}
                ${pet.speed_talent > 0 ? `· 速度+${pet.speed_talent}` : ''}
            </div>
            ${reasonsHtml}
        </div>
    `;
}

// ====== 品种配置弹窗 ======
function openSpeciesConfig(baseId, speciesName) {
    currentConfigSpeciesId = baseId;
    document.getElementById('speciesConfigTitle').textContent = `配置 - ${speciesName}`;
    document.getElementById('speciesKeepCount').value = 3;

    // 加载当前配置
    const ids = [];
    const speciesGroup = allSpeciesData.species_groups.find(g => g.base_id == baseId);
    if (speciesGroup && speciesGroup.config) {
        ids.push(...(speciesGroup.config.preferred_nature_ids || []));
        document.getElementById('speciesKeepCount').value = speciesGroup.config.keep_count || 3;
    }

    // 填充性格标签（按属性分组）
    const container = document.getElementById('speciesNatureContainer');
    container.innerHTML = '';
    const groups = window.NATURE_GROUPS || [];
    for (const group of groups) {
        const col = document.createElement('div');
        col.className = 'nature-group';
        const label = document.createElement('div');
        label.className = 'nature-group-label';
        label.textContent = group.label;
        col.appendChild(label);
        for (const id of group.ids) {
            const tag = document.createElement('span');
            tag.className = 'nature-tag' + (ids.includes(id) ? ' selected' : '');
            tag.textContent = getNatureName(id);
            tag.dataset.id = id;
            tag.addEventListener('click', () => tag.classList.toggle('selected'));
            col.appendChild(tag);
        }
        container.appendChild(col);
    }

    document.getElementById('speciesConfigModal').style.display = 'flex';
}

function closeSpeciesConfigModal() {
    document.getElementById('speciesConfigModal').style.display = 'none';
    currentConfigSpeciesId = null;
}

async function saveSingleConfig() {
    if (!currentConfigSpeciesId) return;
    const container = document.getElementById('speciesNatureContainer');
    const natureIds = Array.from(container.querySelectorAll('.nature-tag.selected')).map(t => parseInt(t.dataset.id));
    const keepCount = parseInt(document.getElementById('speciesKeepCount').value) || 3;

    try {
        const res = await fetch('/api/species_preferences', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                preferences: [{
                    base_id: currentConfigSpeciesId,
                    preferred_nature_ids: natureIds,
                    keep_count: keepCount
                }]
            })
        });
        if (res.ok) {
            closeSpeciesConfigModal();
            await loadRecommendations();
        } else {
            alert('保存失败');
        }
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

// ====== 全局配置弹窗 ======
async function openConfigModal() {
    const modal = document.getElementById('configModal');
    const tbody = document.getElementById('configTableBody');

    modal.style.display = 'flex';
    tbody.innerHTML = '<tr><td colspan="3">加载中...</td></tr>';

    try {
        const res = await fetch('/api/species_preferences');
        const data = await res.json();
        renderConfigTable(data.preferences);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="3" style="color:#e74c3c;">加载失败: ${e.message}</td></tr>`;
    }
}

function renderConfigTable(preferences) {
    const tbody = document.getElementById('configTableBody');
    if (!preferences || preferences.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="color:#95a5a6;">暂无配置</td></tr>';
        return;
    }

    tbody.innerHTML = preferences.map(p => {
        const natureIds = p.preferred_nature_ids || [];
        const groups = window.NATURE_GROUPS || [];
        const groupsHtml = groups.map(g => {
            const tags = g.ids.map(id => {
                const sel = natureIds.includes(id) ? ' selected' : '';
                return `<span class="nature-tag${sel}" data-id="${id}">${getNatureName(id)}</span>`;
            }).join('');
            return `<div class="nature-group"><div class="nature-group-label">${g.label}</div>${tags}</div>`;
        }).join('');
        return `
            <tr>
                <td>${escapeHtml(p.species_name)}</td>
                <td>
                    <div class="nature-tag-grid" data-base-id="${p.base_id}">
                        ${groupsHtml}
                    </div>
                </td>
                <td>
                    <input type="number" class="config-keep" data-base-id="${p.base_id}" value="${p.keep_count}" min="1" max="99" style="width:60px;padding:4px;">
                </td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('.nature-tag').forEach(tag => {
        tag.addEventListener('click', () => tag.classList.toggle('selected'));
    });
}

function closeConfigModal() {
    document.getElementById('configModal').style.display = 'none';
}

async function saveAllConfigs() {
    const natureGrids = document.querySelectorAll('.nature-tag-grid');
    const keepInputs = document.querySelectorAll('.config-keep');

    const prefs = [];
    natureGrids.forEach(grid => {
        const baseId = parseInt(grid.dataset.baseId);
        const natureIds = Array.from(grid.querySelectorAll('.nature-tag.selected')).map(t => parseInt(t.dataset.id));
        const keepInput = document.querySelector(`.config-keep[data-base-id="${baseId}"]`);
        const keepCount = keepInput ? parseInt(keepInput.value) || 3 : 3;
        prefs.push({ base_id: baseId, preferred_nature_ids: natureIds, keep_count: keepCount });
    });

    try {
        const res = await fetch('/api/species_preferences', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ preferences: prefs })
        });
        if (res.ok) {
            closeConfigModal();
            await loadRecommendations();
        } else {
            alert('保存失败');
        }
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

// ====== 工具函数 ======
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
