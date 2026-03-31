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
            } catch (error) {
                showError(error.message)
                accounts.value = []
                accountPagination.total = 0
                accountPagination.totalPages = 1
            } finally {
                accountsLoading.value = false
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
                    record.canEditStatus
                    || record.canDeleteAccount
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
            monitorStatusColor,
            monitorStatusText,
            monitorUrl,
            pageSizeOptions,
            pagedAccounts,
            paginationTotalText,
            resetAccountPagination,
            runAccountAction,
            saveAutomationSettings,
            settings,
            settingsSaving,
            setActionPopoverOpen,
            startTask,
            stopTask,
            successCount,
            targetCount,
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
