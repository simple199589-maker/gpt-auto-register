const { createApp, reactive, ref, computed, onMounted, onBeforeUnmount, watch, nextTick } = Vue

const antNamespace = window.antd || window.Antd || {}
const antPlugin = antNamespace && antNamespace.default && antNamespace.default.install
    ? antNamespace.default
    : antNamespace
const antMessage = antNamespace.message || (antPlugin && antPlugin.message) || null

function registerAntComponents(appInstance) {
    const menuComponent = antNamespace.Menu || (antPlugin && antPlugin.Menu)
    const selectComponent = antNamespace.Select || (antPlugin && antPlugin.Select)
    const radioComponent = antNamespace.Radio || (antPlugin && antPlugin.Radio)
    const checkboxComponent = antNamespace.Checkbox || (antPlugin && antPlugin.Checkbox)
    const componentPairs = [
        ['AMenu', menuComponent],
        ['AMenuItem', (menuComponent && (menuComponent.Item || menuComponent.MenuItem)) || antNamespace.MenuItem],
        ['ACard', antNamespace.Card || (antPlugin && antPlugin.Card)],
        ['AInput', antNamespace.Input || (antPlugin && antPlugin.Input)],
        ['AInputNumber', antNamespace.InputNumber || (antPlugin && antPlugin.InputNumber)],
        ['AButton', antNamespace.Button || (antPlugin && antPlugin.Button)],
        ['ASwitch', antNamespace.Switch || (antPlugin && antPlugin.Switch)],
        ['ATag', antNamespace.Tag || (antPlugin && antPlugin.Tag)],
        ['AEmpty', antNamespace.Empty || (antPlugin && antPlugin.Empty)],
        ['ASelect', selectComponent],
        ['ASelectOption', (selectComponent && (selectComponent.Option || selectComponent.SelectOption)) || antNamespace.SelectOption],
        ['ATable', antNamespace.Table || (antPlugin && antPlugin.Table)],
        ['APagination', antNamespace.Pagination || (antPlugin && antPlugin.Pagination)],
        ['ATooltip', antNamespace.Tooltip || (antPlugin && antPlugin.Tooltip)],
        ['APopover', antNamespace.Popover || (antPlugin && antPlugin.Popover)],
        ['AModal', antNamespace.Modal || (antPlugin && antPlugin.Modal)],
        ['ADrawer', antNamespace.Drawer || (antPlugin && antPlugin.Drawer)],
        ['ARadioGroup', (radioComponent && radioComponent.Group) || antNamespace.RadioGroup],
        ['ARadio', radioComponent],
        ['ACheckboxGroup', (checkboxComponent && checkboxComponent.Group) || antNamespace.CheckboxGroup],
        ['ACheckbox', checkboxComponent],
    ]

    componentPairs.forEach(([name, component]) => {
        if (component) {
            appInstance.component(name, component)
        }
    })
}

function showSuccess(message) {
    if (antMessage) {
        antMessage.success(message)
        return
    }
    window.alert(message)
}

function showError(message) {
    if (antMessage) {
        antMessage.error(message)
        return
    }
    window.alert(message)
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options)
    let data = null

    try {
        data = await response.json()
    } catch (error) {
        data = null
    }

    if (!response.ok) {
        const text = data && (data.error || data.message)
            ? (data.error || data.message)
            : `请求失败: ${response.status}`
        throw new Error(text)
    }

    return data
}

function includesAnyKeyword(text, keyword) {
    return String(text || '').toLowerCase().includes(String(keyword || '').trim().toLowerCase())
}

function normalizeReasonText(text) {
    const value = String(text || '').trim()
    if (!value || value === '暂无附加信息') {
        return ''
    }
    return value
}

function formatEmailCompact(email) {
    return String(email || '').trim()
}

function formatPasswordCompact(password) {
    const value = String(password || '').trim()
    if (!value) {
        return '--'
    }
    if (value.length <= 10) {
        return value
    }
    return `${value.slice(0, 3)}...${value.slice(-3)}`
}

function formatTimeCompact(value) {
    const raw = String(value || '').trim()
    if (!raw) {
        return '--'
    }
    const match = raw.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/)
    if (!match) {
        return raw
    }
    return `${match[2]}-${match[3]} ${match[4]}:${match[5]}`
}

function resolveStatusTone(kind) {
    if (kind === 'failed') {
        return 'danger'
    }
    if (kind === 'pending') {
        return 'warning'
    }
    if (kind === 'success') {
        return 'success'
    }
    if (kind === 'disabled') {
        return 'muted'
    }
    return 'info'
}

function classifyOverallStatus(record) {
    if (record && record.overallStatus) {
        return String(record.overallStatus)
    }
    const status = String(record && record.status || '')
    if (status.includes('注册中')) {
        return 'pending'
    }
    if (status.includes('失败') || status.includes('错误') || status.includes('缺失') || status.includes('中断')) {
        return 'failed'
    }
    if (status.includes('已上传') || status.includes('已激活') || status.includes('已注册')) {
        return 'success'
    }
    return 'pending'
}

function classifyLoginStatus(record) {
    if (record && (record.loginState || record.loginStatus)) {
        return String(record.loginState || record.loginStatus)
    }
    const status = String(record && record.status || '')
    if (status.includes('登录失败') || status.includes('Token获取失败')) {
        return 'failed'
    }
    if (status.includes('登录成功') || status.includes('已上传Sub2Api')) {
        return 'success'
    }
    return 'pending'
}

function classifySub2ApiStatus(record) {
    if (record && record.sub2apiState) {
        return String(record.sub2apiState)
    }
    const subStatus = String(record && record.sub2apiStatus || '')

    if (record && record.sub2apiUploaded) {
        return 'success'
    }
    if (subStatus.includes('未启用')) {
        return 'disabled'
    }
    if (!subStatus || subStatus.includes('待上传') || subStatus.includes('未上传')) {
        return 'pending'
    }
    return 'failed'
}

