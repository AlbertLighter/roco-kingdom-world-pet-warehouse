// Shared helpers (duplicated from app.js for standalone breeding.html)
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

let bloodlineMap = {};
let typeMap = {};
let medalMap = {};

async function fetchConfigs() {
    try {
        const [blRes, tpRes, mdRes] = await Promise.all([
            fetch('/api/config/bloodlines'),
            fetch('/api/config/types'),
            fetch('/api/config/medals')
        ]);
        bloodlineMap = await blRes.json();
        typeMap = await tpRes.json();
        medalMap = await mdRes.json();
    } catch (e) { /* ignore */ }
}

function getBloodlineName(id) {
    const bl = bloodlineMap[id];
    return bl ? bl.blood_name || bl.name : null;
}

function getTypeNames(idsStr) {
    if (!idsStr) return [];
    try { return JSON.parse(idsStr).map(id => { const t = typeMap[id]; return t ? t.short_name || t.type_name : null; }).filter(Boolean); }
    catch { return []; }
}

function parseMedals(medalStr) {
    if (!medalStr) return [];
    return medalStr.split('/').filter(Boolean).map(id => { const m = medalMap[id]; return m ? m.name : null; }).filter(Boolean);
}

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

function renderRuler(label, value, min, max, divisor, unit) {
    if (!value || !min || !max) { const valStr = value ? (value / divisor).toFixed(2) + unit : '-'; return `<div>${label}: ${valStr}</div>`; }
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

function renderStatsTable(pet) {
    const statConf = [
        { key: 'hp', label: 'HP', cls: 'stat-label-hp', race: 'hp_race', talent: 'hp_talent' },
        { key: 'adAttack', label: '物攻', cls: 'stat-label-atk', race: 'adAttack_race', talent: 'adAttack_talent' },
        { key: 'adDefense', label: '物防', cls: 'stat-label-def', race: 'adDefense_race', talent: 'adDefense_talent' },
        { key: 'apAttack', label: '魔攻', cls: 'stat-label-spa', race: 'apAttack_race', talent: 'apAttack_talent' },
        { key: 'apDefense', label: '魔防', cls: 'stat-label-spd', race: 'apDefense_race', talent: 'apDefense_talent' },
        { key: 'speed', label: '速度', cls: 'stat-label-spe', race: 'speed_race', talent: 'speed_talent' }
    ];
    const natureStats = ['HP', '物攻', '物防', '魔攻', '魔防', '速度'];
    const plusIdx = natureStats.indexOf(pet.nature_plus);
    const minusIdx = natureStats.indexOf(pet.nature_minus);
    let rows = '';
    statConf.forEach((s, i) => {
        const val = pet[s.key] || 0;
        const race = pet[s.race] || 0;
        const talent = pet[s.talent] || 0;
        let vc = '';
        if (i === plusIdx) vc = 'stat-buff';
        else if (i === minusIdx) vc = 'stat-debuff';
        const tc = talent > 0 ? 'stat-talent-positive' : 'stat-talent-zero';
        rows += `<tr><td class="${s.cls}" style="text-align:left;font-weight:bold;">${s.label}</td><td class="${vc}">${val}</td><td style="color:#7f8c8d;">${race}</td><td class="${tc}">${talent > 0 ? '+' + talent : talent}</td></tr>`;
    });
    return `<table class="stats-table"><thead><tr><th style="text-align:left;">属性</th><th>当前</th><th>种族</th><th>天赋</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function createPetCard(pet) {
    const genderClass = ['', 'male', 'female'][pet.gender] || 'unknown';
    const genderLabel = ['', '♂', '♀'][pet.gender] || '';
    const genderIconClass = ['', 'gender-male', 'gender-female'][pet.gender] || '';
    const talentRankLabel = ['普通', '良好', '优秀', '极品'][pet.talent_rank - 1] || '未知';
    const bloodlineName = pet.bloodline ? getBloodlineName(pet.bloodline) : null;
    const typeNames = getTypeNames(pet.skill_dam_type);
    const medals = parseMedals(pet.medal);
    const ballUrl = pet.catch_ball ? `https://game.gtimg.cn/images/rocom/rocodata/Ball/${pet.catch_ball}.png` : null;
    const escapedName = escapeHtml(pet.name);
    const escapedNatureName = escapeHtml(pet.nature_name || '未知');
    const escapedNaturePlus = escapeHtml(pet.nature_plus || '-');
    const escapedNatureMinus = escapeHtml(pet.nature_minus || '-');
    const eggStr = pet.base_egg_group_int ? escapeHtml(JSON.parse(pet.base_egg_group_int).join(', ')) : '-';
    const medalStr = medals.length ? escapeHtml(medals.join(', ').substring(0, 20)) + (medals.join(', ').length > 20 ? '…' : '') : '-';

    return `
        <div class="pet-card ${genderClass}">
            <div class="pet-header">
                <div class="pet-header-left">
                    ${ballUrl ? `<img class="ball-icon" src="${ballUrl}" alt="" onerror="this.style.display='none'">` : ''}
                    <span class="pet-name">${escapedName} <span class="${genderIconClass}">${genderLabel}</span></span>
                    <span class="pet-level">Lv.${pet.level}</span>
                </div>
                <span class="pet-sn">#${pet.serial_num}</span>
            </div>
            <div class="badge-row">
                <span class="badge badge-talent-${pet.talent_rank}">${talentRankLabel}</span>
                ${bloodlineName ? `<span class="badge badge-bloodline">🩸 ${escapeHtml(bloodlineName)}</span>` : ''}
                ${typeNames.map(t => `<span class="badge badge-type">${escapeHtml(t)}</span>`).join('')}
                ${pet.mutation ? `<span class="badge" style="background:#fce4ec;color:#c62828;display:inline-flex;align-items:center;gap:3px;"><img src="https://game.gtimg.cn/images/rocom/rocodata/MutationDiffType/${pet.mutation}.png" style="height:16px;width:auto;" onerror="this.style.display='none'"> 异色</span>` : ''}
            </div>
            <div class="pet-content">${renderHexagon(pet)}</div>
            ${renderStatsTable(pet)}
            <div style="font-size:0.78em;text-align:center;margin-bottom:6px;color:#555;">
                性格: ${escapedNatureName}
                <span style="color:#27ae60;">(+${escapedNaturePlus})</span>
                <span style="color:#e74c3c;">(-${escapedNatureMinus})</span>
            </div>
            <div class="extra-info">
                ${renderRuler('身高', pet.height, pet.base_height_low, pet.base_height_high, 100, 'm')}
                ${renderRuler('体重', pet.weight, pet.base_weight_low, pet.base_weight_high, 1000, 'kg')}
                <div>蛋组: ${eggStr}</div>
                <div title="${escapeHtml(pet.medal || '')}">🏅 ${medalStr}</div>
            </div>
            <div class="talent-rank rank-${pet.talent_rank}">天赋评级: ${talentRankLabel}</div>
            <div class="gender-setter">
                <button onclick="setGender(${pet.serial_num}, 1)">设为♂</button>
                <button onclick="setGender(${pet.serial_num}, 2)">设为♀</button>
            </div>
        </div>
    `;
}

// ---- 育种逻辑 (保持不变) ----
const targetPetSelect = document.getElementById('targetPetSelect');
const targetSearch = document.getElementById('targetSearch');
const natureSelect = document.getElementById('natureSelect');
const talentChecks = document.querySelectorAll('#talentChecks input');
const useKingBall = document.getElementById('useKingBall');
const kingBallAttr = document.getElementById('kingBallAttr');
const breedBigSize = document.getElementById('breedBigSize');
const recommendBtn = document.getElementById('recommendBtn');
const recommendationResults = document.getElementById('recommendationResults');
const STORAGE_KEY = 'breeding_config';
const HISTORY_KEY = 'breeding_history';
let allBasePets = [];

function renderTargetOptions(filterText = '') {
    const currentValue = targetPetSelect.value;
    targetPetSelect.innerHTML = '<option value="">选择目标精灵...</option>';
    const filtered = allBasePets.filter(p => p.name.toLowerCase().includes(filterText.toLowerCase()));
    filtered.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.objId;
        opt.textContent = p.name;
        targetPetSelect.appendChild(opt);
    });
    targetPetSelect.value = currentValue;
}

