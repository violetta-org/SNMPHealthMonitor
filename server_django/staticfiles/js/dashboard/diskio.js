import{BaseDashboardUI}from'./base.js';export class DiskIODashboard extends BaseDashboardUI{constructor(dataProcessor){super(dataProcessor);this.currentPage=1;this.perPage=10;this.diskIOData=[];this.totalItems=0;}
registerElements(){this.registerElement('connection-status','#connection-status');this.registerElement('last-update-time','#last-update-time');this.registerElement('diskio-tbody','#diskio-tbody');this.registerElement('pagination-container','#pagination-container');}
attachWebSocketManager(wsManager,sysname,topic){this.wsManager=wsManager;this.sysname=sysname;this.topic=topic;setTimeout(()=>this.setupPaginationListeners(),500);}
setupPaginationListeners(){let container=this.elements['pagination-container'];if(!container){container=document.querySelector('#pagination-container');if(container)this.elements['pagination-container']=container;}
if(!container)return;const newContainer=container.cloneNode(true);container.parentNode.replaceChild(newContainer,container);this.elements['pagination-container']=newContainer;newContainer.addEventListener('click',(e)=>{const target=e.target;if(target.id==='prev-page'){this.changePage(-1);}else if(target.id==='next-page'){this.changePage(1);}});}
changePage(delta){const totalPages=Math.ceil(this.totalItems/this.perPage);const newPage=this.currentPage+delta;if(newPage<1||newPage>totalPages){return;}
this.currentPage=newPage;this.updateDiskIOTable();}
updateDiskIOTable(){let tbody=this.elements['diskio-tbody'];if(!tbody){tbody=document.querySelector('#diskio-tbody');if(tbody)this.elements['diskio-tbody']=tbody;}
let paginationContainer=this.elements['pagination-container'];if(!paginationContainer){paginationContainer=document.querySelector('#pagination-container');if(paginationContainer){this.elements['pagination-container']=paginationContainer;this.setupPaginationListeners();}}
if(!tbody||!paginationContainer){if(this.diskIOData.length>0){console.warn('[DiskIODashboard] Waiting for DOM elements: #diskio-tbody or #pagination-container...');}
return;}
tbody.innerHTML='';let startIndex=0;let endIndex=this.diskIOData.length;if(this.totalItems>this.diskIOData.length){startIndex=0;endIndex=this.diskIOData.length;}else{startIndex=(this.currentPage-1)*this.perPage;endIndex=Math.min(startIndex+this.perPage,this.diskIOData.length);}
for(let i=startIndex;i<endIndex;i++){const disk=this.diskIOData[i];if(!disk)continue;const row=document.createElement('tr');row.innerHTML=`
                <td>${disk.disk || disk.device || 'Unknown'}</td>
                <td>${disk.read_bytes_s != null ? this.dataProcessor.formatBytes(disk.read_bytes_s) + '/s' : 'N/A'}</td>
                <td>${disk.write_bytes_s != null ? this.dataProcessor.formatBytes(disk.write_bytes_s) + '/s' : 'N/A'}</td>
                <td>${this.dataProcessor.formatBytes(disk.read_bytes || 0)}</td>
                <td>${this.dataProcessor.formatBytes(disk.write_bytes || 0)}</td>
            `;tbody.appendChild(row);}
this.updatePaginationUI();}
updatePaginationUI(){const paginationContainer=this.elements['pagination-container'];if(!paginationContainer)return;const totalPages=Math.ceil(this.totalItems/this.perPage);if(totalPages<=1&&this.totalItems===0){paginationContainer.innerHTML='';return;}
paginationContainer.innerHTML=`
            <div class="pagination-info">
                Page ${this.currentPage} of ${totalPages || 1} (${this.totalItems} total)
            </div>
            <div class="pagination-buttons">
                <button id="prev-page" ${this.currentPage <= 1 ? 'disabled' : ''}>Previous</button>
                <button id="next-page" ${this.currentPage >= totalPages ? 'disabled' : ''}>Next</button>
            </div>
        `;}
update(processedData){if(processedData.device_info){this.updateDeviceStatus(processedData.device_info);this.updateLastUpdateTime(processedData.device_info);this.updateServerIP(processedData.device_info);}
const diskIO=processedData.disk_io;if(diskIO&&diskIO.data){this.diskIOData=diskIO.data;if(diskIO.pagination){this.currentPage=diskIO.pagination.page||1;this.totalItems=diskIO.pagination.total||0;if(diskIO.pagination.per_page){this.perPage=diskIO.pagination.per_page;}}else{this.totalItems=this.diskIOData.length;}
this.updateDiskIOTable();}}}