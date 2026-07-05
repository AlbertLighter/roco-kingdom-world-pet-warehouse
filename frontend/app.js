let currentPage = 1;
const pageSize = 30;

// 配置缓存
let bloodlineMap = {};
let typeMap = {};
let medalMap = {};
let talentSkillMap = {};

// 放生推荐缓存
let releaseMap = {};           // serial_num → {is_recommended, score, reasons}
let speciesPrefsList = [];    // 品种偏好列表（用于配置弹窗）
let currentConfigBaseId = null;

const natureMap = {
    1: "大胆", 2: "固执", 3: "调皮", 4: "勇敢", 5: "逞强",
    6: "稳重", 7: "天真", 8: "懒散", 9: "悠闲", 10: "坦率",
    11: "聪明", 12: "专注", 13: "偏执", 14: "冷静", 15: "理性",
    16: "警惕", 17: "温顺", 18: "害羞", 19: "慎重", 20: "焦虑",
    21: "胆小", 22: "急躁", 23: "开朗", 24: "莽撞", 25: "热情",
    26: "沉默", 27: "忧郁", 28: "平和", 29: "粗心", 30: "踏实"
};

function getNatureName(id) {
    return natureMap[id] || ('未知(' + id + ')');
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ---- 字段对照表（同微信小游戏） ----
// PetBloodline (血脉):   PET_BLOOD_CONF.json  id → { name, blood_name }
// PetSkillDamType (系别): TYPE_DICTIONARY.json  id → { type_name, short_name }
// PetMedal (奖牌):       MEDAL_CONF.json  id → { name, quality, desc }
// EquipSkill1~4 (技能):  SKILL_CONF.json  id → { name, desc, energy_cost, ... }
// PetMutation (变异):    变异类型 ID → 异色标签
// PetTalentRank (天赋):  1=普通, 2=良好, 3=优秀, 4=极品
// PetNature (性格):      性格ID → { name, buff(属性索引), debuff(属性索引) }
// 六维属性:
//   MaxHp(生命) / PhyAttack(物攻) / MagAttack(魔攻)
//   PhyDefense(物防) / MagDefense(魔防) / Speed(速度)
//   每个属性有: 当前值 / 种族值(Race) / 天赋值(Talent)

async function fetchConfigs() {
    try {
        const [blRes, tpRes, mdRes, tsRes] = await Promise.all([
            fetch('/api/config/bloodlines'),
            fetch('/api/config/types'),
            fetch('/api/config/medals'),
            fetch('/api/config/talent_skills')
        ]);
        bloodlineMap = await blRes.json();
        typeMap = await tpRes.json();
        medalMap = await mdRes.json();
        talentSkillMap = await tsRes.json();
    } catch (e) {
        console.warn('Failed to load config maps:', e);
    }
}

// ---- DOM 引用 ----
const petListEl = document.getElementById('petList');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const pageInfo = document.getElementById('pageInfo');
const refreshTimeValue = document.getElementById('refreshTimeValue');

async function fetchReleaseData() {
    try {
        const res = await fetch('/api/release_recommendations?page=1&page_size=5000');
        if (!res.ok) return;
        const data = await res.json();
        speciesPrefsList = data.species_groups || [];
        releaseMap = {};
        for (const group of speciesPrefsList) {
            for (const p of group.pets || []) {
                releaseMap[p.serial_num] = {
                    is_recommended: p.is_recommended,
                    is_kept: p.is_kept,
                    score: p.score,
                    reasons: p.reasons || [],
                };
            }
        }
    } catch (e) {
        console.warn('获取放生推荐失败:', e);
    }
}

async function fetchRefreshTime() {
    try {
        const response = await fetch('/api/refresh_time');
        const data = await response.json();
        refreshTimeValue.textContent = data.refresh_time || '暂无数据（请先同步）';
    } catch (error) {
        refreshTimeValue.textContent = '获取失败';
    }
}

async function fetchPets() {
    const name = searchInput.value.trim().slice(0, 100);
    const url = `/api/pets?page=${currentPage}&pageSize=${pageSize}&name=${encodeURIComponent(name)}`;
    try {
        const response = await fetch(url);
        const data = await response.json();
        renderPets(data.data);
        updatePagination(data.total);
        document.getElementById('fetchError')?.remove();
    } catch (error) {
        console.error('Failed to fetch pets:', error);
        const errorEl = document.createElement('div');
        errorEl.id = 'fetchError';
        errorEl.style.cssText = 'color: #e74c3c; text-align: center; padding: 20px;';
        errorEl.textContent = '❌ 网络错误，无法获取宠物数据';
        petListEl.innerHTML = '';
        petListEl.appendChild(errorEl);
    }
}

// ---- 六维雷达图 ----
function renderHexagon(pet) {
    const stats = [
        { key: 'hp', label: 'HP', talent: 'hp_talent', match: ['HP', '生命'] },
        { key: 'apAttack', label: '魔攻', talent: 'apAttack_talent', match: ['魔攻'] },
        { key: 'apDefense', label: '魔防', talent: 'apDefense_talent', match: ['魔防', '魔抗'] },
        { key: 'speed', label: '速度', talent: 'speed_talent', match: ['速度'] },
        { key: 'adDefense', label: '物防', talent: 'adDefense_talent', match: ['物防'] },
        { key: 'adAttack', label: '物攻', talent: 'adAttack_talent', match: ['物攻'] }
    ];
    const size = 200;
    const cx = size / 2, cy = size / 2;
    const r_max = 55;
    const stat_max = 400;

    const points = stats.map((s, i) => {
        const angle = (i * 60 - 90) * (Math.PI / 180);
        const val = Math.min(pet[s.key], stat_max);
        const r = (val / stat_max) * r_max;
        return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
    }).join(' ');

    const bg = (pct) => stats.map((_, i) => {
        const angle = (i * 60 - 90) * (Math.PI / 180);
        return `${cx + r_max * pct * Math.cos(angle)},${cy + r_max * pct * Math.sin(angle)}`;
    }).join(' ');

    return `
        <div class="hexagon-container">
            <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
                <polygon points="${bg(1)}" fill="none" stroke="#ddd" stroke-width="1" />
                <polygon points="${bg(0.5)}" fill="none" stroke="#ddd" stroke-width="1" />
                ${stats.map((_, i) => {
                    const angle = (i * 60 - 90) * (Math.PI / 180);
                    return `<line x1="${cx}" y1="${cy}" x2="${cx + r_max * Math.cos(angle)}" y2="${cy + r_max * Math.sin(angle)}" stroke="#ddd" stroke-width="1" />`;
                }).join('')}
                <polygon points="${points}" fill="rgba(52,152,219,0.35)" stroke="#3498db" stroke-width="2" />
                ${stats.map((s, i) => {
                    const angle = (i * 60 - 90) * (Math.PI / 180);
                    const x = cx + (r_max + 10) * Math.cos(angle);
                    const y = cy + (r_max + 10) * Math.sin(angle);
                    const anchor = Math.abs(x - cx) < 10 ? 'middle' : (x > cx ? 'start' : 'end');
                    let ind = '', vc = '#2c3e50';
                    if (s.match.includes(pet.nature_plus)) { ind = '<tspan fill="#2ecc71">↑</tspan>'; vc = '#2ecc71'; }
                    else if (s.match.includes(pet.nature_minus)) { ind = '<tspan fill="#e74c3c">↓</tspan>'; vc = '#e74c3c'; }
                    const lc = pet[s.talent] !== 0 ? '#f39c12' : '#2c3e50';
                    return `
                        <text x="${x}" y="${y}" text-anchor="${anchor}" dominant-baseline="middle" font-size="10" font-weight="bold">
                            <tspan fill="${lc}">${s.label}</tspan>
                            <tspan fill="${vc}">${pet[s.key]}</tspan> ${ind}
                        </text>
                        <text x="${x}" y="${y + 11}" text-anchor="${anchor}" dominant-baseline="middle" font-size="8" fill="#95a5a6">(${pet[s.talent]})</text>
                    `;
                }).join('')}
            </svg>
        </div>
    `;
}

// ---- 尺子 ----
function renderRuler(label, value, min, max, divisor, unit) {
    if (!value || !min || !max) {
        const valStr = value ? (value / divisor).toFixed(2) + unit : '-';
        return `<div>${label}: ${valStr}</div>`;
    }
    const valF = (value / divisor).toFixed(2);
    const minF = (min / divisor).toFixed(2);
    const maxF = (max / divisor).toFixed(2);
    let pct = 50;
    if (max > min) { pct = ((value - min) / (max - min)) * 100; pct = Math.max(0, Math.min(100, pct)); }
    return `
        <div class="ruler-wrapper" title="当前: ${valF}${unit} | 范围: ${minF} - ${maxF}${unit}">
            <div class="ruler-label">${label}: ${valF}${unit}</div>
            <div class="ruler-container"><div class="ruler-marker" style="left:${pct}%;"></div></div>
            <div class="ruler-range"><span>${minF}</span><span>${maxF}</span></div>
        </div>
    `;
}

// ---- 获取特长名称 ----
function getTalentSkillName(id) {
    if (!id) return null;
    const ts = talentSkillMap[id];
    return ts ? ts.name : null;
}

// ---- 获取血脉名称 ----
function getBloodlineName(id) {
    const bl = bloodlineMap[id];
    return bl ? bl.blood_name || bl.name : `血脉${id}`;
}

// ---- 获取系别名称 ----
function getTypeNames(idsStr) {
    if (!idsStr) return [];
    try {
        return JSON.parse(idsStr).map(id => {
            const t = typeMap[id];
            return t ? t.short_name || t.type_name : `系别${id}`;
        });
    } catch { return []; }
}

// ---- 解析奖牌 ----
function parseMedals(medalStr) {
    if (!medalStr) return [];
    return medalStr.split('/').filter(Boolean).map(id => {
        const m = medalMap[id];
        return m ? m.name : `奖牌${id}`;
    });
}

// ---- 渲染个体值表格 ----
function renderStatsTable(pet) {
    const statConf = [
        { key: 'hp', label: 'HP', cls: 'stat-label-hp', race: 'hp_race', talent: 'hp_talent' },
        { key: 'adAttack', label: '物攻', cls: 'stat-label-atk', race: 'adAttack_race', talent: 'adAttack_talent' },
        { key: 'adDefense', label: '物防', cls: 'stat-label-def', race: 'adDefense_race', talent: 'adDefense_talent' },
        { key: 'apAttack', label: '魔攻', cls: 'stat-label-spa', race: 'apAttack_race', talent: 'apAttack_talent' },
        { key: 'apDefense', label: '魔防', cls: 'stat-label-spd', race: 'apDefense_race', talent: 'apDefense_talent' },
        { key: 'speed', label: '速度', cls: 'stat-label-spe', race: 'speed_race', talent: 'speed_talent' }
    ];
    // 性格 buff/debuff 对照：HP/物攻/物防/魔攻/魔防/速度
    const natureStats = ['HP', '物攻', '物防', '魔攻', '魔防', '速度'];
    const plusIdx = natureStats.indexOf(pet.nature_plus);
    const minusIdx = natureStats.indexOf(pet.nature_minus);

    let rows = '';
    statConf.forEach((s, i) => {
        const val = pet[s.key] || 0;
        const race = pet[s.race] || 0;
        const talent = pet[s.talent] || 0;
        let valCls = '';
        if (i === plusIdx) valCls = 'stat-buff';
        else if (i === minusIdx) valCls = 'stat-debuff';
        const talCls = talent > 0 ? 'stat-talent-positive' : 'stat-talent-zero';
        rows += `<tr>
            <td class="${s.cls}" style="text-align:left;font-weight:bold;">${s.label}</td>
            <td class="${valCls}">${val}</td>
            <td style="color:#7f8c8d;">${race}</td>
            <td class="${talCls}">${talent > 0 ? '+' + talent : talent}</td>
        </tr>`;
    });

    return `
        <table class="stats-table">
            <thead><tr>
                <th style="text-align:left;">属性</th>
                <th>当前</th>
                <th>种族</th>
                <th>天赋</th>
            </tr></thead>
            <tbody>${rows}</tbody>
        </table>
    `;
}

// ---- 渲染单张宠物卡片 ----
function createPetCard(pet) {
    const genderClass = ['', 'male', 'female'][pet.gender] || 'unknown';
    const genderLabel = ['', '♂', '♀'][pet.gender] || '';
    const genderIconClass = ['', 'gender-male', 'gender-female'][pet.gender] || '';
    const talentRankLabel = ['普通', '良好', '优秀', '极品'][pet.talent_rank - 1] || '未知';

    // 血脉
    const bloodlineId = pet.bloodline;
    const bloodlineName = bloodlineId ? getBloodlineName(bloodlineId) : null;

    // 系别
    const typeNames = getTypeNames(pet.skill_dam_type);

    // 奖牌
    const medals = parseMedals(pet.medal);

    // 捕捉球图标 URL
    const ballUrl = pet.catch_ball
        ? `https://game.gtimg.cn/images/rocom/rocodata/Ball/${pet.catch_ball}.png`
        : null;

    const escapedName = escapeHtml(pet.name);
    const escapedNatureName = escapeHtml(pet.nature_name || '未知');
    const escapedNaturePlus = escapeHtml(pet.nature_plus || '-');
    const escapedNatureMinus = escapeHtml(pet.nature_minus || '-');

    // 放生推荐状态
    const releaseInfo = releaseMap[pet.serial_num];
    let releaseBadge = '';
    let releaseClass = '';
    let releaseReasons = '';
    if (releaseInfo) {
        if (releaseInfo.is_recommended) {
            releaseBadge = `<span class="release-badge rec">❌ 建议放生</span>`;
            releaseClass = 'card-recommended';
            if (releaseInfo.reasons && releaseInfo.reasons.length > 0) {
                const reasonsText = escapeHtml(releaseInfo.reasons.join('；'));
                releaseReasons = `<div style="font-size:0.72em;color:#e74c3c;margin-top:2px;" title="${reasonsText}">${reasonsText}</div>`;
            }
        } else if (releaseInfo.is_kept) {
            releaseBadge = `<span class="release-badge kept">✅ 保留</span>`;
            releaseClass = 'card-kept';
        }
    }

    return `
        <div class="pet-card ${genderClass} ${releaseClass}">
            <!-- 头部 -->
            <div class="pet-header">
                <div class="pet-header-left">
                    ${ballUrl ? `<img class="ball-icon" src="${ballUrl}" alt="" onerror="this.style.display='none'">` : ''}
                    <span class="pet-name">${escapedName} <span class="${genderIconClass}">${genderLabel}</span></span>
                    <span class="pet-level">Lv.${pet.level}</span>
                </div>
                <span class="pet-sn">#${pet.serial_num}</span>
            </div>

            <!-- 徽章行 -->
            <div class="badge-row">
                <span class="badge badge-talent-${pet.talent_rank}">${talentRankLabel}</span>
                ${bloodlineName ? `<span class="badge badge-bloodline">🩸 ${escapeHtml(bloodlineName)}</span>` : ''}
                ${typeNames.map(t => `<span class="badge badge-type">${escapeHtml(t)}</span>`).join('')}
                ${getTalentSkillName(pet.talent_skill) ? `<span class="badge badge-talent-skill">⭐ ${escapeHtml(getTalentSkillName(pet.talent_skill))}</span>` : ''}
                ${pet.mutation ? `<span class="badge" style="background:#fce4ec;color:#c62828;display:inline-flex;align-items:center;gap:3px;"><img src="https://game.gtimg.cn/images/rocom/rocodata/MutationDiffType/${pet.mutation}.png" style="height:16px;width:auto;" onerror="this.style.display='none'"> 异色</span>` : ''}
                ${releaseBadge}
            </div>

            <!-- 雷达图 -->
            <div class="pet-content">${renderHexagon(pet)}</div>

            <!-- 个体值表格 -->
            ${renderStatsTable(pet)}

            <!-- 性格 -->
            <div style="font-size:0.78em;text-align:center;margin-bottom:6px;color:#555;">
                性格: ${escapedNatureName}
                <span style="color:#27ae60;">(+${escapedNaturePlus})</span>
                <span style="color:#e74c3c;">(-${escapedNatureMinus})</span>
            </div>

            <!-- 额外信息 -->
            <div class="extra-info">
                ${renderRuler('身高', pet.height, pet.base_height_low, pet.base_height_high, 100, 'm')}
                ${renderRuler('体重', pet.weight, pet.base_weight_low, pet.base_weight_high, 1000, 'kg')}
                <div>蛋组: ${(pet.base_egg_group_int ? escapeHtml(JSON.parse(pet.base_egg_group_int).join(', ')) : '-')}</div>
                ${medals.length ? `<div title="${escapeHtml(pet.medal)}">🏅 ${escapeHtml(medals.join(', ').substring(0, 20))}${medals.join(', ').length > 20 ? '…' : ''}</div>` : '<div>🏅 -</div>'}
            </div>

            <!-- 放生原因 -->
            ${releaseReasons}

            <!-- 天赋评级 -->
            <div class="talent-rank rank-${pet.talent_rank}">天赋评级: ${talentRankLabel}</div>

            <!-- 性别设置 + 品种配置 -->
            <div class="gender-setter">
                <button onclick="setGender(${pet.serial_num}, 1)">设为♂</button>
                <button onclick="setGender(${pet.serial_num}, 2)">设为♀</button>
                <button onclick="openSpeciesConfig(${pet.base_id}, '${escapeHtml(pet.base_name || pet.name)}')" style="margin-left:6px;padding:4px 8px;background:#f39c12;color:white;border:none;border-radius:3px;cursor:pointer;font-size:0.78em;">⚙️</button>
            </div>
        </div>
    `;
}

function renderPets(pets) {
    petListEl.innerHTML = '';
    pets.forEach(pet => {
        const card = document.createElement('div');
        card.innerHTML = createPetCard(pet);
        petListEl.appendChild(card.firstElementChild);
    });
}

async function setGender(sn, gender) {
    await fetch('/api/update_gender', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({serial_num: sn, gender: gender})
    });
    fetchPets();
}