targetSearch.addEventListener('input', (e) => renderTargetOptions(e.target.value));

function getCurrentConfig() {
    return {
        targetPetId: targetPetSelect.value,
        targetPetName: targetPetSelect.options[targetPetSelect.selectedIndex]?.text || '',
        natureId: natureSelect.value,
        natureName: natureSelect.options[natureSelect.selectedIndex]?.text || '无',
        talents: Array.from(talentChecks).filter(i => i.checked).map(i => i.value),
        useKingBall: useKingBall.checked,
        kingBallAttr: kingBallAttr.value,
        breedBigSize: breedBigSize.checked
    };
}

function saveConfig() { localStorage.setItem(STORAGE_KEY, JSON.stringify(getCurrentConfig())); }

function saveToHistory() {
    const config = getCurrentConfig();
    if (!config.targetPetId) return;
    let history;
    try { history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); if (!Array.isArray(history)) history = []; } catch (e) { history = []; }
    history = history.filter(h => {
        const hTalents = (h.talents || []).sort().join(',');
        const cTalents = (config.talents || []).sort().join(',');
        return !(h.targetPetId === config.targetPetId && h.natureId === config.natureId && hTalents === cTalents && h.useKingBall === config.useKingBall && h.kingBallAttr === config.kingBallAttr);
    });
    history.unshift(config);
    history = history.slice(0, 20);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    const historyList = document.getElementById('historyList');
    let history;
    try { history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); if (!Array.isArray(history)) history = []; } catch (e) { history = []; }
    historyList.innerHTML = '';
    history.forEach((h, index) => {
        const item = document.createElement('div');
        item.style.cssText = 'padding:10px;background:#f8f9fa;border:1px solid #e9ecef;border-radius:6px;font-size:0.85em;cursor:pointer;position:relative;transition:all 0.2s;';
        const talentLabels = { hp: '血', adAttack: '攻', apAttack: '魔', adDefense: '防', apDefense: '抗', speed: '速' };
        const talentStr = h.talents.map(t => talentLabels[t]).join('/');
        item.innerHTML = `
            <div class="history-apply" style="margin-right:20px;">
                <div style="font-weight:bold;color:#2c3e50;">${h.targetPetName}</div>
                <div style="color:#7f8c8d;margin-top:2px;">性格: ${h.natureName} | 天赋: ${talentStr || '无'}${h.useKingBall ? `<br><span style="color:#e67e22;">[国王球: ${talentLabels[h.kingBallAttr]}]</span>` : ''}</div>
            </div>
            <button class="delete-history" data-index="${index}" style="position:absolute;top:5px;right:5px;background:none;border:none;color:#e74c3c;cursor:pointer;padding:2px 5px;font-weight:bold;">×</button>
        `;
        item.querySelector('.history-apply').addEventListener('click', () => applyConfig(h));
        item.querySelector('.delete-history').addEventListener('click', (e) => { e.stopPropagation(); deleteHistory(index); });
        item.addEventListener('mouseenter', () => item.style.backgroundColor = '#e9ecef');
        item.addEventListener('mouseleave', () => item.style.backgroundColor = '#f8f9fa');
        historyList.appendChild(item);
    });
}

