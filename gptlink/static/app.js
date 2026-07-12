const $ = selector => document.querySelector(selector)
const $$ = selector => [...document.querySelectorAll(selector)]

const ui = {
  accountPill: $('#accountPill'), accountLabel: $('#accountLabel'), refresh: $('#refreshButton'),
  login: $('#loginButton'), logout: $('#logoutButton'), form: $('#generateForm'), prompt: $('#prompt'),
  quality: $('#quality'), outputFormat: $('#outputFormat'), imageCount: $('#imageCount'),
  background: $('#background'), moderation: $('#moderation'), partialImages: $('#partialImages'),
  compressionField: $('#compressionField'), compression: $('#compression'), compressionValue: $('#compressionValue'),
  referenceSection: $('#referenceSection'), referenceInput: $('#referenceInput'), referenceDropzone: $('#referenceDropzone'),
  referencePreview: $('#referencePreview'), maskInput: $('#maskInput'), maskLabel: $('#maskLabel'),
  customSize: $('#customSize'), customWidth: $('#customWidth'), customHeight: $('#customHeight'),
  generate: $('#generateButton'), formMessage: $('#formMessage'), emptyResult: $('#emptyResult'),
  loadingResult: $('#loadingResult'), loadingText: $('#loadingText'), resultGrid: $('#resultGrid'),
  resultMeta: $('#resultMeta'), createKey: $('#createKeyButton'), keyList: $('#keyList'),
  newKeyReveal: $('#newKeyReveal'), newKeyValue: $('#newKeyValue'), copyKey: $('#copyKeyButton'),
  copyCode: $('#copyCodeButton'), codeExample: $('#codeExample'), history: $('#imageHistory'), toast: $('#toast')
}

let mode = 'create'
let selectedRatio = 'auto'
let referenceFiles = []
let maskFile = null
let currentApiKey = localStorage.getItem('gptlinkApiKey') || ''
let toastTimer

function toast(message) {
  ui.toast.textContent = message
  ui.toast.classList.add('visible')
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => ui.toast.classList.remove('visible'), 2600)
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error?.message || body.detail || `Request failed (${response.status})`)
  return body
}

function findPercentage(value) {
  if (!value || typeof value !== 'object') return null
  for (const [key, child] of Object.entries(value)) {
    if (['usedPercent', 'used_percent', 'percentUsed', 'percent_used'].includes(key) && typeof child === 'number') return Math.max(0, Math.min(100, child))
    const nested = findPercentage(child)
    if (nested !== null) return nested
  }
  return null
}

async function loadStatus() {
  ui.refresh.disabled = true
  try {
    const status = await requestJson('/api/status')
    const account = status.codex?.account || status.codex
    const connected = account?.type === 'chatgpt'
    ui.accountPill.classList.toggle('connected', connected)
    ui.accountPill.classList.remove('loading')
    if (connected) {
      const remaining = findPercentage(status.rate_limits)
      ui.accountLabel.textContent = `${String(account.planType || 'ChatGPT').toUpperCase()}${remaining === null ? '' : ` · ${Math.round(100 - remaining)}% left`}`
      ui.login.classList.add('hidden')
      ui.logout.classList.remove('hidden')
    } else {
      ui.accountLabel.textContent = 'Not connected'
      ui.login.classList.remove('hidden')
      ui.logout.classList.add('hidden')
    }
  } catch (error) {
    ui.accountLabel.textContent = 'Connection error'
    ui.login.classList.remove('hidden')
  } finally { ui.refresh.disabled = false }
}

async function beginLogin() {
  const result = await requestJson('/api/auth/login', { method: 'POST' })
  const url = result.authUrl || result.auth_url
  if (!url) throw new Error('Codex did not return a login URL')
  window.open(url, '_blank', 'noopener')
  toast('Finish signing in, then return here.')
  const polling = setInterval(loadStatus, 2500)
  setTimeout(() => clearInterval(polling), 180000)
}

function setMode(nextMode) {
  mode = nextMode
  $$('.mode-tab').forEach(button => button.classList.toggle('active', button.dataset.mode === mode))
  ui.referenceSection.classList.toggle('hidden', mode !== 'edit')
}

function setRatio(ratio) {
  selectedRatio = ratio
  $$('.choice').forEach(button => button.classList.toggle('active', button.dataset.ratio === ratio))
  ui.customSize.classList.toggle('hidden', ratio !== 'custom')
}

function renderReferences() {
  ui.referencePreview.innerHTML = ''
  referenceFiles.forEach((file, index) => {
    const chip = document.createElement('div')
    chip.className = 'file-chip'
    chip.innerHTML = `<img alt="Reference ${index + 1}"><button type="button" aria-label="Remove reference">×</button>`
    chip.querySelector('img').src = URL.createObjectURL(file)
    chip.querySelector('button').addEventListener('click', () => {
      referenceFiles = referenceFiles.filter((_, itemIndex) => itemIndex !== index)
      renderReferences()
    })
    ui.referencePreview.append(chip)
  })
}