function updatePagination(total) {
    const totalPages = Math.ceil(total / pageSize);
    pageInfo.innerText = `第 ${currentPage} / ${totalPages || 1} 页 (共 ${total} 条)`;
    prevBtn.disabled = currentPage <= 1;
    nextBtn.disabled = currentPage >= totalPages;
}

searchBtn.addEventListener('click', () => { currentPage = 1; fetchPets(); });
prevBtn.addEventListener('click', () => { if (currentPage > 1) { currentPage--; fetchPets(); } });
nextBtn.addEventListener('click', () => { currentPage++; fetchPets(); });

// ---- 同步逻辑 (不变) ----
const syncBtn = document.getElementById('syncBtn');
const syncProgress = document.getElementById('syncProgress');
const syncProgressBar = document.getElementById('syncProgressBar');
const syncProgressText = document.getElementById('syncProgressText');
const syncLog = document.getElementById('syncLog');
async function checkSyncStatus() {
    // 不再需要冷却，仅保留兼容
}

syncBtn.addEventListener('click', async () => {
    syncBtn.disabled = true;
    syncBtn.style.background = '#95a5a6';
    syncBtn.textContent = '同步中...';
    syncProgress.style.display = 'block';
    syncLog.innerHTML = '';
    syncProgressBar.style.width = '0%';
    syncProgressText.textContent = '0%';
    try {
        const response = await fetch('/api/sync', { method: 'POST' });
        if (!response.ok) {
            const err = await response.json();
            addSyncLog(`❌ ${err.detail?.message || err.detail || '同步失败'}`);
            resetSyncBtn();
            return;
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try { handleSyncEvent(JSON.parse(line.slice(6))); } catch (e) { /* ignore */ }
                }
            }
        }
    } catch (error) { addSyncLog(`❌ 网络错误: ${error.message}`); }
    resetSyncBtn();
});