function deleteHistory(index) {
    let history;
    try { history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); if (!Array.isArray(history)) history = []; } catch (e) { history = []; }
    history.splice(index, 1);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    renderHistory();
}

function applyConfig(config) {
    targetPetSelect.value = config.targetPetId;
    natureSelect.value = config.natureId;
    talentChecks.forEach(check => { check.checked = (config.talents || []).includes(check.value); });
    useKingBall.checked = config.useKingBall;
    kingBallAttr.value = config.kingBallAttr;
    if (breedBigSize) breedBigSize.checked = config.breedBigSize || false;
    saveConfig();
}

function loadConfig() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    try { applyConfig(JSON.parse(saved)); } catch (e) { console.error('Failed to load breeding config', e); }
}

async function init() {
    await fetchConfigs();
    const resBase = await fetch('/api/base_pets');
    allBasePets = await resBase.json();
    renderTargetOptions();
    const natures = "大胆,固执,调皮,勇敢,逞强,稳重,天真,懒散,悠闲,坦率,聪明,专注,偏执,冷静,理性,警惕,温顺,害羞,慎重,焦虑,胆小,急躁,开朗,莽撞,热情,沉默,忧郁,平和,粗心,踏实".split(',');
    natureSelect.innerHTML = '<option value="">选择期望性格...</option>';
    natures.forEach((name, i) => {
        const opt = document.createElement('option');
        opt.value = i + 1;
        opt.textContent = name;
        natureSelect.appendChild(opt);
    });
    loadConfig();
    renderHistory();
    [targetPetSelect, natureSelect, useKingBall, kingBallAttr, breedBigSize].forEach(el => { if (el) el.addEventListener('change', saveConfig); });
    talentChecks.forEach(el => el.addEventListener('change', saveConfig));
    document.getElementById('clearHistoryBtn').addEventListener('click', () => { if (confirm('确定要清空所有历史配置吗？')) { localStorage.removeItem(HISTORY_KEY); renderHistory(); } });
}

