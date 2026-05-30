let currentPage = 1;
const pageSize = 30;

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

const petListEl = document.getElementById('petList');
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const pageInfo = document.getElementById('pageInfo');
const refreshTimeValue = document.getElementById('refreshTimeValue');

async function fetchRefreshTime() {
    try {
        const response = await fetch('/api/refresh_time');
        const data = await response.json();
        if (data.refresh_time) {
            refreshTimeValue.textContent = data.refresh_time;
        } else {
            refreshTimeValue.textContent = '暂无数据（请先同步）';
        }
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
                <!-- 背景网格 -->
                <polygon points="${bg_points_100}" fill="none" stroke="#ccc" stroke-width="1" />
                <polygon points="${bg_points_50}" fill="none" stroke="#ccc" stroke-width="1" />
                ${stats.map((_, i) => {
                    const angle = (i * 60 - 90) * (Math.PI / 180);
                    const x2 = cx + r_max * Math.cos(angle);
                    const y2 = cy + r_max * Math.sin(angle);
                    return `<line x1="${cx}" y1="${cy}" x2="${x2}" y2="${y2}" stroke="#ccc" stroke-width="1" />`;
                }).join('')}
                
                <!-- 属性多边形 -->
                <polygon points="${points}" fill="rgba(52, 152, 219, 0.4)" stroke="#3498db" stroke-width="2" />
                
                <!-- 标签 -->
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

function renderPets(pets) {
    petListEl.innerHTML = '';
    pets.forEach(pet => {
        const card = document.createElement('div');
        const genderClass = ['', 'male', 'female'][pet.gender] || 'unknown';
        card.className = `pet-card ${genderClass}`;
        
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

        card.innerHTML = `
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
                <button onclick="setGender(${pet.serial_num}, 1)">设为雄</button>
                <button onclick="setGender(${pet.serial_num}, 2)">设为雌</button>
            </div>
        `;
        petListEl.appendChild(card);
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

searchBtn.addEventListener('click', () => {
    currentPage = 1;
    fetchPets();
});

prevBtn.addEventListener('click', () => {
    if (currentPage > 1) {
        currentPage--;
        fetchPets();
    }
});

nextBtn.addEventListener('click', () => {
    currentPage++;
    fetchPets();
});

// Sync button logic
const syncBtn = document.getElementById('syncBtn');
const syncProgress = document.getElementById('syncProgress');
const syncProgressBar = document.getElementById('syncProgressBar');
const syncProgressText = document.getElementById('syncProgressText');
const syncLog = document.getElementById('syncLog');

let cooldownTimer = null;

function formatTime(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    if (h > 0) {
        return `${h}小时${m}分${s}秒`;
    } else if (m > 0) {
        return `${m}分${s}秒`;
    } else {
        return `${s}秒`;
    }
}

function startCooldown(remainingSeconds) {
    syncBtn.disabled = true;
    syncBtn.style.background = '#95a5a6';
    syncBtn.style.cursor = 'not-allowed';
    
    function updateTimer() {
        if (remainingSeconds <= 0) {
            clearInterval(cooldownTimer);
            cooldownTimer = null;
            syncBtn.disabled = false;
            syncBtn.style.background = '#27ae60';
            syncBtn.style.cursor = 'pointer';
            syncBtn.textContent = '同步精灵';
            return;
        }
        syncBtn.textContent = `冷却中 (${formatTime(remainingSeconds)})`;
        remainingSeconds--;
    }
    
    updateTimer();
    cooldownTimer = setInterval(updateTimer, 1000);
}

async function checkSyncStatus() {
    try {
        const response = await fetch('/api/sync_status');
        const data = await response.json();
        
        if (data.cooldown_active) {
            startCooldown(data.remaining_seconds);
        }
    } catch (error) {
        console.error('Failed to check sync status:', error);
    }
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
            if (response.status === 429) {
                addSyncLog(`❌ ${err.detail.message}`);
                startCooldown(err.detail.remaining_seconds);
            } else {
                addSyncLog(`❌ ${err.detail?.message || err.detail || '同步失败'}`);
                resetSyncBtn();
            }
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
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleSyncEvent(data);
                    } catch (e) {
                        // ignore parse errors
                    }
                }
            }
        }
    } catch (error) {
        addSyncLog(`❌ 网络错误: ${error.message}`);
    }

    resetSyncBtn();
});

function handleSyncEvent(data) {
    if (data.error) {
        addSyncLog(`❌ 错误: ${data.error}`);
        return;
    }

    if (data.done) {
        syncProgressBar.style.width = '100%';
        syncProgressText.textContent = '100%';
        const r = data.result || {};
        addSyncLog(`✅ 同步完成！新增 ${r.new || 0} 只，更新 ${r.updated || 0} 只，共 ${r.total || 0} 只`);
        fetchPets();
        fetchRefreshTime();
        // Check cooldown from API (based on pet refresh time)
        checkSyncStatus();
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

// Initial fetch
fetchPets();
fetchRefreshTime();
checkSyncStatus();
window.setGender = setGender; // 暴露给 HTML onclick
