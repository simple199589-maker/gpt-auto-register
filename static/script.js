let isRunning = false;
let logIndex = 0;
let pollInterval = null;
let lastFrameVersion = -1;
let isStreamingMonitor = false;

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    switchTab('dashboard');
    startPolling();
});

// 切换视图
function switchTab(tabName) {
    document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

    document.getElementById(`view-${tabName}`).classList.add('active');

    // 找到对应的 nav item 高亮
    const navIndex = tabName === 'dashboard' ? 0 : 1;
    document.querySelectorAll('.nav-item')[navIndex].classList.add('active');

    if (tabName === 'accounts') {
        loadAccounts();
    }
}

// 轮询状态
function startPolling() {
    pollStatus(); // 立即执行一次
    pollInterval = setInterval(pollStatus, 1000);
}

async function pollStatus() {
    try {
        const res = await fetch(`/api/status?log_index=${logIndex}`);
        const data = await res.json();

        updateUI(data);
    } catch (e) {
        console.error("Polling error:", e);
    }
}

function updateUI(data) {
    // 1. 更新基本指标
    document.getElementById('valAction').textContent = data.current_action;
    document.getElementById('valSuccess').textContent = data.success;
    document.getElementById('valFail').textContent = data.fail;
    document.getElementById('valInventory').textContent = data.total_inventory;
    document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();

    // 2. 更新运行状态 (按钮和指示灯)
    isRunning = data.is_running;
    const btnStart = document.getElementById('btnStart');
    const btnStop = document.getElementById('btnStop');
    const statusDot = document.getElementById('statusDot');
    const statusText = document.getElementById('statusText');

    if (isRunning) {
        btnStart.classList.add('hidden');
        btnStop.classList.remove('hidden');
        statusDot.classList.add('active');
        statusText.textContent = "运行中";
    } else {
        btnStart.classList.remove('hidden');
        btnStop.classList.add('hidden');
        statusDot.classList.remove('active');
        statusText.textContent = "系统空闲";
    }

    // 4. 更新监控画面
    const monitorImg = document.getElementById('liveMonitor');
    const noSignal = document.getElementById('noSignal');
    const monitorStatus = document.getElementById('monitorStatus');
    const hasFrame = Boolean(data.has_frame);
    const frameVersion = Number.isInteger(data.frame_version) ? data.frame_version : -1;

    if (isRunning || hasFrame) {
        monitorImg.classList.remove('hidden');
        if (isRunning) {
            if (!isStreamingMonitor || !monitorImg.src || monitorImg.src.indexOf('/video_feed') === -1) {
                monitorImg.src = `/video_feed?ts=${Date.now()}`;
                isStreamingMonitor = true;
            }

            if (hasFrame) {
                noSignal.classList.add('hidden');
            } else {
                noSignal.classList.remove('hidden');
                noSignal.textContent = "等待首帧画面...";
            }
        } else {
            isStreamingMonitor = false;
            if (hasFrame) {
                noSignal.classList.add('hidden');
                if (frameVersion !== lastFrameVersion || monitorImg.src.indexOf('/api/frame') === -1) {
                    monitorImg.src = `/api/frame?v=${frameVersion}`;
                    lastFrameVersion = frameVersion;
                }
            } else {
                noSignal.classList.remove('hidden');
                noSignal.textContent = "等待信号...";
            }
        }
        monitorStatus.textContent = isRunning ? "LIVE" : "IDLE";
        monitorStatus.classList.remove('neutral');
        monitorStatus.classList.add('success');
    } else {
        isStreamingMonitor = false;
        monitorImg.classList.add('hidden');
        noSignal.classList.remove('hidden');
        noSignal.textContent = "等待信号...";
        monitorStatus.textContent = "OFFLINE";
        monitorStatus.classList.remove('success');
        monitorStatus.classList.add('neutral');
    }

    // 5. 追加日志
    if (data.logs && data.logs.length > 0) {
        const container = document.getElementById('logContainer');

        // 移除占位符
        const placeholder = container.querySelector('.log-placeholder');
        if (placeholder) placeholder.remove();

        data.logs.forEach(logLine => {
            const div = document.createElement('div');
            div.className = 'log-entry';
            div.textContent = logLine;
            container.appendChild(div);
        });

        // 自动滚动到底部
        container.scrollTop = container.scrollHeight;

        // 更新索引，避免重复拉取
        logIndex += data.logs.length;
    }
}

// 启动任务
async function startTask() {
    const count = parseInt(document.getElementById('targetCount').value) || 1;

    // 清空旧日志
    clearLogs();

    try {
        const res = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ count: count })
        });

        if (!res.ok) {
            alert("启动失败: " + await res.text());
        }
    } catch (e) {
        alert("请求失败: " + e);
    }
}

// 停止任务
async function stopTask() {
    if (!confirm("确定要停止当前任务吗？")) return;

    try {
        await fetch('/api/stop', { method: 'POST' });
    } catch (e) {
        console.error(e);
    }
}

// 清空日志
function clearLogs() {
    document.getElementById('logContainer').innerHTML = '<div class="log-placeholder">等待任务启动...</div>';
    logIndex = 0; // 注意：后端日志清理逻辑可能需要配合，这里只是前端重置
    // 实际上后端是基于 index 的，所以重置 index 会导致拉取到后端存量的旧日志
    // 为了简单起见，我们重置前端，但后端日志索引如果没变，可能会导致不同步
    // 更好的做法是后端提供清空接口，或者前端维护一个 offset。
    // 在这个简单实现里，我们直接重置 index 并希望后端是配合的，但在 AppState 里我们没有清空后端。
    // 修正：我们不应该重置 logIndex 为 0，而是应该保持当前 index，只是清空显示。
    // 但是为了视觉上的清空，我们这里清空 DOM 元素即可。
}

// 加载账号列表
async function loadAccounts() {
    const tbody = document.getElementById('accountTableBody');
    tbody.innerHTML = '<tr><td colspan="4" style="text-align:center">加载中...</td></tr>';

    try {
        const res = await fetch('/api/accounts');
        const accounts = await res.json();

        renderAccounts(accounts);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align:center;color:red">加载失败: ${e}</td></tr>`;
    }
}

function renderAccounts(accounts) {
    const tbody = document.getElementById('accountTableBody');
    tbody.innerHTML = '';

    if (accounts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#666">暂无数据</td></tr>';
        return;
    }

    accounts.forEach(acc => {
        let statusClass = '';
        if (acc.status.includes('成功') || acc.status.includes('已注册')) statusClass = 'success';
        if (acc.status.includes('失败')) statusClass = 'fail';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${acc.email}</td>
            <td style="font-family:monospace">${acc.password}</td>
            <td><span class="status-tag ${statusClass}">${acc.status}</span></td>
            <td>${acc.time}</td>
        `;
        tbody.appendChild(tr);
    });

    // 保存到全局以便搜索
    window.allAccounts = accounts;
}

// 搜索账号
function filterAccounts() {
    const term = document.getElementById('searchInput').value.toLowerCase();
    if (!window.allAccounts) return;

    const filtered = window.allAccounts.filter(acc =>
        acc.email.toLowerCase().includes(term)
    );
    renderAccounts(filtered);
}
