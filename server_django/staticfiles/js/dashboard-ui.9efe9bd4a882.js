export class DashboardUI{constructor(dataProcessor){this.elements=new Map();this.dataProcessor=dataProcessor;this.lastUpdateTime=null;this.cpuCoresInitialized=false;}
registerElement(key,selector){const element=document.querySelector(selector);if(element){this.elements.set(key,element);console.log(`[DashboardUI] Registered element: ${key} -> ${selector}`);}else{console.warn(`[DashboardUI] Element not found: ${selector}`);}}
updateSystemStatus(processedData){console.log('[DashboardUI] Updating system status UI');this.updateLastUpdateTime();if(processedData.system_info){this.updateText('sysname',processedData.system_info.sysname||'N/A');this.updateText('sys-location',processedData.system_info.sys_location||'N/A');this.updateText('sys-uptime',this.dataProcessor.formatUptime(processedData.system_info.sys_uptime));}
if(processedData.cpu_percent&&processedData.cpu_percent.length>0){this.updateCPUCores(processedData.cpu_percent);}
if(processedData.memory){const memPercent=processedData.memory.percent||0;this.updateGauge('memory',memPercent);this.updateText('memory-used',this.dataProcessor.formatBytes(processedData.memory.used));this.updateText('memory-total',this.dataProcessor.formatBytes(processedData.memory.total));this.updateText('memory-total-detail',this.dataProcessor.formatBytes(processedData.memory.total));this.updateText('memory-free',this.dataProcessor.formatBytes(processedData.memory.free));}
if(processedData.swap){const swapPercent=processedData.swap.percent||0;this.updateGauge('swap',swapPercent);this.updateText('swap-used',this.dataProcessor.formatBytes(processedData.swap.used));this.updateText('swap-total',this.dataProcessor.formatBytes(processedData.swap.total));this.updateText('swap-total-detail',this.dataProcessor.formatBytes(processedData.swap.total));this.updateText('swap-free',this.dataProcessor.formatBytes(processedData.swap.free));}
if(processedData.load_avg){const load1=Number(processedData.load_avg.load_1m)||0;const load5=Number(processedData.load_avg.load_5m)||0;const load15=Number(processedData.load_avg.load_15m)||0;this.updateGauge('load-1m',load1);this.updateGauge('load-5m',load5);this.updateGauge('load-15m',load15);this.updateText('load-1m-value',load1);this.updateText('load-5m-value',load5);this.updateText('load-15m-value',load15);}}
updateCPUCores(cpuData){const container=document.getElementById('cpu-cores-container');if(!container){console.warn('[DashboardUI] CPU cores container not found');return;}
const currentCoreCount=container.children.length;const newCoreCount=cpuData.length;if(!this.cpuCoresInitialized||currentCoreCount!==newCoreCount){container.innerHTML='';cpuData.forEach((cpu,index)=>{const coreCard=this.createCPUCoreGauge(index);container.appendChild(coreCard);});this.cpuCoresInitialized=true;console.log(`[DashboardUI] Initialized ${cpuData.length} CPU core gauges`);}
cpuData.forEach((cpu,index)=>{const percent=cpu.percent||0;const gaugeId=`cpu-core-${index}`;const gaugeElement=document.getElementById(`${gaugeId}-gauge`);const valueElement=document.getElementById(`${gaugeId}-value`);if(gaugeElement&&valueElement){const progressCircle=gaugeElement.querySelector('.gauge-progress');if(progressCircle){const circumference=2*Math.PI*45;const offset=circumference-(percent/100)*circumference;progressCircle.style.strokeDashoffset=offset;}
valueElement.textContent=percent.toFixed(1);const unitEl=document.getElementById(`${gaugeId}-unit`);if(unitEl)unitEl.textContent='%';}});console.log(`[DashboardUI] Updated ${cpuData.length} CPU cores`);}
createCPUCoreGauge(coreIndex){const card=document.createElement('div');card.className='gauge-card';const gaugeId=`cpu-core-${coreIndex}`;card.innerHTML=`
            <h3>Core ${coreIndex + 1}</h3>
            <div class="gauge-wrapper">
                <svg id="${gaugeId}-gauge" class="gauge" viewBox="0 0 120 120">
                    <circle class="gauge-background" cx="60" cy="60" r="45"></circle>
                    <circle class="gauge-progress" cx="60" cy="60" r="45"></circle>
                </svg>
                <div class="gauge-content">
                    <span id="${gaugeId}-value" class="gauge-value">0.0</span>
                    <span id="${gaugeId}-unit" class="gauge-unit">%</span>
                </div>
            </div>
        `;return card;}
updateGauge(id,percent){const gaugeElement=this.elements.get(id+'-gauge');const valueElement=this.elements.get(id+'-value');if(!gaugeElement){console.warn(`[DashboardUI] Gauge not found: ${id}-gauge`);return;}
const clampedPercent=Math.min(Math.max(percent,0),100);const progressCircle=gaugeElement.querySelector('.gauge-progress');if(progressCircle){const circumference=2*Math.PI*45;const offset=circumference-(clampedPercent/100)*circumference;progressCircle.style.strokeDashoffset=offset;}
if(valueElement){valueElement.textContent=clampedPercent.toFixed(1);}
let unitEl=null;if(gaugeElement.parentElement){unitEl=gaugeElement.parentElement.querySelector('.gauge-unit');}
if(!unitEl){if(valueElement&&valueElement.nextElementSibling&&valueElement.nextElementSibling.classList.contains('gauge-unit')){unitEl=valueElement.nextElementSibling;}}
if(unitEl){let unit='%';if(id.startsWith('temperature'))unit='°C';else if(id.startsWith('cpu-core'))unit='%';else if(id.startsWith('load-'))unit='%';else if(id==='memory'||id==='swap')unit='%';unitEl.textContent=unit;}
console.log(`[DashboardUI] Updated gauge ${id}: ${clampedPercent.toFixed(1)}%`);}
updateText(id,text){const element=this.elements.get(id);if(element){element.textContent=text;}}
updateLastUpdateTime(){const lastUpdateElement=this.elements.get('last-update-time');if(lastUpdateElement){const now=new Date();const timeString=now.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});lastUpdateElement.textContent=timeString;this.lastUpdateTime=now;}}
updateConnectionStatus(isConnected){const statusElement=this.elements.get('connection-status');if(statusElement){statusElement.textContent=isConnected?'Connected':'Disconnected';statusElement.className=isConnected?'status-badge status-connected':'status-badge status-disconnected';}}
showToast(message,type='error',options={}){const container=document.getElementById('toast-container');if(!container){console.warn('[DashboardUI] Toast container not found');return;}
const toast=document.createElement('div');toast.className='toast '+type;const icons={error:'❌',success:'✅',warning:'⚠️',info:'ℹ️'};const titles={error:'Error',success:'Success',warning:'Warning',info:'Information'};let toastHTML=`
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-content">
                <div class="toast-title">${titles[type] || titles.info}</div>
                <div class="toast-message">${message}</div>
            </div>
        `;if(options.actions&&options.actions.length>0){toastHTML+='<div class="toast-actions">';options.actions.forEach(action=>{toastHTML+=`<button class="toast-btn toast-btn-${action.type || 'secondary'}" data-action="${action.id}">${action.label}</button>`;});toastHTML+='</div>';}
toast.innerHTML=toastHTML;container.appendChild(toast);if(options.actions){options.actions.forEach(action=>{const btn=toast.querySelector(`[data-action="${action.id}"]`);if(btn&&action.callback){btn.addEventListener('click',()=>{action.callback();this.closeToast(toast);});}});}
const duration=options.duration||(type==='error'?3000:5000);if(duration>0){setTimeout(()=>{this.closeToast(toast);},duration);}
console.log(`[DashboardUI] Toast shown: ${type} - ${message}`);}
closeToast(toast){toast.style.animation='slideOut 0.3s ease forwards';setTimeout(()=>{toast.remove();},300);}
showError(message,retryCallback){this.showToast(message,'error',{duration:0,actions:[{id:'retry',label:'Retry',type:'primary',callback:retryCallback},{id:'close',label:'Close',type:'secondary',callback:()=>{}}]});}
hideError(){const container=document.getElementById('toast-container');if(container){container.innerHTML='';}}
showSuccess(message){this.showToast(message,'success',{duration:3000});}
showWarning(message){this.showToast(message,'warning',{duration:4000});}
updateSystem(processedData){console.log('[DashboardUI] Updating system UI',processedData);this.updateLastUpdateTime();if(processedData.system_info){this.updateText('sysname',processedData.system_info.sysname||'N/A');this.updateText('sys-location',processedData.system_info.sys_location||'N/A');this.updateText('sys-uptime',this.dataProcessor.formatUptime(processedData.system_info.sys_uptime));}
if(processedData.load_avg){const load1m=Number(processedData.load_avg.load_1m)||0;const load5m=Number(processedData.load_avg.load_5m)||0;const load15m=Number(processedData.load_avg.load_15m)||0;this.updateGauge('load-1m',load1m);this.updateGauge('load-5m',load5m);this.updateGauge('load-15m',load15m);this.updateText('load-1m-value',load1m);this.updateText('load-5m-value',load5m);this.updateText('load-15m-value',load15m);}else{console.warn('[DashboardUI] No load_avg data in processedData');}}
updateCPU(processedData){console.log('[DashboardUI] Updating CPU UI');this.updateLastUpdateTime();if(processedData.cpu_percent&&processedData.cpu_percent.length>0){this.updateCPUCores(processedData.cpu_percent);}}
updateMemory(processedData){console.log('[DashboardUI] Updating memory UI');this.updateLastUpdateTime();if(processedData.memory){const memPercent=processedData.memory.percent||0;this.updateGauge('memory',memPercent);this.updateText('memory-used',this.dataProcessor.formatBytes(processedData.memory.used));this.updateText('memory-total',this.dataProcessor.formatBytes(processedData.memory.total));this.updateText('memory-total-detail',this.dataProcessor.formatBytes(processedData.memory.total));this.updateText('memory-free',this.dataProcessor.formatBytes(processedData.memory.free));this.updateText('memory-used-detail',this.dataProcessor.formatBytes(processedData.memory.used));}
if(processedData.swap){const swapPercent=processedData.swap.percent||0;this.updateGauge('swap',swapPercent);this.updateText('swap-used',this.dataProcessor.formatBytes(processedData.swap.used));this.updateText('swap-total',this.dataProcessor.formatBytes(processedData.swap.total));this.updateText('swap-total-detail',this.dataProcessor.formatBytes(processedData.swap.total));this.updateText('swap-free',this.dataProcessor.formatBytes(processedData.swap.free));this.updateText('swap-used-detail',this.dataProcessor.formatBytes(processedData.swap.used));}}
updateNetwork(processedData){console.log('[DashboardUI] Updating network UI');this.updateLastUpdateTime();const container=document.getElementById('network-interfaces-container');if(!container){console.warn('[DashboardUI] Network interfaces container not found');return;}
if(processedData.net_io&&processedData.net_io.length>0){container.innerHTML='';processedData.net_io.forEach((iface)=>{const ifaceCard=document.createElement('div');ifaceCard.className='network-interface-card';ifaceCard.innerHTML=`
                    <h3>${iface.interface || 'Unknown'}</h3>
                    <div class="network-stats">
                        <div class="stat-item">
                            <label>Bytes Sent:</label>
                            <span>${this.dataProcessor.formatBytes(iface.bytes_sent || 0)}</span>
                        </div>
                        <div class="stat-item">
                            <label>Bytes Received:</label>
                            <span>${this.dataProcessor.formatBytes(iface.bytes_recv || 0)}</span>
                        </div>
                `;container.appendChild(ifaceCard);});}}