function addReferences(files) {
  const imageFiles = [...files].filter(file => file.type.startsWith('image/'))
  referenceFiles = [...referenceFiles, ...imageFiles].slice(0, 16)
  renderReferences()
}

function selectedSize() {
  const ratioSizes = { auto: 'auto', '1:1': '1024x1024', '16:9': '1536x864', '9:16': '864x1536', '4:3': '1152x864', '3:2': '1248x832' }
  if (selectedRatio === 'custom') return `${ui.customWidth.value}x${ui.customHeight.value}`
  return ratioSizes[selectedRatio]
}

function generationOptions() {
  const format = ui.outputFormat.value
  return {
    model: 'gpt-image-2', n: Number(ui.imageCount.value), size: selectedSize(),
    quality: ui.quality.value, output_format: format, background: ui.background.value,
    moderation: ui.moderation.value, partial_images: Number(ui.partialImages.value),
    stream: true, response_format: 'url',
    ...(format === 'png' ? {} : { output_compression: Number(ui.compression.value) })
  }
}

function buildRequest() {
  const options = generationOptions()
  if (mode === 'create') {
    return {
      url: '/v1/images/generations',
      options: {
        method: 'POST',
        headers: { Authorization: `Bearer ${currentApiKey}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: ui.prompt.value.trim(), ...options })
      }
    }
  }
  if (!referenceFiles.length) throw new Error('Add at least one reference image.')
  const form = new FormData()
  referenceFiles.forEach(file => form.append('image', file))
  if (maskFile) form.append('mask', maskFile)
  form.append('prompt', ui.prompt.value.trim())
  Object.entries(options).forEach(([key, value]) => form.append(key, String(value)))
  return { url: '/v1/images/edits', options: { method: 'POST', headers: { Authorization: `Bearer ${currentApiKey}` }, body: form } }
}

function setGenerating(generating) {
  ui.generate.disabled = generating
  ui.generate.querySelector('span').textContent = generating ? 'Generating…' : 'Generate'
  ui.emptyResult.classList.toggle('hidden', generating)
  ui.loadingResult.classList.toggle('hidden', !generating)
  if (generating) {
    ui.resultGrid.innerHTML = ''
    ui.resultGrid.classList.add('hidden')
    ui.resultMeta.textContent = ''
  }
}

function showResultImage(index, source, label) {
  let item = ui.resultGrid.querySelector(`[data-index="${index}"]`)
  if (!item) {
    item = document.createElement('a')
    item.className = 'result-item'
    item.dataset.index = index
    item.target = '_blank'
    item.rel = 'noopener'
    item.innerHTML = '<img alt="Generated image"><span></span>'
    ui.resultGrid.append(item)
  }
  item.href = source
  item.querySelector('img').src = source
  item.querySelector('span').textContent = label
  ui.resultGrid.classList.remove('hidden')
  ui.resultGrid.classList.toggle('single', Number(ui.imageCount.value) === 1)
  ui.loadingResult.classList.add('hidden')
}

async function consumeImageStream(response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.error?.message || `Generation failed (${response.status})`)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let completed = 0
  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''
    for (const chunk of chunks) {
      const dataLine = chunk.split('\n').find(line => line.startsWith('data:'))
      if (!dataLine) continue
      const raw = dataLine.slice(5).trim()
      if (raw === '[DONE]') continue
      const event = JSON.parse(raw)
      if (event.type === 'error') throw new Error(event.error?.message || 'Generation failed')
      if (event.type === 'image_generation.partial_image') {
        ui.loadingText.textContent = `Preview ${event.partial_image_index + 1} received`
        showResultImage(event.output_index, `data:image/png;base64,${event.b64_json}`, 'Preview')
      }
      if (event.type === 'image_generation.completed') {
        const source = event.url || `data:image/${event.output_format || 'png'};base64,${event.b64_json}`
        showResultImage(event.output_index, source, 'Final')
        completed += 1
        ui.resultMeta.textContent = `${completed} of ${ui.imageCount.value} complete`
      }
    }
    if (done) break
  }
}

async function generate(event) {
  event.preventDefault()
  ui.formMessage.classList.add('hidden')
  if (!currentApiKey) {
    ui.formMessage.textContent = 'Create a local API key first.'
    ui.formMessage.classList.remove('hidden')
    return
  }
  try {
    const request = buildRequest()
    setGenerating(true)
    const response = await fetch(request.url, request.options)
    await consumeImageStream(response)
    toast('Generation complete.')
    await loadHistory()
  } catch (error) {
    ui.formMessage.textContent = error.message
    ui.formMessage.classList.remove('hidden')
    if (!ui.resultGrid.children.length) ui.emptyResult.classList.remove('hidden')
  } finally {
    setGenerating(false)
    if (ui.resultGrid.children.length) ui.emptyResult.classList.add('hidden')
  }
}

async function loadKeys() {
  const { data } = await requestJson('/api/keys')
  ui.keyList.innerHTML = ''
  if (!data.length) {
    ui.keyList.innerHTML = '<p class="empty-history">No API keys yet.</p>'
    return
  }
  data.forEach(key => {
    const row = document.createElement('div')
    row.className = `key-row${key.revoked_at ? ' revoked' : ''}`
    row.innerHTML = `<div><strong>${escapeHtml(key.name)}</strong><code>${escapeHtml(key.prefix)}••••••••</code></div>`
    if (!key.revoked_at) {
      const button = document.createElement('button')
      button.className = 'revoke-button'
      button.textContent = 'Revoke'
      button.addEventListener('click', async () => { await requestJson(`/api/keys/${key.id}`, { method: 'DELETE' }); await loadKeys(); toast('Key revoked.') })
      row.append(button)
    }
    ui.keyList.append(row)
  })
}

async function createKey() {
  const payload = await requestJson('/api/keys', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Local app' }) })
  currentApiKey = payload.data.secret
  localStorage.setItem('gptlinkApiKey', currentApiKey)
  ui.newKeyValue.textContent = currentApiKey
  ui.newKeyReveal.classList.remove('hidden')
  updateCode()
  await loadKeys()
}

function updateCode() {
  const key = currentApiKey || 'YOUR_GPTLINK_KEY'
  ui.codeExample.textContent = `from openai import OpenAI\n\nclient = OpenAI(\n    api_key="${key}",\n    base_url="http://127.0.0.1:8787/v1",\n)\n\nresult = client.images.generate(\n    model="gpt-image-2",\n    prompt="A quiet modern workspace",\n    size="1536x864",\n    quality="high",\n)`
}

async function loadHistory() {
  const { data } = await requestJson('/api/images')
  ui.history.innerHTML = ''
  if (!data.length) {
    ui.history.innerHTML = '<p class="empty-history">No generated images yet.</p>'
    return
  }
  data.forEach(image => {
    const link = document.createElement('a')
    link.className = 'history-item'
    link.href = image.url
    link.target = '_blank'
    link.rel = 'noopener'
    link.innerHTML = `<img src="${image.url}" alt="${escapeHtml(image.prompt)}" loading="lazy"><span class="history-meta">${escapeHtml(image.prompt)}</span>`
    ui.history.append(link)
  })
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character])
}

$$('.mode-tab').forEach(button => button.addEventListener('click', () => setMode(button.dataset.mode)))
$$('.choice').forEach(button => button.addEventListener('click', () => setRatio(button.dataset.ratio)))
ui.outputFormat.addEventListener('change', () => ui.compressionField.classList.toggle('hidden', ui.outputFormat.value === 'png'))
ui.compression.addEventListener('input', () => { ui.compressionValue.textContent = `${ui.compression.value}%` })
ui.referenceInput.addEventListener('change', () => addReferences(ui.referenceInput.files))
ui.referenceDropzone.addEventListener('dragover', event => { event.preventDefault(); ui.referenceDropzone.classList.add('dragging') })
ui.referenceDropzone.addEventListener('dragleave', () => ui.referenceDropzone.classList.remove('dragging'))
ui.referenceDropzone.addEventListener('drop', event => { event.preventDefault(); ui.referenceDropzone.classList.remove('dragging'); addReferences(event.dataTransfer.files) })
ui.maskInput.addEventListener('change', () => { maskFile = ui.maskInput.files[0] || null; ui.maskLabel.textContent = maskFile?.name || 'Choose a PNG mask' })
ui.form.addEventListener('submit', generate)
ui.prompt.addEventListener('keydown', event => { if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') ui.form.requestSubmit() })
ui.refresh.addEventListener('click', loadStatus)
ui.login.addEventListener('click', () => beginLogin().catch(error => toast(error.message)))
ui.logout.addEventListener('click', async () => { await requestJson('/api/auth/logout', { method: 'POST' }); await loadStatus() })
ui.createKey.addEventListener('click', () => createKey().catch(error => toast(error.message)))
ui.copyKey.addEventListener('click', async () => { await navigator.clipboard.writeText(ui.newKeyValue.textContent); toast('API key copied.') })
ui.copyCode.addEventListener('click', async () => { await navigator.clipboard.writeText(ui.codeExample.textContent); toast('Example copied.') })

updateCode()
Promise.all([loadStatus(), loadKeys(), loadHistory()]).catch(error => toast(error.message))

