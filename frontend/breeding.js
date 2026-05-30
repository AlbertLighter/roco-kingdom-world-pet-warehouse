// Shared rendering logic from app.js
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
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
    
    const size = 220;
    const cx = size / 2;
    const cy = size / 2;
    const r_max = 60;
    const stat_max = 400; 

    const points = stats.map((stat, i) => {
        const angle = (i * 60 - 90) * (Math.PI / 180);
        const val = Math.min(pet[stat.key], stat_max);
        const r = (val / stat_max) * r_max;
        const x = cx + r * Math.cos(angle);
        const y = cy + r * Math.sin(angle);
        return `${x},${y}`;
    }).join(' ');

    const bg_points_100 = stats.map((_, i) => {
        const angle = (i * 60 - 90) * (Math.PI / 180);
        const x = cx + r_max * Math.cos(angle);
        const y = cy + r_max * Math.sin(angle);
        return `${x},${y}`;
    }).join(' ');

    const bg_points_50 = stats.map((_, i) => {
        const angle = (i * 60 - 90) * (Math.PI / 180);
        const x = cx + (r_max * 0.5) * Math.cos(angle);
        const y = cy + (r_max * 0.5) * Math.sin(angle);
        return `${x},${y}`;
    }).join(' ');

    return `
        <div class="hexagon-container">
            <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
                <polygon points="${bg_points_100}" fill="none" stroke="#ccc" stroke-width="1" />
                <polygon points="${bg_points_50}" fill="none" stroke="#ccc" stroke-width="1" />
                ${stats.map((_, i) => {
                    const angle = (i * 60 - 90) * (Math.PI / 180);
                    const x2 = cx + r_max * Math.cos(angle);
                    const y2 = cy + r_max * Math.sin(angle);
                    return `<line x1="${cx}" y1="${cy}" x2="${x2}" y2="${y2}" stroke="#ccc" stroke-width="1" />`;
                }).join('')}
                <polygon points="${points}" fill="rgba(52, 152, 219, 0.4)" stroke="#3498db" stroke-width="2" />
                ${stats.map((stat, i) => {
                    const angle = (i * 60 - 90) * (Math.PI / 180);
                    const x = cx + (r_max + 12) * Math.cos(angle);
                    const y = cy + (r_max + 12) * Math.sin(angle);
                    const textAnchor = Math.abs(x - cx) < 10 ? 'middle' : (x > cx ? 'start' : 'end');
                    
                    let indicator = '';
                    let valueColor = '#2c3e50';
                    if (stat.match.includes(pet.nature_plus)) {
                        indicator = '<tspan fill="#2ecc71">↑</tspan>';
                        valueColor = '#2ecc71';
                    } else if (stat.match.includes(pet.nature_minus)) {
                        indicator = '<tspan fill="#e74c3c">↓</tspan>';
                        valueColor = '#e74c3c';
                    }

                    const labelColor = pet[stat.talent] !== 0 ? '#f39c12' : '#2c3e50';

                    return `
                        <text x="${x}" y="${y}" text-anchor="${textAnchor}" dominant-baseline="middle" font-size="11" font-weight="bold">
                            <tspan fill="${labelColor}">${stat.label}</tspan> 
                            <tspan fill="${valueColor}">${pet[stat.key]}</tspan> 
                            ${indicator}
                        </text>
                        <text x="${x}" y="${y + 12}" text-anchor="${textAnchor}" dominant-baseline="middle" font-size="9" fill="#95a5a6">
                            (${pet[stat.talent]})
                        </text>
                    `;
                }).join('')}
            </svg>
        </div>
    `;
}