function classifyTeamManageStatus(record) {
    if (record && record.teamManageState) {
        return String(record.teamManageState)
    }
    const status = String(record && record.teamManageStatus || '')

    if (record && record.teamManageUploaded) {
        return 'success'
    }
    if (status.includes('未启用')) {
        return 'disabled'
    }
    if (!status || status.includes('待上传') || status.includes('未上传')) {
        return 'pending'
    }
    return 'failed'
}

const app = createApp({
    template: '#app-template',
    setup() {
        const currentTab = ref('dashboard')
        const targetCount = ref(1)
        const isRunning = ref(false)
        const currentAction = ref('等待启动')
        const successCount = ref(0)
        const failCount = ref(0)
        const totalInventory = ref(0)
        const lastUpdate = ref('--:--:--')
        const logs = ref([])
        const logIndex = ref(0)
        const pollTimer = ref(null)
        const mobileMenuOpen = ref(false)
        const dashboardStats = reactive({
            total: 0,
            category: { normal: 0, mother: 0 },
            login: { pending: 0, success: 0, failed: 0, disabled: 0 },
            sub2api: { pending: 0, success: 0, failed: 0, disabled: 0 },
            team_manage: { pending: 0, success: 0, failed: 0, disabled: 0 },
            pending_accounts: 0,
            failed_accounts: 0,
            login_success_rate: 0,
            recent_errors: []
        })
        const settingsSaving = ref(false)
        const groupIdsInputFocused = ref(false)
        const accountsLoading = ref(false)
        const accountExporting = ref(false)
        const accountImporting = ref(false)
        const accounts = ref([])
        const logContainerRef = ref(null)
        const accountImportFileRef = ref(null)
        const accountActionLoading = reactive({})
        const actionPopoverOpen = reactive({})
        const showManualAccountPanel = ref(false)
        const manualAccountSubmitting = ref(false)
        const manualAccountForm = reactive({
            email: '',
            password: '',
            accountCategory: 'normal',
            remark: ''
        })
        const accountDetailModalOpen = ref(false)
        const accountDetailRecord = ref(null)
        const loginUploadModalOpen = ref(false)
        const loginUploadRecord = ref(null)
        const loginUploadSubmitting = ref(false)
        const loginOtpSubmitting = ref(false)
        const loginOtpReady = ref(false)
        const loginOtpStatusText = ref('')
        const loginOtpResendRemaining = ref(60)
        const loginOtpResending = ref(false)
        const loginUploadCancelling = ref(false)
        let loginOtpStatusTimer = null
        let loginUploadRequestSeq = 0
        const loginUploadForm = reactive({
            otpMode: 'auto',
            uploadTargets: ['sub2api'],
            otpCode: ''
        })
        const serverSettings = reactive({
            sub2api_auto_upload_enabled: false,
            sub2api_group_ids: [],
            proxy_enabled: false,
            proxy_host: '',
            proxy_port: 0
        })
        const settings = reactive({
            sub2api_auto_upload_enabled: false,
            sub2api_group_ids: [],
            sub2api_group_ids_text: '',
            proxy_enabled: false,
            proxy_host: '',
            proxy_port: 0,
            proxy_port_text: ''
        })
        const accountFilters = reactive({
            keyword: '',
            category: 'all',
            login: 'all',
            sub2api: 'all',
            teamManage: 'all'
        })
        const accountPagination = reactive({
            current: 1,
            pageSize: 10,
            total: 0,
            totalPages: 1
        })
        const pageSizeOptions = ['10', '20', '50']

        const accountColumns = [
            { title: '邮箱', dataIndex: 'email', key: 'email', width: 210 },
            { title: '密码', dataIndex: 'password', key: 'password', width: 118 },
            { title: '分类', key: 'category', width: 88 },
            { title: '登录状态', dataIndex: 'status', key: 'status', width: 154 },
            { title: '上传', key: 'sub2api', width: 128 },
            { title: 'Team', key: 'teamManage', width: 128 },
            { title: '时间', dataIndex: 'time', key: 'time', width: 116 },
            { title: '', key: 'actions', width: 64, fixed: 'right' }
        ]

        const totalAccountPages = computed(() => {
            return Math.max(Number(accountPagination.totalPages || 1), 1)
        })

        const pagedAccounts = computed(() => accounts.value)

        /**
         * 构建账号列表筛选参数。
         *
         * @author AI by zb
         */
        function buildAccountFilterParams(includePagination = true) {
            const params = new URLSearchParams({
                keyword: String(accountFilters.keyword || '').trim(),
                account_category: accountFilters.category === 'all' ? '' : accountFilters.category,
                login_status: accountFilters.login === 'all' ? '' : accountFilters.login,
                sub2api_status: accountFilters.sub2api === 'all' ? '' : accountFilters.sub2api,
                team_manage_status: accountFilters.teamManage === 'all' ? '' : accountFilters.teamManage,
            })
            if (includePagination) {
                params.set('page', String(accountPagination.current))
                params.set('page_size', String(accountPagination.pageSize))
            }
            return params
        }

        function syncSettings(data) {
            serverSettings.sub2api_auto_upload_enabled = Boolean(data && data.sub2api_auto_upload_enabled)
            serverSettings.sub2api_group_ids = Array.isArray(data && data.sub2api_group_ids)
                ? data.sub2api_group_ids.map((item) => Number(item)).filter((item) => Number.isInteger(item))
                : []
            serverSettings.proxy_enabled = Boolean(data && data.proxy_enabled)
            serverSettings.proxy_host = String(data && data.proxy_host || '')
            serverSettings.proxy_port = Number(data && data.proxy_port || 0)

            if (!settingsSaving.value) {
                settings.sub2api_auto_upload_enabled = serverSettings.sub2api_auto_upload_enabled
                settings.sub2api_group_ids = [...serverSettings.sub2api_group_ids]
                settings.proxy_enabled = serverSettings.proxy_enabled
                settings.proxy_host = serverSettings.proxy_host
                settings.proxy_port = serverSettings.proxy_port
                settings.proxy_port_text = serverSettings.proxy_port ? String(serverSettings.proxy_port) : ''
                if (!groupIdsInputFocused.value) {
                    settings.sub2api_group_ids_text = serverSettings.sub2api_group_ids.join(',')
                }
            }
        }

        function parseGroupIdsInput(text) {
            return String(text || '')
                .replaceAll('，', ',')
                .split(',')
                .map((item) => item.trim())
                .filter((item) => /^-?\d+$/.test(item))
                .map((item) => Number(item))
        }

        function parseProxyPortInput(text) {
            const port = Number.parseInt(String(text || '').trim(), 10)
            return Number.isInteger(port) && port >= 0 && port <= 65535 ? port : 0
        }

        function restoreSettingsFromServer() {
            settings.sub2api_auto_upload_enabled = serverSettings.sub2api_auto_upload_enabled
            settings.sub2api_group_ids = [...serverSettings.sub2api_group_ids]
            settings.sub2api_group_ids_text = serverSettings.sub2api_group_ids.join(',')
            settings.proxy_enabled = serverSettings.proxy_enabled
            settings.proxy_host = serverSettings.proxy_host
            settings.proxy_port = serverSettings.proxy_port
            settings.proxy_port_text = serverSettings.proxy_port ? String(serverSettings.proxy_port) : ''
        }

        /**
         * 同步统计中心数据。
         *
         * @author AI by zb
         */
        function syncDashboardStats(rawStats) {
            const stats = rawStats || {}
            const category = stats.category || {}
            const login = stats.login || {}
            const sub2api = stats.sub2api || {}
            const teamManage = stats.team_manage || {}

            dashboardStats.total = Number(stats.total || 0)
            dashboardStats.category.normal = Number(category.normal || 0)
            dashboardStats.category.mother = Number(category.mother || 0)
            dashboardStats.login.pending = Number(login.pending || 0)
            dashboardStats.login.success = Number(login.success || 0)
            dashboardStats.login.failed = Number(login.failed || 0)
            dashboardStats.login.disabled = Number(login.disabled || 0)
            dashboardStats.sub2api.pending = Number(sub2api.pending || 0)
            dashboardStats.sub2api.success = Number(sub2api.success || 0)
            dashboardStats.sub2api.failed = Number(sub2api.failed || 0)
            dashboardStats.sub2api.disabled = Number(sub2api.disabled || 0)
            dashboardStats.team_manage.pending = Number(teamManage.pending || 0)
            dashboardStats.team_manage.success = Number(teamManage.success || 0)
            dashboardStats.team_manage.failed = Number(teamManage.failed || 0)
            dashboardStats.team_manage.disabled = Number(teamManage.disabled || 0)
            dashboardStats.pending_accounts = Number(stats.pending_accounts || 0)
            dashboardStats.failed_accounts = Number(stats.failed_accounts || 0)
            dashboardStats.login_success_rate = Number(stats.login_success_rate || 0)
            dashboardStats.recent_errors = Array.isArray(stats.recent_errors) ? stats.recent_errors : []
        }

        async function pollStatus() {
            try {
                const data = await requestJson(`/api/status?log_index=${logIndex.value}`)
                isRunning.value = Boolean(data && data.is_running)
                currentAction.value = data && data.current_action ? data.current_action : '等待启动'
                successCount.value = Number(data && data.success || 0)
                failCount.value = Number(data && data.fail || 0)
                totalInventory.value = Number(data && data.total_inventory || 0)
                lastUpdate.value = new Date().toLocaleTimeString()

                syncSettings(data)
                syncDashboardStats(data && data.dashboard_stats)

                if (Array.isArray(data && data.logs) && data.logs.length) {
                    logs.value.push(...data.logs)
                    logIndex.value += data.logs.length
                }

            } catch (error) {
                console.error('Polling error:', error)
            }
        }

        function startPolling() {
            pollStatus()
            pollTimer.value = window.setInterval(pollStatus, 1000)
        }

        function stopPolling() {
            if (pollTimer.value) {
                window.clearInterval(pollTimer.value)
                pollTimer.value = null
            }
        }

        function isActivationPipelineBusy() {
            return false
        }

        async function startTask() {
            try {
                logs.value = []
                await requestJson('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ count: Number(targetCount.value) || 1 })
                })
                showSuccess('任务已启动')
            } catch (error) {
                showError(error.message)
            }
        }

        async function stopTask() {
            if (!window.confirm('确定要停止当前任务吗？')) {
                return
            }

            try {
                await requestJson('/api/stop', { method: 'POST' })
                showSuccess('已发送停止请求')
            } catch (error) {
                showError(error.message)
            }
        }

        function clearLogs() {
            logs.value = []
        }

        async function saveAutomationSettings() {
            if (isRunning.value) {
                restoreSettingsFromServer()
                showError('任务运行中，请先停止后再修改设置')
                return
            }

            settingsSaving.value = true
            try {
                const groupIds = parseGroupIdsInput(settings.sub2api_group_ids_text)
                const proxyHost = String(settings.proxy_host || '').trim()
                const proxyPort = parseProxyPortInput(settings.proxy_port_text)
                const payload = {
                    sub2api_auto_upload_enabled: Boolean(settings.sub2api_auto_upload_enabled),
                    sub2api_group_ids: groupIds.length ? groupIds : [...serverSettings.sub2api_group_ids],
                    proxy_enabled: Boolean(settings.proxy_enabled),
                    proxy_host: proxyHost,
                    proxy_port: proxyPort
                }
                const data = await requestJson('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                syncSettings(data)
                restoreSettingsFromServer()
                showSuccess('设置已保存')
            } catch (error) {
                restoreSettingsFromServer()
                showError(error.message)
            } finally {
                settingsSaving.value = false
                groupIdsInputFocused.value = false
            }
        }

        function handleGroupIdsBlur() {
            groupIdsInputFocused.value = false
            saveAutomationSettings()
        }

        function fallbackCopyText(text) {
            const textarea = document.createElement('textarea')
            textarea.value = text
            textarea.setAttribute('readonly', 'readonly')
            textarea.style.position = 'fixed'
            textarea.style.top = '-9999px'
            document.body.appendChild(textarea)
            textarea.select()
            textarea.setSelectionRange(0, textarea.value.length)
            const copied = document.execCommand('copy')
            document.body.removeChild(textarea)
            return copied
        }

        async function copyText(rawText, label) {
            const text = String(rawText || '').trim()
            if (!text || text === '--') {
                showError(`没有可复制的${label}`)
                return
            }

            try {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    await navigator.clipboard.writeText(text)
                } else if (!fallbackCopyText(text)) {
                    throw new Error('浏览器复制失败')
                }
                showSuccess(`${label}已复制`)
            } catch (error) {
                showError(`${label}复制失败`)
            }
        }

        /**
         * 从下载响应头提取文件名。
         *
         * @author AI by zb
         */
        function resolveDownloadFilename(response, fallback) {
            const disposition = response.headers.get('Content-Disposition') || ''
            const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i)
            if (utf8Match && utf8Match[1]) {
                return decodeURIComponent(utf8Match[1].replaceAll('"', ''))
            }
            const normalMatch = disposition.match(/filename="?([^";]+)"?/i)
            return normalMatch && normalMatch[1] ? normalMatch[1] : fallback
        }

        /**
         * 下载账号导出 JSON。
         *
         * @author AI by zb
         */
        async function downloadAccountExport(query, fallbackFilename) {
            const response = await fetch(`/api/accounts/export?${query.toString()}`)
            if (!response.ok) {
                let message = `导出失败: ${response.status}`
                try {
                    const data = await response.json()
                    message = data && (data.error || data.message) ? (data.error || data.message) : message
                } catch (error) {
                    message = response.statusText || message
                }
                throw new Error(message)
            }

            const blob = await response.blob()
            const filename = resolveDownloadFilename(response, fallbackFilename)
            const objectUrl = URL.createObjectURL(blob)
            const link = document.createElement('a')
            link.href = objectUrl
            link.download = filename
            document.body.appendChild(link)
            link.click()
            document.body.removeChild(link)
            URL.revokeObjectURL(objectUrl)
        }

        /**
         * 导出当前筛选条件下的全部账号。
         *
         * @author AI by zb
         */
        async function exportFilteredAccounts() {
            accountExporting.value = true
            try {
                await downloadAccountExport(buildAccountFilterParams(false), `accounts_export_${Date.now()}.json`)
                showSuccess('账号导出已开始')
            } catch (error) {
                showError(error.message)
            } finally {
                accountExporting.value = false
            }
        }

        /**
         * 导出单个账号。
         *
         * @author AI by zb
         */
        async function exportSingleAccount(record) {
            if (!record || !record.email) {
                return
            }
            const actionKey = buildActionKey('/api/accounts/export', record.email)
            accountActionLoading[actionKey] = true
            try {
                const query = new URLSearchParams({ email: record.email })
                await downloadAccountExport(query, `account_export_${record.email}_${Date.now()}.json`)
                showSuccess('账号导出已开始')
            } catch (error) {
                showError(`${record.email}\n${error.message}`)
            } finally {
                accountActionLoading[actionKey] = false
            }
        }

        /**
         * 打开账号 JSON 文件选择器。
         *
         * @author AI by zb
         */
        function triggerImportJsonFile() {
            if (isRunning.value) {
                showError('任务运行中，请稍后再导入')
                return
            }
            if (accountImportFileRef.value) {
                accountImportFileRef.value.value = ''
                accountImportFileRef.value.click()
            }
        }

        /**
         * 读取文本文件。
         *
         * @author AI by zb
         */
        function readFileAsText(file) {
            return new Promise((resolve, reject) => {
                const reader = new FileReader()
                reader.onload = () => resolve(String(reader.result || ''))
                reader.onerror = () => reject(new Error('读取文件失败'))
                reader.readAsText(file, 'utf-8')
            })
        }

        /**
         * 导入账号 JSON 文件。
         *
         * @author AI by zb
         */
        async function handleImportJsonFileChange(event) {
            const file = event && event.target && event.target.files ? event.target.files[0] : null
            if (!file) {
                return
            }

            accountImporting.value = true
            try {
                const text = await readFileAsText(file)
                const payload = JSON.parse(text)
                const data = await requestJson('/api/accounts/import-json', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                const failed = Array.isArray(data && data.failed) ? data.failed.length : 0
                const message = failed
                    ? `已导入 ${data.imported || 0} 个账号，失败 ${failed} 个`
                    : (data && data.message ? data.message : '账号导入完成')
                showSuccess(message)
                if (accountPagination.current !== 1) {
                    accountPagination.current = 1
                } else {
                    await loadAccounts()
                }
            } catch (error) {
                showError(error.message || '导入失败')
            } finally {
                accountImporting.value = false
                if (event && event.target) {
                    event.target.value = ''
                }
            }
        }

        async function loadAccounts() {
            accountsLoading.value = true
            try {
                const query = buildAccountFilterParams(true)
                const data = await requestJson(`/api/accounts?${query.toString()}`)
                accounts.value = Array.isArray(data && data.items) ? data.items : []
                accountPagination.total = Number(data && data.pagination && data.pagination.total || 0)
                accountPagination.totalPages = Number(data && data.pagination && data.pagination.total_pages || 1)
                if (accountPagination.current > accountPagination.totalPages) {
                    accountPagination.current = accountPagination.totalPages
                    return
                }
            } catch (error) {
                showError(error.message)
                accounts.value = []
                accountPagination.total = 0
                accountPagination.totalPages = 1
            } finally {
                accountsLoading.value = false
            }
        }

        /**
         * 将后端返回的最新账号记录合并到当前列表。
         *
         * @author AI by zb
         */
        function mergeAccountRecord(nextRecord) {
            const normalizedEmail = String(nextRecord && nextRecord.email || '').trim().toLowerCase()
            if (!normalizedEmail) {
                return
            }

            const targetIndex = accounts.value.findIndex((item) => {
                return String(item && item.email || '').trim().toLowerCase() === normalizedEmail
            })
            if (targetIndex < 0) {
                return
            }
            accounts.value.splice(targetIndex, 1, nextRecord)
        }

        /**
         * 重置导入账号表单。
         *
         * @author AI by zb
         */
        function resetManualAccountForm() {
            manualAccountForm.email = ''
            manualAccountForm.password = ''
            manualAccountForm.accountCategory = 'normal'
            manualAccountForm.remark = ''
        }

        /**
         * 关闭导入账号面板并清空输入。
         *
         * @author AI by zb
         */
        function closeManualAccountPanel() {
            showManualAccountPanel.value = false
            resetManualAccountForm()
        }

        /**
         * 切换导入账号面板显示状态。
         *
         * @author AI by zb
         */
        function toggleManualAccountPanel() {
            if (showManualAccountPanel.value) {
                closeManualAccountPanel()
                return
            }
            showManualAccountPanel.value = true
        }

        /**
         * 提交导入账号请求。
         *
         * @author AI by zb
         */
        async function submitManualAccount() {
            const email = String(manualAccountForm.email || '').trim().toLowerCase()
            const password = String(manualAccountForm.password || '').trim()
            const accountCategory = String(manualAccountForm.accountCategory || 'normal').trim()
            const remark = String(manualAccountForm.remark || '').trim()

            if (!email) {
                showError('请输入账号邮箱')
                return
            }
            if (!password) {
                showError('请输入账号密码')
                return
            }

            manualAccountSubmitting.value = true
            try {
                const data = await requestJson('/api/accounts/import', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password, account_category: accountCategory, remark })
                })

                showSuccess(data && data.message ? data.message : '账号已导入')
                closeManualAccountPanel()
                if (accountPagination.current !== 1) {
                    accountPagination.current = 1
                } else {
                    await loadAccounts()
                }
            } catch (error) {
                showError(error.message)
            } finally {
                manualAccountSubmitting.value = false
            }
        }

        function buildActionKey(url, email) {
            return `${url}::${email}`
        }

        function isAccountActionRunning(url, email) {
            return Boolean(accountActionLoading[buildActionKey(url, email)])
        }

        function isAnyAccountActionRunning(record) {
            const email = record && record.email ? record.email : ''
            if (!email) {
                return false
            }
            return [
                '/api/accounts/login-sub2api',
                '/api/accounts/upload-sub2api',
                '/api/accounts/upload-team-manage',
                '/api/accounts/export',
                '/api/accounts/delete'
            ].some((url) => isAccountActionRunning(url, email))
        }

        function hasAccountActions(record) {
            return Boolean(
                record
                && (
                    record.email
                    || record.canDeleteAccount
                    || record.canUploadExistingToken
                    || record.canUploadTeamManage
                )
            )
        }

        function getActionPopoverKey(record) {
            return `action-popover::${getAccountRowKey(record)}`
        }

        function isActionPopoverOpen(record) {
            return Boolean(actionPopoverOpen[getActionPopoverKey(record)])
        }

        function setActionPopoverOpen(record, open) {
            if (!record) {
                return
            }
            actionPopoverOpen[getActionPopoverKey(record)] = Boolean(open)
        }

        async function runAccountAction(url, email, payload = {}) {
            if (!email) {
                return
            }

            const actionKey = buildActionKey(url, email)
            accountActionLoading[actionKey] = true

            try {
                const data = await requestJson(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, ...payload })
                })

                if (!data || data.success !== false || data.cancelled) {
                    showSuccess(data && data.message ? data.message : '操作成功')
                } else {
                    showError(data.message || '操作失败')
                }
                await loadAccounts()
                return data
            } catch (error) {
                showError(`${email}\n${error.message}`)
            } finally {
                accountActionLoading[actionKey] = false
            }
        }

        async function handleUploadSub2Api(record) {
            if (!record || !record.email) {
                return
            }
            if (record.sub2apiUploaded) {
                const confirmed = window.confirm(`${record.email}\n该记录已经上传过 Sub2Api，确认重新上传吗？`)
                if (!confirmed) {
                    return
                }
            }
            await runAccountAction('/api/accounts/upload-sub2api', record.email)
        }

        async function handleUploadTeamManage(record) {
            if (!record || !record.email) {
                return
            }
            if (record.teamManageUploaded) {
                const confirmed = window.confirm(`${record.email}\n该母号已经上传过 Team 管理，确认重新上传吗？`)
                if (!confirmed) {
                    return
                }
            }
            await runAccountAction('/api/accounts/upload-team-manage', record.email)
        }

        /**
         * 根据账号类型重置登录上传弹窗默认值。
         *
         * @author AI by zb
         */
        function resetLoginUploadForm(record = null) {
            loginUploadForm.otpMode = record && record.isMotherAccount ? 'manual' : 'auto'
            loginUploadForm.uploadTargets = record && record.isMotherAccount
                ? ['sub2api', 'team_manage']
                : ['sub2api']
            loginUploadForm.otpCode = ''
            loginOtpReady.value = false
            loginOtpStatusText.value = ''
            loginOtpResendRemaining.value = 60
        }

        /**
         * 停止登录验证码状态轮询。
         *
         * @author AI by zb
         */
        function stopLoginOtpStatusPolling() {
            if (loginOtpStatusTimer) {
                clearInterval(loginOtpStatusTimer)
                loginOtpStatusTimer = null
            }
        }

        /**
         * 将后端验证码等待状态同步到弹窗。
         *
         * @author AI by zb
         */
        function applyLoginOtpStatus(data) {
            const active = Boolean(data && data.active)
            loginOtpReady.value = active && Boolean(data && data.can_submit)
            loginOtpStatusText.value = data && data.message
                ? String(data.message)
                : (active ? '验证码已发送，请输入 6 位验证码' : '正在等待验证码发送')
            const remaining = Number(data && data.resend_remaining)
            loginOtpResendRemaining.value = Number.isFinite(remaining) ? Math.max(Math.ceil(remaining), 0) : 60
        }

        /**
         * 拉取当前账号的验证码等待状态。
         *
         * @author AI by zb
         */
        async function refreshLoginOtpStatus() {
            const record = loginUploadRecord.value
            if (!record || !record.email || loginUploadForm.otpMode !== 'manual') {
                return
            }
            try {
                const query = new URLSearchParams({ email: record.email })
                const data = await requestJson(`/api/accounts/login-otp/status?${query.toString()}`)
                applyLoginOtpStatus(data)
            } catch (error) {
                loginOtpStatusText.value = error.message || '验证码状态获取失败'
            }
        }

        /**
         * 开始轮询手填验证码状态。
         *
         * @author AI by zb
         */
        function startLoginOtpStatusPolling() {
            stopLoginOtpStatusPolling()
            loginOtpReady.value = false
            loginOtpStatusText.value = '正在等待验证码发送'
            loginOtpResendRemaining.value = 60
            refreshLoginOtpStatus()
            loginOtpStatusTimer = setInterval(refreshLoginOtpStatus, 1000)
        }

        /**
         * 请求后端取消当前手填验证码等待。
         *
         * @author AI by zb
         */
        async function cancelLoginOtpFlow(email) {
            if (!email) {
                return
            }
            try {
                await requestJson('/api/accounts/login-otp/cancel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                })
            } catch (error) {
                showError(error.message)
            }
        }

        /**
         * 打开单账号登录上传弹窗。
         *
         * @author AI by zb
         */
        function openLoginUploadModal(record) {
            if (!record || !record.email) {
                return
            }
            loginUploadRecord.value = record
            resetLoginUploadForm(record)
            loginUploadModalOpen.value = true
        }

        /**
         * 关闭单账号登录上传弹窗。
         *
         * @author AI by zb
         */
        async function closeLoginUploadModal() {
            const record = loginUploadRecord.value
            if (loginUploadSubmitting.value && loginUploadForm.otpMode !== 'manual') {
                showError('自动登录进行中，暂不支持中途取消')
                return
            }
            const shouldCancel = Boolean(record && record.email && loginUploadSubmitting.value)
            if (shouldCancel) {
                loginUploadCancelling.value = true
                loginUploadRequestSeq += 1
                await cancelLoginOtpFlow(record.email)
                loginUploadCancelling.value = false
            }
            stopLoginOtpStatusPolling()
            loginUploadSubmitting.value = false
            loginOtpSubmitting.value = false
            loginOtpResending.value = false
            loginUploadModalOpen.value = false
            loginUploadRecord.value = null
            resetLoginUploadForm()
        }

        /**
         * 提交单账号登录上传请求。
         *
         * @author AI by zb
         */
        async function submitLoginUpload() {
            if (loginUploadSubmitting.value) {
                return
            }
            const record = loginUploadRecord.value
            if (!record || !record.email) {
                return
            }
            const targets = Array.isArray(loginUploadForm.uploadTargets)
                ? loginUploadForm.uploadTargets
                : []
            if (!targets.length) {
                showError('请选择至少一个上传目标')
                return
            }

            const requestSeq = loginUploadRequestSeq + 1
            loginUploadRequestSeq = requestSeq
            loginUploadSubmitting.value = true
            if (loginUploadForm.otpMode === 'manual') {
                startLoginOtpStatusPolling()
            }
            const actionKey = buildActionKey('/api/accounts/login-sub2api', record.email)
            accountActionLoading[actionKey] = true
            try {
                const data = await requestJson('/api/accounts/login-sub2api', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        email: record.email,
                        otp_mode: loginUploadForm.otpMode,
                        upload_targets: targets
                    })
                })
                if (requestSeq !== loginUploadRequestSeq) {
                    return
                }
                if (!data || data.success !== false || data.cancelled) {
                    showSuccess(data && data.message ? data.message : '操作成功')
                } else {
                    showError(data.message || '操作失败')
                }
                await loadAccounts()
                if (data && data.success !== false) {
                    stopLoginOtpStatusPolling()
                    loginUploadModalOpen.value = false
                    loginUploadRecord.value = null
                    resetLoginUploadForm()
                }
            } catch (error) {
                if (requestSeq === loginUploadRequestSeq) {
                    showError(`${record.email}\n${error.message}`)
                }
            } finally {
                accountActionLoading[actionKey] = false
                if (requestSeq === loginUploadRequestSeq) {
                    loginUploadSubmitting.value = false
                    stopLoginOtpStatusPolling()
                }
            }
        }

        /**
         * 提交手填登录验证码。
         *
         * @author AI by zb
         */
        async function submitLoginOtp() {
            const record = loginUploadRecord.value
            const code = String(loginUploadForm.otpCode || '').trim()
            if (!record || !record.email) {
                return
            }
            if (!loginOtpReady.value) {
                showError('请等待验证码发送完成')
                return
            }
            if (!/^\d{6}$/.test(code)) {
                showError('请输入 6 位验证码')
                return
            }

            loginOtpSubmitting.value = true
            try {
                const data = await requestJson('/api/accounts/login-otp', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: record.email, code })
                })
                showSuccess(data && data.message ? data.message : '验证码已提交')
                loginUploadForm.otpCode = ''
            } catch (error) {
                showError(error.message)
            } finally {
                loginOtpSubmitting.value = false
            }
        }

        /**
         * 请求重发当前登录验证码。
         *
         * @author AI by zb
         */
        async function resendLoginOtp() {
            const record = loginUploadRecord.value
            if (!record || !record.email) {
                return
            }
            if (loginOtpResendRemaining.value > 0) {
                showError(`请等待 ${loginOtpResendRemaining.value} 秒后再重发`)
                return
            }
            loginOtpResending.value = true
            try {
                const data = await requestJson('/api/accounts/login-otp/resend', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: record.email })
                })
                applyLoginOtpStatus(data)
                showSuccess(data && data.message ? data.message : '验证码已重发')
            } catch (error) {
                showError(error.message)
                await refreshLoginOtpStatus()
            } finally {
                loginOtpResending.value = false
            }
        }

        async function handleLoginSub2Api(record) {
            if (!record || !record.email) {
                return
            }
            if (isRunning.value) {
                showError('任务运行中，请稍后再试')
                return
            }
            openLoginUploadModal(record)
        }

        async function handleDeleteAccount(record) {
            if (!record || !record.email) {
                return
            }
            const confirmed = window.confirm(`${record.email}\n确认删除这个账号吗？此操作不可撤销。`)
            if (!confirmed) {
                return
            }
            await runAccountAction('/api/accounts/delete', record.email)
        }

        async function handleAccountActionMenu(actionKey, record) {
            if (!record || !record.email) {
                return
            }
            setActionPopoverOpen(record, false)

            if (actionKey === 'viewDetail') {
                openAccountDetailModal(record)
                return
            }
            if (actionKey === 'loginSub2Api') {
                await handleLoginSub2Api(record)
                return
            }
            if (actionKey === 'uploadSub2Api') {
                await handleUploadSub2Api(record)
                return
            }
            if (actionKey === 'uploadTeamManage') {
                await handleUploadTeamManage(record)
                return
            }
            if (actionKey === 'exportAccount') {
                await exportSingleAccount(record)
                return
            }
            if (actionKey === 'deleteAccount') {
                await handleDeleteAccount(record)
            }
        }

        /**
         * 打开账号详情弹窗。
         *
         * @author AI by zb
         */
        function openAccountDetailModal(record) {
            if (!record || !record.email) {
                return
            }
            accountDetailRecord.value = record
            accountDetailModalOpen.value = true
        }

        /**
         * 关闭账号详情弹窗。
         *
         * @author AI by zb
         */
        function closeAccountDetailModal() {
            accountDetailModalOpen.value = false
            accountDetailRecord.value = null
        }

        /**
         * 构建账号详情弹窗分区数据。
         *
         * @author AI by zb
         */
        const accountDetailSections = computed(() => {
            const r = accountDetailRecord.value
            if (!r) return []
            const oauth = r.oauthTokens || r.hasOAuthTokens ? null : null
            return [
                {
                    title: '基本信息',
                    fields: [
                        { key: 'email', label: '邮箱', value: r.email },
                        { key: 'password', label: '密码', value: r.password },
                        { key: 'category', label: '分类', value: r.accountCategoryLabel },
                        { key: 'remark', label: '备注', value: r.remark },
                    ].filter(f => f.value)
                },
                {
                    title: '登录状态',
                    fields: [
                        { key: 'loginState', label: '登录状态', value: r.loginState === 'success' ? '成功' : r.loginState === 'failed' ? '失败' : '待验证' },
                        { key: 'loginMessage', label: '登录信息', value: r.loginMessage },
                        { key: 'loginVerifiedAt', label: '验证时间', value: r.loginVerifiedAt ? formatTimeCompact(r.loginVerifiedAt) : '' },
                    ].filter(f => f.value)
                },
                {
                    title: 'Sub2Api',
                    fields: [
                        { key: 'sub2apiState', label: '状态', value: r.sub2apiState === 'success' ? '已上传' : r.sub2apiState === 'failed' ? '失败' : r.sub2apiState === 'disabled' ? '未启用' : '待上传' },
                        { key: 'sub2apiMessage', label: '信息', value: r.sub2apiMessage },
                    ].filter(f => f.value)
                },
                {
                    title: 'Team 管理',
                    fields: [
                        { key: 'teamManageState', label: '状态', value: r.teamManageState === 'success' ? '已上传' : r.teamManageState === 'failed' ? '失败' : r.teamManageState === 'disabled' ? '未启用' : '待上传' },
                        { key: 'teamManageMessage', label: '信息', value: r.teamManageMessage },
                    ].filter(f => f.value)
                },
            ].filter(s => s.fields.length > 0)
        })

        async function handleLogout() {
            try {
                await requestJson('/api/auth/logout', { method: 'POST' })
                window.location.href = '/login'
            } catch (error) {
                showError(error.message)
            }
        }

        function handleMenuClick({ key }) {
            currentTab.value = key
            mobileMenuOpen.value = false
        }

        function resetAccountPagination() {
            accountPagination.current = 1
        }

        function getAccountRowKey(record) {
            return `${record.email || ''}-${record.time || ''}`
        }

        function getOverallTagColor(record) {
            const kind = classifyOverallStatus(record)
            if (kind === 'pending') {
                return 'blue'
            }
            if (kind === 'success') {
                return 'green'
            }
            if (kind === 'failed') {
                return 'red'
            }
            return 'default'
        }

        function getSub2ApiTagColor(record) {
            const kind = classifySub2ApiStatus(record)
            if (kind === 'success') {
                return 'cyan'
            }
            if (kind === 'failed') {
                return 'red'
            }
            if (kind === 'disabled') {
                return 'default'
            }
            return 'gold'
        }

        function getTeamManageTagColor(record) {
            const kind = classifyTeamManageStatus(record)
            if (kind === 'success') {
                return 'purple'
            }
            if (kind === 'failed') {
                return 'red'
            }
            if (kind === 'disabled') {
                return 'default'
            }
            return 'gold'
        }

        function paginationTotalText(total, range) {
            return `${range[0]}-${range[1]} / ${total} 条`
        }

        function getOverallReason(record) {
            return normalizeReasonText(record && record.lastError)
        }

        function getLoginTagColor(record) {
            const kind = classifyLoginStatus(record)
            if (kind === 'success') {
                return 'green'
            }
            if (kind === 'failed') {
                return 'red'
            }
            if (kind === 'disabled') {
                return 'default'
            }
            return 'blue'
        }

        function getLoginReason(record) {
            return normalizeReasonText(record && (record.loginMessage || record.lastError))
        }

        function getLoginStatusTone(record) {
            return resolveStatusTone(classifyLoginStatus(record))
        }

        function getSub2ApiReason(record) {
            return normalizeReasonText(record && record.sub2apiMessage)
        }

        function getTeamManageReason(record) {
            return normalizeReasonText(record && record.teamManageMessage)
        }

        function getOverallStatusTone(record) {
            return resolveStatusTone(classifyOverallStatus(record))
        }

        function getSub2ApiStatusTone(record) {
            return resolveStatusTone(classifySub2ApiStatus(record))
        }

        function getTeamManageStatusTone(record) {
            return resolveStatusTone(classifyTeamManageStatus(record))
        }

        function getStatusTooltipClass(tone) {
            return `status-tooltip status-tooltip-${tone || 'info'}`
        }

        function getPrimaryStatusLabel(record) {
            const kind = classifyLoginStatus(record)
            if (record && record.loginMessage && kind === 'failed') {
                return '登录失败'
            }
            if (kind === 'success') {
                return '登录成功'
            }
            if (kind === 'failed') {
                return '登录失败'
            }
            if (kind === 'disabled') {
                return '已跳过'
            }
            return '待验证'
        }

        function getPrimaryStatusReason(record) {
            return getLoginReason(record)
        }

        function getPrimaryStatusTone(record) {
            return getLoginStatusTone(record)
        }

        function getPrimaryTagColor(record) {
            return getLoginTagColor(record)
        }

        /**
         * 计算统计分组总量。
         *
         * @author AI by zb
         */
        function getDashboardGroupTotal(group) {
            const stats = group || {}
            return ['pending', 'success', 'failed', 'disabled']
                .map((key) => Number(stats[key] || 0))
                .reduce((total, value) => total + value, 0)
        }

        /**
         * 计算统计分组状态占比。
         *
         * @author AI by zb
         */
        function getDashboardPercent(group, key) {
            const total = getDashboardGroupTotal(group)
            if (!total) {
                return 0
            }
            return Math.round(Number(group && group[key] || 0) * 100 / total)
        }

        /**
         * 格式化统计中心成功率。
         *
         * @author AI by zb
         */
        function formatDashboardRate(value) {
            const rate = Number(value || 0)
            return `${Number.isInteger(rate) ? rate : rate.toFixed(1)}%`
        }

        /**
         * 生成最近异常的状态摘要。
         *
         * @author AI by zb
         */
        function getDashboardErrorStatusText(item) {
            if (!item) {
                return '状态异常'
            }
            if (item.loginState === 'failed') {
                return '登录失败'
            }
            if (item.sub2apiState === 'failed') {
                return 'Sub2Api 失败'
            }
            if (item.teamManageState === 'failed') {
                return 'Team 失败'
            }
            return '状态异常'
        }

        watch(
            () => [accountFilters.keyword, accountFilters.category, accountFilters.login, accountFilters.sub2api, accountFilters.teamManage],
            () => {
                if (currentTab.value !== 'accounts') {
                    return
                }
                if (accountPagination.current !== 1) {
                    accountPagination.current = 1
                    return
                }
                loadAccounts()
            }
        )

        watch(
            () => [accountPagination.current, accountPagination.pageSize],
            () => {
                if (currentTab.value === 'accounts') {
                    loadAccounts()
                }
            }
        )

        watch(
            () => logs.value.length,
            async () => {
                await nextTick()
                if (logContainerRef.value) {
                    logContainerRef.value.scrollTop = logContainerRef.value.scrollHeight
                }
            }
        )

        watch(currentTab, async (value) => {
            if (value === 'accounts') {
                await loadAccounts()
            }
        })

        onMounted(() => {
            startPolling()
        })

        onBeforeUnmount(() => {
            stopPolling()
            stopLoginOtpStatusPolling()
        })

        return {
            accountColumns,
            accountExporting,
            accountFilters,
            accountImportFileRef,
            accountImporting,
            accountPagination,
            accounts,
            accountsLoading,
            clearLogs,
            closeLoginUploadModal,
            currentAction,
            currentTab,
            copyText,
            closeManualAccountPanel,
            dashboardStats,
            exportFilteredAccounts,
            failCount,
            getAccountRowKey,
            getActionPopoverKey,
            formatDashboardRate,
            formatEmailCompact,
            formatPasswordCompact,
            formatTimeCompact,
            getDashboardErrorStatusText,
            getDashboardPercent,
            getOverallTagColor,
            getOverallReason,
            getOverallStatusTone,
            getPrimaryStatusLabel,
            getPrimaryStatusReason,
            getPrimaryStatusTone,
            getPrimaryTagColor,
            getLoginTagColor,
            getLoginReason,
            getLoginStatusTone,
            getStatusTooltipClass,
            getSub2ApiTagColor,
            getSub2ApiReason,
            getSub2ApiStatusTone,
            getTeamManageTagColor,
            getTeamManageReason,
            getTeamManageStatusTone,
            handleMenuClick,
            handleAccountActionMenu,
            handleDeleteAccount,
            handleGroupIdsBlur,
            handleImportJsonFileChange,
            handleLoginSub2Api,
            handleLogout,
            handleUploadSub2Api,
            handleUploadTeamManage,
            hasAccountActions,
            groupIdsInputFocused,
            isActionPopoverOpen,
            isAnyAccountActionRunning,
            isAccountActionRunning,
            isRunning,
            lastUpdate,
            loadAccounts,
            loginOtpReady,
            loginOtpResending,
            loginOtpResendRemaining,
            loginOtpSubmitting,
            loginOtpStatusText,
            loginUploadCancelling,
            loginUploadForm,
            loginUploadModalOpen,
            loginUploadRecord,
            loginUploadSubmitting,
            logContainerRef,
            logs,
            manualAccountForm,
            manualAccountSubmitting,
            mobileMenuOpen,
            pageSizeOptions,
            pagedAccounts,
            paginationTotalText,
            resetAccountPagination,
            resetManualAccountForm,
            resendLoginOtp,
            runAccountAction,
            saveAutomationSettings,
            settings,
            settingsSaving,
            setActionPopoverOpen,
            showManualAccountPanel,
            startTask,
            stopTask,
            submitLoginOtp,
            submitLoginUpload,
            submitManualAccount,
            successCount,
            targetCount,
            toggleManualAccountPanel,
            totalAccountPages,
            totalInventory,
            triggerImportJsonFile,
            accountDetailModalOpen,
            accountDetailRecord,
            accountDetailSections,
            closeAccountDetailModal,
            openAccountDetailModal
        }
    }
})

if (window.IconsVue) {
    Object.entries(window.IconsVue).forEach(([name, component]) => {
        app.component(name, component)
    })
}

if (antPlugin && typeof antPlugin.install === 'function') {
    app.use(antPlugin)
} else {
    registerAntComponents(app)
}
app.mount('#app')