updateDisk(processedData){console.log('[DashboardUI] Updating disk UI');this.updateLastUpdateTime();const container=document.getElementById('disk-usage-container');if(!container){console.warn('[DashboardUI] Disk usage container not found');return;}
if(processedData.disk_usage&&processedData.disk_usage.length>0){container.innerHTML='';processedData.disk_usage.forEach((disk)=>{const diskCard=document.createElement('div');diskCard.className='disk-card';const percent=disk.percent||0;diskCard.innerHTML=`
                    <h3>${disk.mountpoint || disk.device || 'Unknown'}</h3>
                    <div class="disk-gauge">
                        <svg class="gauge" viewBox="0 0 120 120">
                            <circle class="gauge-background" cx="60" cy="60" r="45" fill="none" stroke="#3a4d5f" stroke-width="8"/>
                            <circle class="gauge-progress disk-${disk.device || 'unknown'}" cx="60" cy="60" r="45" fill="none" stroke="#00bcd4" stroke-width="8" 
                                    stroke-dasharray="283" stroke-dashoffset="283" transform="rotate(-90 60 60)" stroke-linecap="round"/>
                            <text x="60" y="55" text-anchor="middle" class="gauge-value">${Math.round(percent)}%</text>
                            <text x="60" y="70" text-anchor="middle" class="gauge-sublabel">${disk.device || ''}</text>
                        </svg>
                    </div>
                    <div class="disk-info">
                        <div class="disk-stat">
                            <label>Total:</label>
                            <span>${this.dataProcessor.formatBytes(disk.total || 0)}</span>
                        </div>
                        <div class="disk-stat">
                            <label>Used:</label>
                            <span>${this.dataProcessor.formatBytes(disk.used || 0)}</span>
                        </div>
                        <div class="disk-stat">
                            <label>Free:</label>
                            <span>${this.dataProcessor.formatBytes(disk.free || 0)}</span>
                        </div>
                    </div>
                `;container.appendChild(diskCard);setTimeout(()=>{const progressCircle=diskCard.querySelector('.gauge-progress');if(progressCircle){const circumference=2*Math.PI*45;const offset=circumference-(percent/100)*circumference;progressCircle.style.strokeDashoffset=offset;}},100);});}}