function renderRuler(label, value, min, max, divisor, unit) {
    if (!value || !min || !max) {
        const valStr = value ? (value / divisor).toFixed(2) + unit : '-';
        return `<div>${label}: ${valStr}</div>`;
    }
    const valF = (value / divisor).toFixed(2);
    const minF = (min / divisor).toFixed(2);
    const maxF = (max / divisor).toFixed(2);
    
    let percentage = 50;
    if (max > min) {
        percentage = ((value - min) / (max - min)) * 100;
        percentage = Math.max(0, Math.min(100, percentage));
    }
    
    return `
        <div class="ruler-wrapper" title="当前: ${valF}${unit} | 范围: ${minF} - ${maxF}${unit}">
            <div class="ruler-label">${label}: ${valF}${unit}</div>
            <div class="ruler-container">
                <div class="ruler-marker" style="left: ${percentage}%;"></div>
            </div>
            <div class="ruler-range">
                <span>${minF}</span>
                <span>${maxF}</span>
            </div>
        </div>
    `;
}

function createPetCard(pet) {
    const genderClass = ['', 'male', 'female'][pet.gender] || 'unknown';
    const talentRankLabel = ['普通', '良好', '优秀', '极品'][pet.talent_rank - 1] || '未知';
    const genderLabel = ['', '♂', '♀'][pet.gender] || '';
    const genderIconClass = ['', 'gender-male', 'gender-female'][pet.gender] || '';

    const medalDisplay = pet.medal && pet.medal.length > 10 ? pet.medal.substring(0, 10) + '...' : (pet.medal || '-');

    const escapedName = escapeHtml(pet.name);
    const escapedMedal = escapeHtml(pet.medal);
    const escapedNatureName = escapeHtml(pet.nature_name || '未知');
    const escapedNaturePlus = escapeHtml(pet.nature_plus || '-');
    const escapedNatureMinus = escapeHtml(pet.nature_minus || '-');
    const eggGroupStr = pet.base_egg_group_int
        ? escapeHtml(JSON.parse(pet.base_egg_group_int).join(', '))
        : '-';
    const escapedMedalTitle = escapeHtml(pet.medal || '');
    const escapedEggTitle = escapeHtml(pet.base_egg_group_int || '-');

    return `
        <div class="pet-card ${genderClass}">
            <div class="pet-header">
                <span class="pet-name">${escapedName} <span class="${genderIconClass}">${genderLabel}</span></span>
                <span class="pet-sn" style="color: #95a5a6; font-size: 0.8em;">#${pet.serial_num}</span>
                <span class="pet-level">Lv.${pet.level}</span>
            </div>
            <div class="pet-content">
                ${renderHexagon(pet)}
            </div>
            <div class="nature-info" style="font-size:0.9em; margin: 5px 0; text-align: center;">性格: ${escapedNatureName} (+${escapedNaturePlus} -${escapedNatureMinus})</div>
            <div class="extra-info" style="font-size:0.8em; color: #7f8c8d; margin-bottom: 5px; display: grid; grid-template-columns: 1fr 1fr; gap: 2px; padding: 0 10px;">
                <div title="${escapedMedalTitle}">勋章: ${escapedMedal}</div>
                <div title="${escapedEggTitle}">蛋组: ${eggGroupStr}</div>
                ${renderRuler('身高', pet.height, pet.base_height_low, pet.base_height_high, 100, 'm')}
                ${renderRuler('体重', pet.weight, pet.base_weight_low, pet.base_weight_high, 1000, 'kg')}
            </div>
            <div class="talent-rank rank-${pet.talent_rank}">天赋评级: ${talentRankLabel}</div>
            <div class="gender-setter" style="margin-top:10px; display: flex; justify-content: center; gap: 5px;">
                <button onclick="setGender(${pet.serial_num}, 1)" style="font-size: 0.8em; padding: 2px 5px; cursor: pointer;">设为雄</button>
                <button onclick="setGender(${pet.serial_num}, 2)" style="font-size: 0.8em; padding: 2px 5px; cursor: pointer;">设为雌</button>
            </div>
        </div>
    `;
}