function setGender(sn, gender) {
    fetch('/api/update_gender', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({serial_num: sn, gender: gender})
    }).then(r => {
        if (r.ok) location.reload();
    }).catch(e => console.error(e));
}

// ---- Exports ----
window.setGender = setGender;
window.createPetCard = createPetCard;

recommendBtn.addEventListener('click', async () => {
    const config = getCurrentConfig();
    if (!config.targetPetId) return alert('请选择目标精灵');
    saveToHistory();
    recommendationResults.innerHTML = '<div style="text-align:center;margin-top:100px;">正在匹配最佳父母...</div>';
    const res = await fetch('/api/recommend_parents', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            target_base_id: parseInt(config.targetPetId),
            desired_nature_id: config.natureId ? parseInt(config.natureId) : null,
            desired_stats: config.talents,
            use_king_ball: config.useKingBall,
            king_ball_attr: config.kingBallAttr,
            breed_big_size: config.breedBigSize
        })
    });
    const data = await res.json();
    // 获取已占用的精灵集合
    let occupiedSerials = new Set();
    try {
        const slotsRes = await fetch('/api/breeding_slots');
        const slots = await slotsRes.json();
        slots.forEach(s => {
            if (s.father) occupiedSerials.add(s.father.serial_num);
            if (s.mother) occupiedSerials.add(s.mother.serial_num);
        });
    } catch (e) { /* 忽略 */ }
    renderRecommendations(data, occupiedSerials);
});

