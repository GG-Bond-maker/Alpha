// Browser verification over local Chrome DevTools Protocol; no extra npm packages.
import { writeFile, mkdir } from 'node:fs/promises'

const [socketUrl, siteUrl, output] = process.argv.slice(2)
await mkdir(output, { recursive: true })
const socket = new WebSocket(socketUrl)
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
let sequence = 0
const pending = new Map(), errors = []
socket.onmessage = ({ data }) => {
  const message = JSON.parse(data)
  if (message.id) {
    const promise = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) promise?.reject(new Error(JSON.stringify(message.error)))
    else promise?.resolve(message.result)
  }
  if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails)
  if (message.method === 'Runtime.consoleAPICalled' && message.params.type === 'error') errors.push(message.params)
}
function send(method, params = {}) {
  const id = ++sequence
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
    socket.send(JSON.stringify({ id, method, params }))
  })
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms))
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
async function until(expression, limit = 30000) {
  const start = Date.now()
  while (Date.now() - start < limit) {
    if (await evaluate(expression)) return
    await sleep(100)
  }
  throw new Error('Browser condition timed out: ' + expression)
}
async function screenshot(name) {
  const { cssContentSize } = await send('Page.getLayoutMetrics')
  const width = await evaluate('innerWidth')
  await send('Emulation.setDeviceMetricsOverride', { width, height: Math.min(Math.ceil(cssContentSize.height), 5000), deviceScaleFactor: 1, mobile: false, screenWidth: width, screenHeight: Math.min(Math.ceil(cssContentSize.height), 5000) })
  await sleep(300)
  const result = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  await writeFile(`${output}/${name}.png`, Buffer.from(result.data, 'base64'))
}
try {
  await send('Runtime.enable')
  await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: siteUrl })
  await until("document.querySelectorAll('.nav-item').length > 5")
  const tabs = ['Top-K 选股推荐', '算法评测对比', '组合回测', '滚动窗口验证', '业绩归因', '数据与模型', '因子有效性检验', '全局特征归因', '实验诊断图表']
  const snapshots = []
  let selectionChecks = {}
  for (const tab of tabs) {
    await evaluate(`Array.from(document.querySelectorAll('.nav-item')).find(b => b.textContent.includes(${JSON.stringify(tab)})).click()`)
    await until("(document.querySelector('.content section')?.innerText.length || 0) > 80 && !document.querySelector('.content .loading-state') && !document.querySelector('.content section')?.innerText.includes('正在加载')")
    await sleep(600)
    snapshots.push(await evaluate(`({tab:${JSON.stringify(tab)}, text:document.querySelector('.content section').innerText.slice(0,500), canvases:document.querySelectorAll('.content canvas').length, overflow:document.documentElement.scrollWidth>innerWidth})`))
    if (tab === '数据与模型') {
      await until("document.querySelector('select[aria-label=\"训练方案\"]')")
      selectionChecks.trainingDefault = await evaluate("document.querySelector('select[aria-label=\"训练方案\"]').value")
      if (selectionChecks.trainingDefault !== 'robust') throw new Error('Training must default to bounded temporal comparison')
      selectionChecks.psiDoesNotClaimSkill = await evaluate("document.querySelector('.content section').innerText.includes('不能证明预测有效')")
      if (!selectionChecks.psiDoesNotClaimSkill) throw new Error('PSI must not imply predictive effectiveness')
      await evaluate("(()=>{const scheme=document.querySelector('select[aria-label=\"训练方案\"]');scheme.value='legacy';scheme.dispatchEvent(new Event('change',{bubbles:true}))})()")
      await until("document.querySelector('.slider-row')")
      await evaluate("(()=>{const scheme=document.querySelector('select[aria-label=\"训练方案\"]');scheme.value='robust';scheme.dispatchEvent(new Event('change',{bubbles:true}))})()")
      await until("!document.querySelector('.slider-row')")
      selectionChecks.trainingLegacyToggle = true
      await screenshot('training-protocol-desktop')
    }
    if (tab === '因子有效性检验') {
      await until("document.querySelector('.content section').innerText.includes('模型实际因子数')")
      selectionChecks.factorDiagnosticsDistinguishesModelInputs = await evaluate("document.querySelector('.content section').innerText.includes('实际入模')")
      await screenshot('factor-audit-desktop')
    }
    if (tab === 'Top-K 选股推荐') {
      await until("document.querySelectorAll('.desktop-results tbody > tr').length >= 5")
      await evaluate("Array.from(document.querySelectorAll('.desktop-results button')).find(b=>b.textContent==='因子依据').click()")
      await until("document.querySelector('.factor-detail')")
      await screenshot('recommendations-desktop')
      await evaluate("Array.from(document.querySelectorAll('.desktop-results button')).find(b=>b.textContent==='SHAP 归因').click()")
      await until("document.querySelector('dialog[open] .dialog-body')")
      selectionChecks.explanation = await evaluate("({hasFactorEvidence:document.querySelector('dialog[open]').innerText.includes('多因子对照依据'),hasCalibrated:document.querySelector('dialog[open]').innerText.includes('校准后')})")
      await screenshot('recommendation-explanation')
      await evaluate("document.querySelector('dialog[open] .close-btn').click()")
      await evaluate("const select=document.querySelectorAll('.selection-controls select')[1]; select.value='factor';select.dispatchEvent(new Event('change',{bubbles:true}))")
      await until("!document.querySelector('.content .loading-state') && document.querySelector('.recommendation-results h2')?.textContent.includes('多因子对照')")
      selectionChecks.factorMode = await evaluate("document.querySelector('.recommendation-results h2').textContent")
      await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false })
      await sleep(500)
      selectionChecks.mobileOverflow = await evaluate('document.documentElement.scrollWidth>innerWidth')
      await screenshot('recommendations-mobile')
      await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
      await sleep(300)
    }
  }
  await until("document.querySelectorAll('.diagnostic-chart svg').length === 4")
  await sleep(600)
  const desktopCharts = await evaluate("Array.from(document.querySelectorAll('.diagnostic-chart')).map(n=>({width:n.getBoundingClientRect().width,svgWidth:n.querySelector('svg')?.getAttribute('width')}))")
  const desktopLayout = await evaluate("({width:innerWidth,sidebar:document.querySelector('.sidebar').getBoundingClientRect().width,margin:getComputedStyle(document.querySelector('.main-area')).marginLeft})")
  await screenshot('diagnostics-desktop')
  await evaluate("document.querySelector('select[aria-label=\"选择月度收益口径\"]').value='relative'; document.querySelector('select[aria-label=\"选择月度收益口径\"]').dispatchEvent(new Event('change',{bubbles:true}))")
  await sleep(200)
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: false })
  await sleep(500)
  const mobile = await evaluate("({width:innerWidth, scrollWidth:document.documentElement.scrollWidth, chartWidths:Array.from(document.querySelectorAll('.diagnostic-chart')).map(n=>n.getBoundingClientRect().width)})")
  await screenshot('diagnostics-mobile')
  const result = { tabs: snapshots, selectionChecks, desktopCharts, desktopLayout, mobile, errors }
  await writeFile(`${output}/browser-checks.json`, JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result))
  if (errors.length) process.exitCode = 1
  if (mobile.scrollWidth > mobile.width) process.exitCode = 1
  if (selectionChecks.mobileOverflow || !selectionChecks.explanation?.hasFactorEvidence) process.exitCode = 1
} finally {
  if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ id: ++sequence, method: 'Browser.close' }))
  await sleep(100)
  socket.close()
}