function handleSyncEvent(data) {
    if (data.error) { addSyncLog(`❌ 错误: ${data.error}`); return; }
    if (data.done) {
        syncProgressBar.style.width = '100%';
        syncProgressText.textContent = '100%';
        const r = data.result || {};
        addSyncLog(`✅ 同步完成！新增 ${r.new || 0} 只，更新 ${r.updated || 0} 只，共 ${r.total || 0} 只`);
        fetchPets();
        fetchRefreshTime();
        // 同步后检测家园生蛋配置
        checkBreedingAfterSync();
        return;
    }
    const { message, current, total } = data;
    addSyncLog(message);
    if (total > 0) {
        const pct = Math.round((current / total) * 100);
        syncProgressBar.style.width = `${pct}%`;
        syncProgressText.textContent = `${pct}% (${current}/${total})`;
    }
}

function addSyncLog(text) {
    const line = document.createElement('div');
    line.textContent = text;
    line.style.padding = '1px 0';
    syncLog.appendChild(line);
    syncLog.scrollTop = syncLog.scrollHeight;
}

function resetSyncBtn() {
    syncBtn.disabled = false;
    syncBtn.style.background = '#27ae60';
    syncBtn.textContent = '同步精灵';
}

// ---- 性别同步 ----
const syncGenderBtn = document.getElementById('syncGenderBtn');
const syncGenderProgress = document.getElementById('syncGenderProgress');
const syncGenderProgressBar = document.getElementById('syncGenderProgressBar');
const syncGenderProgressText = document.getElementById('syncGenderProgressText');
const syncGenderLog = document.getElementById('syncGenderLog');

