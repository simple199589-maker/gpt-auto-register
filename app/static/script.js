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
        const monitorUrl = ref('')
        const hasFrame = ref(false)
        const frameVersion = ref(-1)
        const isStreamingMonitor = ref(false)
        const settingsSaving = ref(false)
        const groupIdsInputFocused = ref(false)
        const accountsLoading = ref(false)
        const accounts = ref([])
        const logContainerRef = ref(null)
        const accountActionLoading = reactive({})
        const actionPopoverOpen = reactive({})
        const showManualAccountPanel = ref(false)
        const manualAccountSubmitting = ref(false)
        const manualAccountForm = reactive({
            email: '',
            password: '',
            accountCategory: 'normal'
        })
        const loginUploadModalOpen = ref(false)
        const loginUploadRecord = ref(null)
        const loginUploadSubmitting = ref(false)
        const loginOtpSubmitting = ref(false)
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

        const monitorStatusText = computed(() => {
            if (isRunning.value) {
                return hasFrame.value ? 'LIVE' : 'SYNCING'
            }
            if (monitorUrl.value) {
                return 'IDLE'
            }
            return 'OFFLINE'
        })

        const monitorStatusColor = computed(() => {
            if (isRunning.value && hasFrame.value) {
                return 'green'
            }
            if (isRunning.value) {
                return 'blue'
            }
            if (monitorUrl.value) {
                return 'gold'
            }
            return 'default'
        })

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

        function updateMonitorState(data) {
            hasFrame.value = Boolean(data && data.has_frame)
            frameVersion.value = Number.isInteger(data && data.frame_version) ? data.frame_version : -1

            if (isRunning.value || hasFrame.value) {
                if (isRunning.value) {
                    if (!isStreamingMonitor.value || !includesAnyKeyword(monitorUrl.value, '/video_feed')) {
                        monitorUrl.value = `/video_feed?ts=${Date.now()}`
                        isStreamingMonitor.value = true
                    }
                } else {
                    isStreamingMonitor.value = false
                    if (hasFrame.value) {
                        monitorUrl.value = `/api/frame?v=${frameVersion.value}`
                    }
                }
                return
            }

            monitorUrl.value = ''
            isStreamingMonitor.value = false
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
                updateMonitorState(data)

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

        async function loadAccounts() {
            accountsLoading.value = true
            try {
                const query = new URLSearchParams({
                    page: String(accountPagination.current),
                    page_size: String(accountPagination.pageSize),
                    keyword: String(accountFilters.keyword || '').trim(),
                    account_category: accountFilters.category === 'all' ? '' : accountFilters.category,
                    login_status: accountFilters.login === 'all' ? '' : accountFilters.login,
                    sub2api_status: accountFilters.sub2api === 'all' ? '' : accountFilters.sub2api,
                    team_manage_status: accountFilters.teamManage === 'all' ? '' : accountFilters.teamManage,
                })
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
                    body: JSON.stringify({ email, password, account_category: accountCategory })
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
                '/api/accounts/delete'
            ].some((url) => isAccountActionRunning(url, email))
        }

        function hasAccountActions(record) {
            return Boolean(
                record
                && (
                    record.canLoginSub2api
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
        function closeLoginUploadModal() {
            if (loginUploadSubmitting.value) {
                return
            }
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

            loginUploadSubmitting.value = true
            try {
                const data = await runAccountAction('/api/accounts/login-sub2api', record.email, {
                    otp_mode: loginUploadForm.otpMode,
                    upload_targets: targets
                })
                if (data && data.success !== false) {
                    loginUploadModalOpen.value = false
                    loginUploadRecord.value = null
                    resetLoginUploadForm()
                }
            } finally {
                loginUploadSubmitting.value = false
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
            if (actionKey === 'deleteAccount') {
                await handleDeleteAccount(record)
            }
        }

        function handleMenuClick({ key }) {
            currentTab.value = key
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
        })

        return {
            accountColumns,
            accountFilters,
            accountPagination,
            accounts,
            accountsLoading,
            clearLogs,
            closeLoginUploadModal,
            currentAction,
            currentTab,
            copyText,
            closeManualAccountPanel,
            failCount,
            getAccountRowKey,
            getActionPopoverKey,
            formatEmailCompact,
            formatPasswordCompact,
            formatTimeCompact,
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
            handleLoginSub2Api,
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
            loginOtpSubmitting,
            loginUploadForm,
            loginUploadModalOpen,
            loginUploadRecord,
            loginUploadSubmitting,
            logContainerRef,
            logs,
            manualAccountForm,
            manualAccountSubmitting,
            monitorStatusColor,
            monitorStatusText,
            monitorUrl,
            pageSizeOptions,
            pagedAccounts,
            paginationTotalText,
            resetAccountPagination,
            resetManualAccountForm,
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
            totalInventory
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