function renderRecommendations(data, occupiedSerials) {
    recommendationResults.innerHTML = '';
    if (data.length === 0) {
        recommendationResults.innerHTML = '<div style="text-align:center;color:#e74c3c;margin-top:100px;"><h2>未找到合适的父母组合</h2><p>建议：请确保您已经在仓库主列表中设置了精灵的性别，或者尝试减少期望天赋要求。</p></div>';
        return;
    }
    data.forEach((rec, i) => {
        const fatherOccupied = occupiedSerials && occupiedSerials.has(rec.father.serial_num);
        const motherOccupied = occupiedSerials && occupiedSerials.has(rec.mother.serial_num);
        const anyOccupied = fatherOccupied || motherOccupied;
        const pairDiv = document.createElement('div');
        pairDiv.className = 'recommendation-pair';

        // 在 createPetCard 生成的 HTML 中注入占用标记
        function markOccupied(cardHtml, side) {
            const badge = side === 'father' && fatherOccupied ? '<span style="position:absolute;top:5px;right:5px;background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:0.75em;font-weight:bold;z-index:1;">已占用</span>' :
                         side === 'mother' && motherOccupied ? '<span style="position:absolute;top:5px;right:5px;background:#e74c3c;color:#fff;padding:2px 8px;border-radius:3px;font-size:0.75em;font-weight:bold;z-index:1;">已占用</span>' : '';
            if (badge) {
                const idx = cardHtml.indexOf('>', cardHtml.indexOf('<div class="pet-card'));
                return cardHtml.slice(0, idx + 1) + badge + cardHtml.slice(idx + 1);
            }
            return cardHtml;
        }

        pairDiv.innerHTML = `
            <div class="pair-info">
                <span>推荐方案 #${i+1}</span>
                <div style="text-align:right;">
                    <div style="color:#27ae60;">综合评分: ${rec.score}</div>
                    ${rec.size_score ? `<div style="color:#d35400;font-size:0.8em;">体型评分: ${rec.size_score}</div>` : ''}
                    <div style="color:#7f8c8d;font-size:0.8em;">继承成功率: ${(rec.probability * 100).toFixed(2)}%</div>
                </div>
            </div>
            <div class="pet-card-wrapper" style="position:relative;"><h4>母方 (决定种族)</h4>${markOccupied(createPetCard(rec.mother), 'mother')}</div>
            <div class="pet-card-wrapper" style="position:relative;"><h4>父方</h4>${markOccupied(createPetCard(rec.father), 'father')}</div>
            <div style="width:100%;text-align:right;margin-top:10px;">
                <button class="add-slot-btn" data-father="${rec.father.serial_num}" data-mother="${rec.mother.serial_num}" style="padding:8px 20px;background:${anyOccupied ? '#95a5a6' : '#8e44ad'};color:#fff;border:none;border-radius:4px;cursor:${anyOccupied ? 'not-allowed' : 'pointer'};font-weight:bold;font-size:0.9em;" ${anyOccupied ? 'disabled' : ''}>
                    ${anyOccupied ? '已占用' : '＋ 加入家园生蛋配置'}
                </button>
            </div>
        `;

        if (!anyOccupied) {
            pairDiv.querySelector('.add-slot-btn').addEventListener('click', async (e) => {
                const btn = e.currentTarget;
                const config = getCurrentConfig();
                const targetId = parseInt(config.targetPetId);
                if (!targetId) { btn.textContent = '✗ 请先选择目标精灵'; return; }
                btn.disabled = true;
                btn.textContent = '加入中...';
                try {
                    const res = await fetch('/api/breeding_slots/add', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            target_base_id: targetId,
                            father_serial: parseInt(btn.dataset.father),
                            mother_serial: parseInt(btn.dataset.mother)
                        })
                    });
                    if (res.ok) {
                        const data = await res.json();
                        btn.textContent = `\u2713 已加入第 ${data.slot_id} 组`;
                        btn.style.background = '#27ae60';
                        await loadBreedingSlots();
                    } else {
                        const err = await res.json();
                        btn.textContent = '\u2717 ' + (err.detail || '失败');
                        btn.disabled = false;
                        btn.style.background = '#e74c3c';
                        setTimeout(() => { btn.textContent = '\uff0b 加入家园生蛋配置'; btn.style.background = '#8e44ad'; btn.disabled = false; }, 2000);
                    }
                } catch (e) {
                    btn.textContent = '\u2717 网络错误';
                    btn.disabled = false;
                    btn.style.background = '#e74c3c';
                }
            });
        }
        recommendationResults.appendChild(pairDiv);
    });
}

// ---- 家园生蛋配置 ----
let breedingSlots = [];       // 当前槽位配置 [{slot_id, target_base_id, target_name, father, mother}]

const saveSlotsBtn = document.getElementById('saveSlotsBtn');
const checkSlotsBtn = document.getElementById('checkSlotsBtn');
const slotsStatus = document.getElementById('slotsStatus');