syncGenderBtn.addEventListener('click', async () => {
    syncGenderBtn.disabled = true;
    syncGenderBtn.style.background = '#95a5a6';
    syncGenderBtn.textContent = '同步中...';
    syncGenderProgress.style.display = 'block';
    syncGenderLog.innerHTML = '';
    syncGenderProgressBar.style.width = '0%';
    syncGenderProgressText.textContent = '0%';
    try {
        const response = await fetch('/api/sync_gender_export', { method: 'POST' });
        if (!response.ok) {
            const err = await response.json();
            addGenderSyncLog(`❌ ${err.detail || '同步失败'}`);
            resetGenderSyncBtn();
            return;
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try { handleGenderSyncEvent(JSON.parse(line.slice(6))); } catch (e) { /* ignore */ }
                }
            }
        }
    } catch (error) { addGenderSyncLog(`❌ 网络错误: ${error.message}`); }
    resetGenderSyncBtn();
});

function handleGenderSyncEvent(data) {
    if (data.error) { addGenderSyncLog(`❌ 错误: ${data.error}`); return; }
    if (data.done) {
        syncGenderProgressBar.style.width = '100%';
        syncGenderProgressText.textContent = '100%';
        const r = data.result || {};
        addGenderSyncLog(`✅ 性别同步完成！更新 ${r.updated || 0} 条，匹配 ${r.matched || 0} 条`);
        fetchPets();
        return;
    }
    const { message, current, total } = data;
    addGenderSyncLog(message);
    if (total > 0) {
        const pct = Math.round((current / total) * 100);
        syncGenderProgressBar.style.width = `${pct}%`;
        syncGenderProgressText.textContent = `${pct}% (${current}/${total})`;
    }
}