async function setGender(sn, gender) {
    try {
        await fetch('/api/update_gender', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({serial_num: sn, gender: gender})
        });
        
        // 找到页面上所有该 SN 的卡片并更新视觉效果
        const cards = document.querySelectorAll('.pet-card');
        cards.forEach(card => {
            // 这里我们没法直接从 DOM 拿到 SN，但可以在生成时加个 data 属性
            if (card.querySelector('.pet-sn').textContent === `#${sn}`) {
                const genderClass = ['', 'male', 'female'][gender];
                card.classList.remove('male', 'female');
                if (genderClass) card.classList.add(genderClass);
                
                const genderLabel = ['', '♂', '♀'][gender];
                const genderIconClass = ['', 'gender-male', 'gender-female'][gender];
                const nameEl = card.querySelector('.pet-name');
                const baseName = nameEl.textContent.split(' ').slice(0, -1).join(' ');
                nameEl.innerHTML = `${escapeHtml(baseName)} <span class="${genderIconClass}">${genderLabel}</span>`;
            }
        });
    } catch (error) {
        console.error('Failed to update gender:', error);
    }
}

// Expose to window for onclick
window.setGender = setGender;

// Breeding specific logic
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
    
    const filtered = allBasePets.filter(p => 
        p.name.toLowerCase().includes(filterText.toLowerCase())
    );

    filtered.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.objId;
        opt.textContent = p.name;
        targetPetSelect.appendChild(opt);
    });

    // 如果当前选中的值在过滤后依然存在，保持选中；
    // 如果过滤后不见了，但它确实有值，为了不让用户搜索时丢失选项，可以强行加回来（可选）
    targetPetSelect.value = currentValue;
}

targetSearch.addEventListener('input', (e) => {
    renderTargetOptions(e.target.value);
});

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

function saveConfig() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(getCurrentConfig()));
}

function saveToHistory() {
    const config = getCurrentConfig();
    if (!config.targetPetId) return;

    let history;
    try {
        history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        if (!Array.isArray(history)) history = [];
    } catch (e) {
        history = [];
    }
    
    // Deduplicate: remove if exists
    history = history.filter(h => {
        const hTalents = (h.talents || []).sort().join(',');
        const cTalents = (config.talents || []).sort().join(',');
        return !(h.targetPetId === config.targetPetId && 
                 h.natureId === config.natureId && 
                 hTalents === cTalents && 
                 h.useKingBall === config.useKingBall && 
                 h.kingBallAttr === config.kingBallAttr);
    });

    // Add to top
    history.unshift(config);
    // Limit to 20 items
    history = history.slice(0, 20);
    
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    renderHistory();
}

function renderHistory() {
    const historyList = document.getElementById('historyList');
    let history;
    try {
        history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        if (!Array.isArray(history)) history = [];
    } catch (e) {
        history = [];
    }
    
    historyList.innerHTML = '';
    history.forEach((h, index) => {
        const item = document.createElement('div');
        item.style.cssText = `
            padding: 10px;
            background: #f8f9fa;
            border: 1px solid #e9ecef;
            border-radius: 6px;
            font-size: 0.85em;
            cursor: pointer;
            position: relative;
            transition: all 0.2s;
        `;
        
        const talentLabels = {
            hp: '血', adAttack: '攻', apAttack: '魔', 
            adDefense: '防', apDefense: '抗', speed: '速'
        };
        const talentStr = h.talents.map(t => talentLabels[t]).join('/');
        
        item.innerHTML = `
            <div class="history-apply" style="margin-right: 20px;">
                <div style="font-weight: bold; color: #2c3e50;">${h.targetPetName}</div>
                <div style="color: #7f8c8d; margin-top: 2px;">
                    性格: ${h.natureName} | 天赋: ${talentStr || '无'}
                    ${h.useKingBall ? `<br><span style="color: #e67e22;">[国王球: ${talentLabels[h.kingBallAttr]}]</span>` : ''}
                </div>
            </div>
            <button class="delete-history" data-index="${index}" style="
                position: absolute;
                top: 5px;
                right: 5px;
                background: none;
                border: none;
                color: #e74c3c;
                cursor: pointer;
                padding: 2px 5px;
                font-weight: bold;
            ">×</button>
        `;

        item.querySelector('.history-apply').addEventListener('click', () => {
            applyConfig(h);
        });

        item.querySelector('.delete-history').addEventListener('click', (e) => {
            e.stopPropagation();
            deleteHistory(index);
        });

        item.addEventListener('mouseenter', () => item.style.backgroundColor = '#e9ecef');
        item.addEventListener('mouseleave', () => item.style.backgroundColor = '#f8f9fa');

        historyList.appendChild(item);
    });
}