function renderSlots() {
    const container = document.getElementById('slotsContainer');
    container.innerHTML = '';

    breedingSlots.forEach(slot => {
        const item = document.createElement('div');
        item.className = 'slot-list-item';

        if (!slot.target_base_id) {
            item.classList.add('empty');
            item.innerHTML = `<div class="slot-title">第 ${slot.slot_id} 组</div><div class="slot-detail" style="color:#bdc3c7;">空 — 前往推荐方案点击「加入家园生蛋配置」</div>`;
            container.appendChild(item);
            return;
        }

        const statusId = `slotStatus_${slot.slot_id}`;
        const genderMark = (g) => ['', '♂', '♀'][g] || '';
        const fatherStr = slot.father ? `#${slot.father.serial_num} ${slot.father.name} ${genderMark(slot.father.gender)}` : '-';
        const motherStr = slot.mother ? `#${slot.mother.serial_num} ${slot.mother.name} ${genderMark(slot.mother.gender)}` : '-';

        item.innerHTML = `
            <div class="slot-title">第 ${slot.slot_id} 组 — ${slot.target_name || '未知目标'}</div>
            <div class="slot-detail">
                <span>父: ${fatherStr}</span>
                <span>母: ${motherStr}</span>
            </div>
            <div class="slot-status"><span id="${statusId}"></span></div>
            <button class="delete-slot-btn" data-slot="${slot.slot_id}" title="清空此槽位">×</button>
        `;

        item.querySelector('.delete-slot-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            const sid = parseInt(e.currentTarget.dataset.slot);
            try {
                await fetch(`/api/breeding_slots/${sid}`, { method: 'DELETE' });
                await loadBreedingSlots();
            } catch (err) {
                slotsStatus.textContent = '删除失败';
            }
        });

        // 点击非空槽位应用到繁育配置
        item.addEventListener('click', (e) => {
            if (e.target.closest('.delete-slot-btn')) return;
            targetPetSelect.value = slot.target_base_id;
            saveConfig();
            slotsStatus.textContent = `已应用第 ${slot.slot_id} 组到繁育参数`;
            setTimeout(() => { slotsStatus.textContent = ''; }, 2000);
        });

        container.appendChild(item);
    });
}

async function loadBreedingSlots() {
    try {
        const slotsRes = await fetch('/api/breeding_slots');
        breedingSlots = await slotsRes.json();
        renderSlots();
    } catch (e) {
        slotsStatus.textContent = '加载生蛋配置失败';
    }
}

async function saveBreedingSlots() {
    const payload = breedingSlots.map(slot => ({
        slot_id: slot.slot_id,
        target_base_id: slot.target_base_id,
        father_serial: slot.father ? slot.father.serial_num : null,
        mother_serial: slot.mother ? slot.mother.serial_num : null,
    }));
    // 检查10个精灵不重复
    const used = new Set();
    for (const p of payload) {
        if (p.father_serial) {
            if (used.has(p.father_serial)) { slotsStatus.textContent = `精灵 #${p.father_serial} 重复使用`; return; }
            used.add(p.father_serial);
        }
        if (p.mother_serial) {
            if (used.has(p.mother_serial)) { slotsStatus.textContent = `精灵 #${p.mother_serial} 重复使用`; return; }
            used.add(p.mother_serial);
        }
    }
    try {
        slotsStatus.textContent = '保存中...';
        const res = await fetch('/api/breeding_slots', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        if (!res.ok) {
            const err = await res.json();
            slotsStatus.textContent = '保存失败: ' + (err.detail || JSON.stringify(err));
            return;
        }
        slotsStatus.textContent = '生蛋配置已保存 ✓';
        await loadBreedingSlots();  // 刷新
    } catch (e) {
        slotsStatus.textContent = '保存失败';
    }
}

async function checkSlotsUpdate() {
    slotsStatus.textContent = '检测中...';
    try {
        const res = await fetch('/api/check_breeding_slots');
        const results = await res.json();
        let changedCount = 0;
        results.forEach(r => {
            const statusEl = document.getElementById('slotStatus_' + r.slot_id);
            if (!statusEl) return;
            if (!r.has_match) {
                statusEl.className = '';
                statusEl.textContent = '⚠ 无匹配';
                return;
            }
            if (r.changed) {
                statusEl.className = 'slot-changed';
                statusEl.textContent = `↻ 推荐更新: ${r.best_father_name} × ${r.best_mother_name}`;
                changedCount++;
            } else {
                statusEl.className = 'slot-ok';
                statusEl.textContent = '✓ 当前最优';
            }
        });
        if (changedCount > 0) {
            slotsStatus.textContent = `检测完成，${changedCount} 组有更优推荐`;
        } else {
            slotsStatus.textContent = '检测完成，所有配置已是最优 ✓';
        }
    } catch (e) {
        slotsStatus.textContent = '检测失败';
    }
}

// 暴露给 app.js（同步完成后调用）
window.checkBreedingSlots = checkSlotsUpdate;

saveSlotsBtn.addEventListener('click', saveBreedingSlots);
checkSlotsBtn.addEventListener('click', checkSlotsUpdate);

// 在 init 完成后加载生蛋配置
const _origInit = init;
init = async function() {
    await _origInit();
    await loadBreedingSlots();
};
init();