function addGenderSyncLog(text) {
    const line = document.createElement('div');
    line.textContent = text;
    line.style.padding = '1px 0';
    syncGenderLog.appendChild(line);
    syncGenderLog.scrollTop = syncGenderLog.scrollHeight;
}

function resetGenderSyncBtn() {
    syncGenderBtn.disabled = false;
    syncGenderBtn.style.background = '#8e44ad';
    syncGenderBtn.textContent = '同步性别';
}

// ---- 家园生蛋同步检测 ----
async function checkBreedingAfterSync() {
    try {
        const res = await fetch('/api/breeding_slots');
        const slots = await res.json();
        const configured = slots.filter(s => s.target_base_id && s.father && s.mother);
        if (configured.length === 0) return;

        addSyncLog('🔍 正在检测家园生蛋推荐...');
        const checkRes = await fetch('/api/check_breeding_slots');
        const results = await checkRes.json();
        const changed = results.filter(r => r.changed);
        if (changed.length > 0) {
            changed.forEach(r => {
                addSyncLog(`📌 第 ${r.slot_id} 组「${r.target_name}」有更优推荐: ${r.best_father_name} × ${r.best_mother_name}`);
            });
            addSyncLog(`💡 共 ${changed.length} 组需要更新，前往繁育中心查看`);
        } else {
            const hasAny = results.filter(r => r.has_match).length;
            if (hasAny > 0) addSyncLog('✅ 家园生蛋配置已是最优');
        }
    } catch (e) {
        // 忽略（可能 breeding_slots 表不存在或未同步）
    }
}

