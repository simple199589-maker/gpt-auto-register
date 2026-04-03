const { createApp, reactive, ref, computed, onMounted, onBeforeUnmount, watch, nextTick } = Vue

const antNamespace = window.antd || window.Antd || {}
const antPlugin = antNamespace && antNamespace.default && antNamespace.default.install
    ? antNamespace.default
    : antNamespace
const antMessage = antNamespace.message || (antPlugin && antPlugin.message) || null

function registerAntComponents(appInstance) {
    const menuComponent = antNamespace.Menu || (antPlugin && antPlugin.Menu)
    const selectComponent = antNamespace.Select || (antPlugin && antPlugin.Select)
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

const DELIVERY_VENDOR_STORAGE_KEY = 'gpt-auto-register.delivery-vendor'

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

function classifyPlusStatus(record) {
    if (record && record.plusState) {
        return String(record.plusState)
    }
    const plusStatus = String(record && record.plusStatus || '')

    if (record && record.plusSuccess) {
        return 'success'
    }
    if (plusStatus.includes('关闭') || plusStatus.includes('跳过')) {
        return 'disabled'
    }
    if (plusStatus.includes('处理中') || plusStatus.includes('取消中') || plusStatus.includes('已提交')) {
        return 'pending'
    }
    if (!record || (!record.plusCalled && !plusStatus)) {
        return 'idle'
    }
    if (record.plusCalled && !record.plusSuccess) {
        return 'failed'
    }
    return 'idle'
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
        const lastActivationRefreshAt = ref(0)
        const manualAccountForm = reactive({
            email: '',
            password: '',
            accessToken: ''
        })
        const deliverySettings = reactive({
            vendor: window.localStorage.getItem(DELIVERY_VENDOR_STORAGE_KEY) || '咸鱼'
        })
        const serverSettings = reactive({
            plus_auto_activate_enabled: false,
            sub2api_auto_upload_enabled: false,
            sub2api_group_ids: []
        })
        const settings = reactive({
            plus_auto_activate_enabled: false,
            sub2api_auto_upload_enabled: false,
            sub2api_group_ids: [],
            sub2api_group_ids_text: ''
        })
        const accountFilters = reactive({
            keyword: '',
            registration: 'all',
            overall: 'all',
            plus: 'all',
            sub2api: 'all'
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
            { title: '状态', dataIndex: 'status', key: 'status', width: 154 },
            { title: '上传', key: 'sub2api', width: 128 },
            { title: '时间', dataIndex: 'time', key: 'time', width: 116 },
            { title: '', key: 'actions', width: 64, fixed: 'right' }
        ]

        function persistDeliverySettings() {
            window.localStorage.setItem(DELIVERY_VENDOR_STORAGE_KEY, String(deliverySettings.vendor || '').trim() || '咸鱼')
        }

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
            serverSettings.plus_auto_activate_enabled = Boolean(data && data.plus_auto_activate_enabled)
            serverSettings.sub2api_auto_upload_enabled = Boolean(data && data.sub2api_auto_upload_enabled)
            serverSettings.sub2api_group_ids = Array.isArray(data && data.sub2api_group_ids)
                ? data.sub2api_group_ids.map((item) => Number(item)).filter((item) => Number.isInteger(item))
                : []

            if (!settingsSaving.value) {
                settings.plus_auto_activate_enabled = serverSettings.plus_auto_activate_enabled
                settings.sub2api_auto_upload_enabled = serverSettings.sub2api_auto_upload_enabled
                settings.sub2api_group_ids = [...serverSettings.sub2api_group_ids]
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

                if (currentTab.value === 'accounts' && !accountsLoading.value && !isActivationPipelineBusy()) {
                    const now = Date.now()
                    if (now - Number(lastActivationRefreshAt.value || 0) >= 5000) {
                        lastActivationRefreshAt.value = now
                        void refreshPendingActivationStatuses(true)
                    }
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

        /**
         * 判断当前页面是否已有手动 Plus / Team 激活线路在执行。
         *
         * @author AI by zb
         */
        function isActivationPipelineBusy() {
            const action = String(currentAction.value || '').trim().toLowerCase()
            if (!action) {
                return false
            }
            const actionLabel = action.split(':', 1)[0].split('：', 1)[0]
            return (
                actionLabel.includes('plus')
                || actionLabel.includes('team')
                || actionLabel.includes('激活')
            )
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
                settings.plus_auto_activate_enabled = serverSettings.plus_auto_activate_enabled
                settings.sub2api_auto_upload_enabled = serverSettings.sub2api_auto_upload_enabled
                settings.sub2api_group_ids = [...serverSettings.sub2api_group_ids]
                settings.sub2api_group_ids_text = serverSettings.sub2api_group_ids.join(',')
                showError('任务运行中，请先停止后再修改设置')
                return
            }

            settingsSaving.value = true
            try {
                const groupIds = parseGroupIdsInput(settings.sub2api_group_ids_text)
                const payload = {
                    plus_auto_activate_enabled: Boolean(settings.plus_auto_activate_enabled),
                    sub2api_auto_upload_enabled: Boolean(settings.sub2api_auto_upload_enabled),
                    sub2api_group_ids: groupIds.length ? groupIds : [...serverSettings.sub2api_group_ids]
                }
                const data = await requestJson('/api/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                })
                syncSettings(data)
                settings.sub2api_group_ids_text = serverSettings.sub2api_group_ids.join(',')
                showSuccess('设置已保存')
            } catch (error) {
                settings.plus_auto_activate_enabled = serverSettings.plus_auto_activate_enabled
                settings.sub2api_auto_upload_enabled = serverSettings.sub2api_auto_upload_enabled
                settings.sub2api_group_ids = [...serverSettings.sub2api_group_ids]
                settings.sub2api_group_ids_text = serverSettings.sub2api_group_ids.join(',')
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
                    registration_status: accountFilters.registration === 'all' ? '' : accountFilters.registration,
                    overall_status: accountFilters.overall === 'all' ? '' : accountFilters.overall,
                    plus_status: accountFilters.plus === 'all' ? '' : accountFilters.plus,
                    sub2api_status: accountFilters.sub2api === 'all' ? '' : accountFilters.sub2api,
                })
                const data = await requestJson(`/api/accounts?${query.toString()}`)
                accounts.value = Array.isArray(data && data.items) ? data.items : []
                accountPagination.total = Number(data && data.pagination && data.pagination.total || 0)
                accountPagination.totalPages = Number(data && data.pagination && data.pagination.total_pages || 1)
                if (accountPagination.current > accountPagination.totalPages) {
                    accountPagination.current = accountPagination.totalPages
                    return
                }
                if (!isActivationPipelineBusy()) {
                    lastActivationRefreshAt.value = Date.now()
                    void refreshPendingActivationStatuses(true)
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
         * 判断指定账号是否需要继续刷新激活状态。
         *
         * @author AI by zb
         */
        function shouldRefreshActivationStatus(record) {
            const requestId = String(record && record.plusRequestId || '').trim()
            const plusState = String(record && record.plusState || '').trim().toLowerCase()
            const plusStatus = String(record && record.plusStatus || '').trim()

            if (!record || !record.email || !requestId) {
                return false
            }
            return (
                plusState === 'pending'
                || plusStatus.includes('处理中')
                || plusStatus.includes('取消中')
                || plusStatus.includes('已提交')
            )
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
         * 按 requestId 刷新单个账号的激活状态。
         *
         * @author AI by zb
         */
        async function refreshActivationStatus(record, silent = true) {
            if (!shouldRefreshActivationStatus(record)) {
                return
            }

            const email = String(record && record.email || '').trim()
            const actionKey = buildActionKey('/api/accounts/refresh-activation', email)
            if (accountActionLoading[actionKey]) {
                return
            }

            accountActionLoading[actionKey] = true
            try {
                const data = await requestJson('/api/accounts/refresh-activation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email })
                })
                if (data && data.account) {
                    mergeAccountRecord(data.account)
                }
            } catch (error) {
                if (!silent) {
                    showError(`${email}\n${error.message}`)
                }
            } finally {
                accountActionLoading[actionKey] = false
            }
        }

        /**
         * 批量刷新当前列表中处于处理中状态的激活任务。
         *
         * @author AI by zb
         */
        async function refreshPendingActivationStatuses(silent = true) {
            const pendingRecords = accounts.value.filter((record) => shouldRefreshActivationStatus(record))
            for (const record of pendingRecords) {
                await refreshActivationStatus(record, silent)
            }
        }

        /**
         * 重置手动新增账号表单。
         *
         * @author AI by zb
         */
        function resetManualAccountForm() {
            manualAccountForm.email = ''
            manualAccountForm.password = ''
            manualAccountForm.accessToken = ''
        }

        /**
         * 关闭手动新增账号面板并清空输入。
         *
         * @author AI by zb
         */
        function closeManualAccountPanel() {
            showManualAccountPanel.value = false
            resetManualAccountForm()
        }

        /**
         * 切换手动新增账号面板显示状态。
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
         * 提交手动新增账号请求。
         *
         * @author AI by zb
         */
        async function submitManualAccount() {
            const email = String(manualAccountForm.email || '').trim().toLowerCase()
            const password = String(manualAccountForm.password || '').trim()
            const accessToken = String(manualAccountForm.accessToken || '').trim()

            if (!email) {
                showError('请输入账号邮箱')
                return
            }
            if (!password && !accessToken) {
                showError('密码和 accessToken 至少填写一项')
                return
            }

            manualAccountSubmitting.value = true
            try {
                const data = await requestJson('/api/accounts/create', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password, accessToken })
                })

                showSuccess(data && data.message ? data.message : '账号已添加')
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
                '/api/accounts/deliver',
                '/api/accounts/access-token',
                '/api/accounts/update-status',
                '/api/accounts/retry-registration',
                '/api/accounts/retry-plus',
                '/api/accounts/retry-team',
                '/api/accounts/cancel-activation',
                '/api/accounts/upload-sub2api',
                '/api/accounts/delete'
            ].some((url) => isAccountActionRunning(url, email))
        }

        function isActivationRetryRunning(record) {
            const email = record && record.email ? record.email : ''
            if (!email) {
                return false
            }
            return (
                isAccountActionRunning('/api/accounts/retry-plus', email)
                || isAccountActionRunning('/api/accounts/retry-team', email)
            )
        }

        function isActivationCurrentAction(record) {
            const email = String(record && record.email || '').trim().toLowerCase()
            const action = String(currentAction.value || '').trim().toLowerCase()
            if (!email || !action || !action.includes(email)) {
                return false
            }
            const actionLabel = action.split(':', 1)[0].split('：', 1)[0]
            return (
                actionLabel.includes('plus')
                || actionLabel.includes('team')
                || actionLabel.includes('激活')
            )
        }

        function shouldShowCancelActivation(record) {
            return Boolean(
                record
                && record.email
                && (isActivationRetryRunning(record) || isActivationCurrentAction(record))
            )
        }

        function hasAccountActions(record) {
            return Boolean(
                record
                && (
                    record.canDeliver
                    || record.canEditStatus
                    || record.canDeleteAccount
                    || record.canCopyAccessToken
                    || record.canRetryRegistration
                    || record.canRetryPlus
                    || record.canRetryTeam
                    || record.canUploadSub2api
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

        async function handleDeliverAccount(record) {
            if (!record || !record.email) {
                return
            }

            const vendor = String(deliverySettings.vendor || '').trim() || '咸鱼'
            const deliveryEmail = String(record.email || '').trim().toLowerCase()

            const confirmed = window.confirm(`${record.email}\n将向 ${deliveryEmail} 发货，厂家标记为 ${vendor}，确认继续吗？`)
            if (!confirmed) {
                return
            }

            persistDeliverySettings()
            const data = await runAccountAction('/api/accounts/deliver', record.email, { vendor })
            if (data && data.tempAccessUrl) {
                const openedWindow = window.open(data.tempAccessUrl, '_blank', 'noopener')
                if (!openedWindow) {
                    showError('发货已完成，但浏览器拦截了临时链接弹窗，请允许弹窗后重试')
                }
            }
        }

        async function handleCopyAccessToken(record) {
            if (!record || !record.email) {
                return
            }

            const actionKey = buildActionKey('/api/accounts/access-token', record.email)
            accountActionLoading[actionKey] = true

            try {
                const data = await requestJson('/api/accounts/access-token', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email: record.email })
                })
                await copyText(data && data.accessToken ? data.accessToken : '', 'accessToken')
            } catch (error) {
                showError(`${record.email}\n${error.message}`)
            } finally {
                accountActionLoading[actionKey] = false
            }
        }

        async function handleEditAccountStatus(record) {
            if (!record || !record.email) {
                return
            }
            const currentStatus = String(getPrimaryStatusLabel(record) || record.status || '').trim()
            const nextStatus = window.prompt(`${record.email}\n请输入新的账号状态`, currentStatus)
            if (nextStatus === null) {
                return
            }
            const normalizedStatus = String(nextStatus || '').trim()
            if (!normalizedStatus) {
                showError('状态不能为空')
                return
            }
            await runAccountAction('/api/accounts/update-status', record.email, { status: normalizedStatus })
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

        async function handleCancelActivation(record) {
            if (!record || !record.email) {
                return
            }
            const confirmed = window.confirm(`${record.email}\n确认取消当前 Plus / Team 激活任务吗？`)
            if (!confirmed) {
                return
            }
            await runAccountAction('/api/accounts/cancel-activation', record.email)
        }

        async function handleAccountActionMenu(actionKey, record) {
            if (!record || !record.email) {
                return
            }
            setActionPopoverOpen(record, false)

            if (actionKey === 'editStatus') {
                await handleEditAccountStatus(record)
                return
            }
            if (actionKey === 'retryRegistration') {
                await runAccountAction('/api/accounts/retry-registration', record.email)
                return
            }
            if (actionKey === 'copyAccessToken') {
                await handleCopyAccessToken(record)
                return
            }
            if (actionKey === 'deliver') {
                await handleDeliverAccount(record)
                return
            }
            if (actionKey === 'retryPlus') {
                await runAccountAction('/api/accounts/retry-plus', record.email)
                return
            }
            if (actionKey === 'retryTeam') {
                await runAccountAction('/api/accounts/retry-team', record.email)
                return
            }
            if (actionKey === 'uploadSub2Api') {
                await handleUploadSub2Api(record)
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

        function getPlusTagColor(record) {
            const kind = classifyPlusStatus(record)
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

        function paginationTotalText(total, range) {
            return `${range[0]}-${range[1]} / ${total} 条`
        }

        function getOverallReason(record) {
            return normalizeReasonText(record && record.lastError)
        }

        function getPlusReason(record) {
            return normalizeReasonText(record && record.plusMessage)
        }

        function getSub2ApiReason(record) {
            return normalizeReasonText(record && record.sub2apiMessage)
        }

        function getOverallStatusTone(record) {
            return resolveStatusTone(classifyOverallStatus(record))
        }

        function getPlusStatusTone(record) {
            return resolveStatusTone(classifyPlusStatus(record))
        }

        function getSub2ApiStatusTone(record) {
            return resolveStatusTone(classifySub2ApiStatus(record))
        }

        function getStatusTooltipClass(tone) {
            return `status-tooltip status-tooltip-${tone || 'info'}`
        }

        function shouldUsePrimaryPlusStatus(record) {
            return classifyPlusStatus(record) !== 'idle'
        }

        function getPrimaryStatusLabel(record) {
            if (shouldUsePrimaryPlusStatus(record)) {
                return record && record.plusStatus
                    ? record.plusStatus
                    : (record && record.plusCalled ? '失败' : '未调用')
            }
            return (record && record.status) || '待处理'
        }

        function getPrimaryStatusReason(record) {
            if (shouldUsePrimaryPlusStatus(record)) {
                return getPlusReason(record) || getOverallReason(record)
            }
            return getOverallReason(record)
        }

        function getPrimaryStatusTone(record) {
            return shouldUsePrimaryPlusStatus(record)
                ? getPlusStatusTone(record)
                : getOverallStatusTone(record)
        }

        function getPrimaryTagColor(record) {
            return shouldUsePrimaryPlusStatus(record)
                ? getPlusTagColor(record)
                : getOverallTagColor(record)
        }

        watch(
            () => [deliverySettings.vendor],
            () => {
                persistDeliverySettings()
            }
        )

        watch(
            () => [accountFilters.keyword, accountFilters.registration, accountFilters.overall, accountFilters.plus, accountFilters.sub2api],
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
            currentAction,
            currentTab,
            copyText,
            closeManualAccountPanel,
            deliverySettings,
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
            getPlusTagColor,
            getPlusReason,
            getPlusStatusTone,
            getStatusTooltipClass,
            getSub2ApiTagColor,
            getSub2ApiReason,
            getSub2ApiStatusTone,
            handleMenuClick,
            handleAccountActionMenu,
            handleCancelActivation,
            handleCopyAccessToken,
            handleDeleteAccount,
            handleEditAccountStatus,
            handleGroupIdsBlur,
            handleUploadSub2Api,
            hasAccountActions,
            groupIdsInputFocused,
            isActionPopoverOpen,
            isAnyAccountActionRunning,
            isAccountActionRunning,
            shouldShowCancelActivation,
            isRunning,
            lastUpdate,
            loadAccounts,
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