updateDiskIO(processedData){console.log('[DashboardUI] Updating disk IO UI');this.updateLastUpdateTime();const tbody=document.getElementById('diskio-tbody');const paginationContainer=document.getElementById('pagination-container');if(!tbody){console.warn('[DashboardUI] DiskIO table body not found');return;}
if(processedData.disk_io&&processedData.disk_io.data){tbody.innerHTML='';processedData.disk_io.data.forEach((disk)=>{const row=document.createElement('tr');row.innerHTML=`
                    <td>${disk.disk || 'Unknown'}</td>
                    <td>${this.dataProcessor.formatBytes(disk.read_bytes_s || 0)}/s</td>
                    <td>${this.dataProcessor.formatBytes(disk.write_bytes_s || 0)}/s</td>
                    <td>${(disk.read_iops || 0).toFixed(2)}</td>
                    <td>${(disk.write_iops || 0).toFixed(2)}</td>
                    <td>${this.dataProcessor.formatBytes(disk.read_bytes || 0)}</td>
                    <td>${this.dataProcessor.formatBytes(disk.write_bytes || 0)}</td>
                `;tbody.appendChild(row);});if(paginationContainer&&processedData.disk_io.pagination){const pagination=processedData.disk_io.pagination;paginationContainer.innerHTML=`
                    <div class="pagination-info">
                        Page ${pagination.page} of ${pagination.total_pages} (${pagination.total} total)
                    </div>
                    <div class="pagination-buttons">
                        <button id="prev-page" ${pagination.page <= 1 ? 'disabled' : ''}>Previous</button>
                        <button id="next-page" ${pagination.page >= pagination.total_pages ? 'disabled' : ''}>Next</button>
                    </div>
                `;}}}}