// ---- 品种配置弹窗 ----
function getSpeciesConfig(baseId) {
    // 从 speciesPrefsList 中查找配置
    const group = speciesPrefsList.find(g => g.base_id == baseId);
    return group ? group.config : null;
}

function openSpeciesConfig(baseId, speciesName) {
    currentConfigBaseId = baseId;
    document.getElementById('speciesConfigTitle').textContent = `配置 - ${speciesName}`;
    document.getElementById('speciesKeepCount').value = 3;

    const select = document.getElementById('speciesNatureSelect');
    select.innerHTML = '';
    for (let i = 1; i <= 30; i++) {
        const opt = document.createElement('option');
        opt.value = i;
        opt.textContent = getNatureName(i);
        select.appendChild(opt);
    }

    const config = getSpeciesConfig(baseId);
    if (config) {
        const ids = config.preferred_nature_ids || [];
        for (const opt of select.options) {
            opt.selected = ids.includes(parseInt(opt.value));
        }
        document.getElementById('speciesKeepCount').value = config.keep_count || 3;
    }

    document.getElementById('speciesConfigModal').style.display = 'flex';
}

function closeSpeciesConfigModal() {
    document.getElementById('speciesConfigModal').style.display = 'none';
    currentConfigBaseId = null;
}

async function saveSpeciesConfig() {
    if (!currentConfigBaseId) return;
    const select = document.getElementById('speciesNatureSelect');
    const natureIds = Array.from(select.selectedOptions).map(o => parseInt(o.value));
    const keepCount = parseInt(document.getElementById('speciesKeepCount').value) || 3;

    try {
        const res = await fetch('/api/species_preferences', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                preferences: [{
                    base_id: currentConfigBaseId,
                    preferred_nature_ids: natureIds,
                    keep_count: keepCount
                }]
            })
        });
        if (res.ok) {
            closeSpeciesConfigModal();
            await fetchReleaseData();  // 刷新推荐数据
            fetchPets();              // 刷新卡片显示
        } else {
            alert('保存失败');
        }
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

// ---- 初始化 ----
async function init() {
    await fetchConfigs();
    await fetchReleaseData();
    fetchPets();
    fetchRefreshTime();
}
window.setGender = setGender;
window.openSpeciesConfig = openSpeciesConfig;

// ---- 品种配置弹窗事件绑定 ----
document.getElementById('configSpeciesBtn').addEventListener('click', () => {
    // 打开全局配置页面
    window.location.href = 'release.html';
});
document.getElementById('closeSpeciesModalBtn').addEventListener('click', closeSpeciesConfigModal);
document.getElementById('cancelSpeciesConfigBtn').addEventListener('click', closeSpeciesConfigModal);
document.getElementById('saveSpeciesConfigBtn').addEventListener('click', saveSpeciesConfig);
document.getElementById('speciesConfigModal').addEventListener('click', function(e) {
    if (e.target === this) closeSpeciesConfigModal();
});

init();