function deleteHistory(index) {
    let history;
    try {
        history = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
        if (!Array.isArray(history)) history = [];
    } catch (e) {
        history = [];
    }
    history.splice(index, 1);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    renderHistory();
}

function applyConfig(config) {
    targetPetSelect.value = config.targetPetId;
    natureSelect.value = config.natureId;
    talentChecks.forEach(check => {
        check.checked = (config.talents || []).includes(check.value);
    });
    useKingBall.checked = config.useKingBall;
    kingBallAttr.value = config.kingBallAttr;
    if (breedBigSize) breedBigSize.checked = config.breedBigSize || false;
    saveConfig();
}


function loadConfig() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    try {
        const config = JSON.parse(saved);
        applyConfig(config);
    } catch (e) {
        console.error('Failed to load breeding config', e);
    }
}

async function init() {
    // ... rest of init ...
    // Load options
    const resBase = await fetch('/api/base_pets');
    allBasePets = await resBase.json();
    renderTargetOptions();

    const natures = [
        "大胆","固执","调皮","勇敢","逞强","稳重","天真","懒散","悠闲","坦率",
        "聪明","专注","偏执","冷静","理性","警惕","温顺","害羞","慎重","焦虑",
        "胆小","急躁","开朗","莽撞","热情","沉默","忧郁","平和","粗心","踏实"
    ];
    natureSelect.innerHTML = '<option value="">选择期望性格...</option>';
    natures.forEach((name, i) => {
        const opt = document.createElement('option');
        opt.value = i + 1;
        opt.textContent = name;
        natureSelect.appendChild(opt);
    });

    loadConfig();
    renderHistory();

    // Event listeners for saving config
    [targetPetSelect, natureSelect, useKingBall, kingBallAttr, breedBigSize].forEach(el => {
        if (el) el.addEventListener('change', saveConfig);
    });
    talentChecks.forEach(el => el.addEventListener('change', saveConfig));

    document.getElementById('clearHistoryBtn').addEventListener('click', () => {
        if (confirm('确定要清空所有历史配置吗？')) {
            localStorage.removeItem(HISTORY_KEY);
            renderHistory();
        }
    });
}

recommendBtn.addEventListener('click', async () => {
    const config = getCurrentConfig();
    
    if (!config.targetPetId) return alert('请选择目标精灵');

    saveToHistory();

    recommendationResults.innerHTML = '<div style="text-align:center; margin-top:100px;">正在匹配最佳父母...</div>';

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
    renderRecommendations(data);
});

function renderRecommendations(data) {
    recommendationResults.innerHTML = '';
    if (data.length === 0) {
        recommendationResults.innerHTML = `
            <div style="text-align: center; color: #e74c3c; margin-top: 100px;">
                <h2>未找到合适的父母组合</h2>
                <p>建议：请确保您已经在仓库主列表中设置了精灵的性别，或者尝试减少期望天赋要求。</p>
            </div>
        `;
        return;
    }

    data.forEach((rec, i) => {
        const pairDiv = document.createElement('div');
        pairDiv.className = 'recommendation-pair';
        
        pairDiv.innerHTML = `
            <div class="pair-info">
                <span>推荐方案 #${i+1}</span>
                <div style="text-align: right;">
                    <div style="color: #27ae60;">综合评分: ${rec.score}</div>
                    ${rec.size_score ? `<div style="color: #d35400; font-size: 0.8em;">体型评分: ${rec.size_score}</div>` : ''}
                    <div style="color: #7f8c8d; font-size: 0.8em;">继承成功率: ${(rec.probability * 100).toFixed(2)}%</div>
                </div>
            </div>
            <div class="pet-card-wrapper">
                <h4>母方 (决定种族)</h4>
                ${createPetCard(rec.mother)}
            </div>
            <div class="pet-card-wrapper">
                <h4>父方</h4>
                ${createPetCard(rec.father)}
            </div>
        `;
        recommendationResults.appendChild(pairDiv);
    });
}

init();
